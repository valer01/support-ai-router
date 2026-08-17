"""Local username/password auth only (v1 — no OIDC yet, unlike
ask-devops-dashboard; can be added later following the same pattern if
needed)."""
from __future__ import annotations
import os
import secrets

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from starlette.middleware.sessions import SessionMiddleware

from app import local_users

SESSION_SECRET = os.environ.get("SUPPORTROUTER_SESSION_SECRET") or secrets.token_hex(32)

router = APIRouter(prefix="/auth", tags=["auth"])


def install_session_middleware(app):
    app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax")


def current_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated. Go to /auth/login.")
    return user


def current_user_optional(request: Request):
    return request.session.get("user")


@router.get("/login")
async def login_page(request: Request, error: str = ""):
    return HTMLResponse(_login_page_html(error=error))


@router.post("/local-login")
async def local_login(request: Request):
    form = await request.form()
    raw_username = form.get("username")
    raw_password = form.get("password")
    username = (raw_username if isinstance(raw_username, str) else "").strip()
    password = raw_password if isinstance(raw_password, str) else ""

    if not username or not password:
        return HTMLResponse(_login_page_html(error="Enter both username and password."), status_code=400)

    if not local_users.verify_password(username, password):
        return HTMLResponse(_login_page_html(error="Invalid username or password."), status_code=401)

    user = local_users.get_user(username)
    if not user:
        return HTMLResponse(_login_page_html(error="Invalid username or password."), status_code=401)
    request.session["user"] = {
        "sub": f"local:{username}",
        "username": username,
        "name": user.get("name") or username,
        "email": user.get("email", ""),
        "auth_mode": "local",
    }
    return RedirectResponse("/", status_code=303)


@router.get("/logout")
@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/auth/login", status_code=303)


@router.get("/me")
async def me(request: Request):
    return {"user": current_user_optional(request)}


def _login_page_html(error: str = "") -> str:
    err_html = (
        f'<p style="color:#f87171;font-size:13px;margin:0 0 12px;">{error}</p>' if error else ""
    )
    return f"""
    <html><body style="background:#0f172a;color:#e2e8f0;font-family:sans-serif;
      display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
      <div style="background:#1e293b;padding:32px;border-radius:12px;border:1px solid #334155;min-width:340px;">
        <h2 style="margin-top:0;">Support AI Router</h2>
        {err_html}
        <form method="post" action="/auth/local-login">
          <label style="font-size:13px;">Username</label>
          <input name="username" style="width:100%;padding:8px;margin:6px 0 14px;background:#0f172a;
            border:1px solid #475569;border-radius:6px;color:#e2e8f0;box-sizing:border-box;" autofocus />
          <label style="font-size:13px;">Password</label>
          <input name="password" type="password" style="width:100%;padding:8px;margin:6px 0 18px;
            background:#0f172a;border:1px solid #475569;border-radius:6px;color:#e2e8f0;box-sizing:border-box;" />
          <button style="width:100%;padding:10px;background:#4f46e5;border:none;border-radius:8px;
            color:white;font-weight:600;cursor:pointer;">Log in</button>
        </form>
      </div>
    </body></html>
    """
