from fastapi import APIRouter
from app.services import audit

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def get_audit_log(limit: int = 100):
    return {"entries": audit.tail(limit)}
