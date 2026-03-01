from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from core.errors import AppOperationConflictError, NotFoundError


@dataclass
class OperationRecord:
    operation_id: str
    operation_type: str
    app_id: str | None
    status: str
    started_at: int
    ended_at: int | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    seq: int = 0
    done: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)
    condition: threading.Condition = field(default_factory=threading.Condition)


class AppOperationManager:
    """In-memory operation manager for streaming long-running app operations."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, OperationRecord] = {}
        self._app_running: dict[str, str] = {}

    def start_operation(self, operation_type: str, app_id: str | None) -> OperationRecord:
        with self._lock:
            if app_id and app_id in self._app_running:
                active_op = self._app_running[app_id]
                raise AppOperationConflictError(
                    f"{app_id} 已有运行中的操作: {active_op}"
                )

            operation_id = uuid.uuid4().hex
            now = int(time.time())
            record = OperationRecord(
                operation_id=operation_id,
                operation_type=operation_type,
                app_id=app_id,
                status="queued",
                started_at=now,
            )
            self._records[operation_id] = record
            if app_id:
                self._app_running[app_id] = operation_id

        self.publish(
            operation_id,
            "status",
            status="queued",
            phase="queued",
        )
        return record

    def bind_app_id(self, operation_id: str, app_id: str) -> None:
        with self._lock:
            record = self._records.get(operation_id)
            if record is None:
                raise NotFoundError(f"operation not found: {operation_id}")
            if record.app_id == app_id:
                return
            if record.app_id and record.app_id != app_id:
                raise AppOperationConflictError(
                    f"operation {operation_id} 已绑定 app_id={record.app_id}"
                )
            if app_id in self._app_running and self._app_running[app_id] != operation_id:
                active_op = self._app_running[app_id]
                raise AppOperationConflictError(
                    f"{app_id} 已有运行中的操作: {active_op}"
                )
            record.app_id = app_id
            self._app_running[app_id] = operation_id

    def publish(self, operation_id: str, event_type: str, **payload: Any) -> None:
        record = self._require_record(operation_id)
        with record.condition:
            record.seq += 1
            event = {
                "operation_id": operation_id,
                "seq": record.seq,
                "ts": int(time.time()),
                "type": event_type,
                "operation_type": record.operation_type,
                "app_id": record.app_id,
                **payload,
            }
            record.events.append(event)
            record.condition.notify_all()

    def mark_running(self, operation_id: str) -> None:
        record = self._require_record(operation_id)
        record.status = "running"
        self.publish(
            operation_id,
            "status",
            status="running",
            phase="running",
        )

    def mark_completed(self, operation_id: str, result: dict[str, Any] | None = None) -> None:
        record = self._require_record(operation_id)
        record.status = "completed"
        record.done = True
        record.ended_at = int(time.time())
        record.result = result or {}
        self.publish(
            operation_id,
            "completed",
            status="completed",
            done=True,
            result=record.result,
        )
        self._release_app(record)

    def mark_failed(self, operation_id: str, error: str) -> None:
        record = self._require_record(operation_id)
        record.status = "failed"
        record.error = error
        record.done = True
        record.ended_at = int(time.time())
        self.publish(
            operation_id,
            "error",
            status="failed",
            done=True,
            message=error,
        )
        self.publish(
            operation_id,
            "completed",
            status="failed",
            done=True,
            error=error,
        )
        self._release_app(record)

    def get_operation(self, operation_id: str) -> dict[str, Any]:
        record = self._require_record(operation_id)
        return {
            "operation_id": record.operation_id,
            "operation_type": record.operation_type,
            "app_id": record.app_id,
            "status": record.status,
            "started_at": record.started_at,
            "ended_at": record.ended_at,
            "error": record.error,
            "result": record.result,
            "done": record.done,
        }

    def wait_events(
        self,
        operation_id: str,
        since_seq: int,
        timeout: float = 15.0,
    ) -> tuple[list[dict[str, Any]], bool]:
        record = self._require_record(operation_id)
        with record.condition:
            if not record.done and record.seq <= since_seq:
                record.condition.wait(timeout=timeout)
            events = [evt for evt in record.events if int(evt.get("seq", 0)) > since_seq]
            return events, record.done

    def _require_record(self, operation_id: str) -> OperationRecord:
        with self._lock:
            record = self._records.get(operation_id)
        if record is None:
            raise NotFoundError(f"operation not found: {operation_id}")
        return record

    def _release_app(self, record: OperationRecord) -> None:
        if not record.app_id:
            return
        with self._lock:
            current = self._app_running.get(record.app_id)
            if current == record.operation_id:
                self._app_running.pop(record.app_id, None)
