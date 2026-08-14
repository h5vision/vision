from __future__ import annotations


class ResumeError(RuntimeError):
    """프론트와 CLI가 분기할 수 있는 재개 기능 오류."""

    def __init__(self, code: str, message: str, *, conflict: bool = True,
                 details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.conflict = conflict
        self.details = details or {}

    def as_dict(self) -> dict:
        return {
            "ok": False,
            "reason": self.code,
            "detail": self.message,
            "conflict": self.conflict,
            **self.details,
        }
