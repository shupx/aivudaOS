from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

import bcrypt

from core.auth.models import SessionInfo
from core.config.service import ConfigService
from core.errors import AuthenticationError
from core.paths import SESSIONS_DIR


class AuthService:
    def __init__(self, config_service: ConfigService) -> None:
        self._config = config_service
        self._sessions: dict[str, SessionInfo] = {}
        self._load_persisted_sessions()

    def login(self, username: str, password: str) -> SessionInfo:
        user = self._config.find_user(username)
        if user is None:
            raise AuthenticationError("Invalid credentials")
        if not bcrypt.checkpw(
            password.encode("utf-8"), user.password_hash.encode("utf-8")
        ):
            raise AuthenticationError("Invalid credentials")

        token = str(uuid.uuid4())
        session = SessionInfo(
            token=token,
            username=user.username,
            role=user.role,
            created_at=int(time.time()),
        )
        self._sessions[token] = session
        self._persist_session(session)
        return session

    def validate_token(self, token: str) -> SessionInfo:
        session = self._sessions.get(token)
        if session is None:
            raise AuthenticationError("Invalid or expired token")
        return session

    def logout(self, token: str) -> None:
        self._sessions.pop(token, None)
        path = self._session_path(token)
        if path.exists():
            path.unlink()

    @staticmethod
    def hash_password(plain: str) -> str:
        return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # --- Persistence ---

    def _session_path(self, token: str) -> Path:
        safe = hashlib.sha256(token.encode()).hexdigest()
        return SESSIONS_DIR / f"{safe}.json"

    def _persist_session(self, session: SessionInfo) -> None:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        path = self._session_path(session.token)
        path.write_text(
            json.dumps(
                {
                    "token": session.token,
                    "username": session.username,
                    "role": session.role,
                    "created_at": session.created_at,
                }
            ),
            encoding="utf-8",
        )

    def _load_persisted_sessions(self) -> None:
        if not SESSIONS_DIR.exists():
            return
        for f in SESSIONS_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text("utf-8"))
                session = SessionInfo(**data)
                self._sessions[session.token] = session
            except Exception:
                f.unlink(missing_ok=True)
