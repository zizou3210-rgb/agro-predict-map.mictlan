from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProgressReporter:
    def __init__(self, progress_file: Path | None):
        self.progress_file = progress_file

    def _write(self, payload: dict[str, Any]) -> None:
        if self.progress_file is None:
            return
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)
        self.progress_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def update(
        self,
        percent: int,
        stage: str,
        message: str,
        *,
        status: str = "running",
        details: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "status": status,
            "percent": percent,
            "stage": stage,
            "message": message,
            "updated_at": utc_timestamp(),
        }
        if details:
            payload["details"] = details
        self._write(payload)

    def complete(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        self.update(
            100,
            "Upload complete",
            message,
            status="completed",
            details=details,
        )

    def error(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        self.update(
            100,
            "Upload error",
            message,
            status="error",
            details=details,
        )

    def pause(
        self,
        percent: int,
        stage: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.update(
            percent,
            stage,
            message,
            status="paused",
            details=details,
        )
