"""鉴权路由 /api/v1/auth。"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.route import EnvelopeRoute
from app.modules.auth import service
from app.modules.auth.models import User
from app.modules.auth.schemas import LoginIn, RefreshIn

router = APIRouter(prefix="/auth", tags=["auth"], route_class=EnvelopeRoute)


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    return service.login(db, body.username, body.password, ip, ua)


@router.post("/refresh")
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    return service.refresh(db, body.refresh_token)


@router.post("/logout")
def logout(
    body: RefreshIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service.logout(db, body.refresh_token if body else None, user)
    return None


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.me(db, user)
