"""Typed errors. Agents must be able to distinguish 'you are wrong' from 'the board is broken'."""


class BlackboardError(Exception):
    code = "ERROR"

    def __init__(self, message: str, **detail):
        super().__init__(message)
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict:
        return {"error": self.code, "message": self.message, **self.detail}


class InvalidURI(BlackboardError):
    code = "INVALID_URI"


class NotFound(BlackboardError):
    code = "NOT_FOUND"


class VersionConflict(BlackboardError):
    """CAS failure (D5 / Delta1). Carries the current version so the caller can re-read and merge."""
    code = "VERSION_CONFLICT"


class Forbidden(BlackboardError):
    """Topic authorization failure. Enforced at the daemon, never in the prompt (Delta10)."""
    code = "FORBIDDEN"


class DigestRequired(BlackboardError):
    """Delta7: no entry is written without a digest."""
    code = "DIGEST_REQUIRED"


class PayloadError(BlackboardError):
    code = "PAYLOAD_ERROR"
