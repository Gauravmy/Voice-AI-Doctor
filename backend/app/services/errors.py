"""Domain errors. Each carries a stable machine-readable `code` used by the REST
API (HTTP error bodies) and by the voice tools (tool result `status`)."""


class DomainError(Exception):
    http_status = 400

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


class ValidationError(DomainError):
    http_status = 422


class NotFoundError(DomainError):
    http_status = 404


class SlotUnavailableError(DomainError):
    http_status = 409
