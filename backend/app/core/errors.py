class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class IntegrationUnavailable(AppError):
    def __init__(self, service: str):
        super().__init__(503, "INTEGRATION_UNAVAILABLE", f"{service} is not available")


class NotFound(AppError):
    def __init__(self):
        super().__init__(404, "NOT_FOUND", "Record was not found")


class Conflict(AppError):
    def __init__(self, message: str = "Record changed; refresh and try again"):
        super().__init__(409, "CONFLICT", message)
