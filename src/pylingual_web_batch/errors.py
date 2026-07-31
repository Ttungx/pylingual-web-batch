class PylingualError(Exception):
    """Base exception for pylingual web batch errors."""


class ApiError(PylingualError):
    """Base exception for API-related errors."""


class ApiResponseError(ApiError):
    """Raised when the API returns an unexpected response."""


class PermanentDecompilerError(ApiError):
    """Raised when decompilation fails permanently."""


class StateError(PylingualError):
    """Raised when persisted batch state is invalid or unavailable."""


class LockError(PylingualError):
    """Raised when the batch lock cannot be acquired."""


class ConfigurationError(PylingualError):
    """Raised when batch configuration is invalid."""
