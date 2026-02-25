from __future__ import annotations

from fastapi import APIRouter

from backend.app.schemas import LoginRequest, LoginResponse
from backend.app.services.auth import auth_token, issue_login_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    result = issue_login_token(payload.username, payload.password)
    return LoginResponse(access_token=result["access_token"], role=result["role"])


@router.get("/me")
async def me(token: str) -> dict[str, str]:
    return await auth_token(token)
