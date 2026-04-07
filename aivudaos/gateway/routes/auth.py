from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, HTTPException

from aivudaos.core.auth.service import AuthService
from aivudaos.core.errors import AuthenticationError
from aivudaos.gateway.deps import get_auth_service
from aivudaos.gateway.schemas import LoginRequest, LoginResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    auth: AuthService = get_auth_service()
    try:
        session = auth.login(payload.username, payload.password)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return LoginResponse(access_token=session.token, role=session.role)


@router.get("/me")
async def me(token: str) -> Dict[str, str]:
    auth: AuthService = get_auth_service()
    try:
        session = auth.validate_token(token)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"username": session.username, "role": session.role}
