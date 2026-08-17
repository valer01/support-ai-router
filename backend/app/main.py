import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse

from app.routers import intake, teams, oncall, audit_router, chat
from app import auth, local_users
from app.db import init_db
from app.seed import seed_teams_if_missing
from app.services import classification_service

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    n = seed_teams_if_missing()
    if n:
        print(f"Seeded {n} team(s) into the routing matrix.")
    seeded_password = local_users.seed_default_user_if_missing()
    if seeded_password:
        print(
            "\n"
            "🔑  Seeded local login account:\n"
            f"     username: {local_users.DEFAULT_USERNAME}\n"
            f"     password: {seeded_password}\n"
            "     (also written to data/INITIAL_LOGIN_CREDENTIALS.txt — read once, then delete it)\n"
        )
    if not classification_service.available():
        print("ℹ  ANTHROPIC_API_KEY not set — classification falls back to human review for every request.\n")
    yield


app = FastAPI(title="Support AI Router", version="0.1.0", lifespan=lifespan)

PUBLIC_PATH_PREFIXES = ("/auth", "/api/health")


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if path.startswith(PUBLIC_PATH_PREFIXES) or path.startswith("/static"):
        return await call_next(request)
    if not request.session.get("user"):
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        return RedirectResponse("/auth/login")
    return await call_next(request)


# Must be installed AFTER the custom middleware above so it ends up
# OUTERMOST in Starlette's stack (last add_middleware call = outermost =
# runs first), guaranteeing request.session exists by the time
# require_login reads it. (Same ordering requirement as
# ask-devops-dashboard's main.py.)
auth.install_session_middleware(app)

app.include_router(auth.router)
app.include_router(intake.router)
app.include_router(chat.router)
app.include_router(teams.router)
app.include_router(oncall.router)
app.include_router(audit_router.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
