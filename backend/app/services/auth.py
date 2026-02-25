from __future__ import annotations

import uuid

from fastapi import HTTPException

from backend.app.core.state import DEFAULT_USER, TOKENS


def issue_login_token(username: str, password: str) -> dict[str, str]:
    if username != DEFAULT_USER["username"] or password != DEFAULT_USER["password"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = str(uuid.uuid4())
    TOKENS[token] = {"username": username, "role": DEFAULT_USER["role"]}
    return {"access_token": token, "role": DEFAULT_USER["role"]}


async def auth_token(token: str) -> dict[str, str]:
    user = TOKENS.get(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user
