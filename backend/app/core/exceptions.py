"""Application-wide exception hierarchy."""


class AppError(Exception):
    """Base exception for application errors."""

    def __init__(self, message: str, *, code: str = "app_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class ConfigurationError(AppError):
    """Raised when required configuration is missing or invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="configuration_error")


class DatabaseNotConfiguredError(ConfigurationError):
    """Raised when a database operation is attempted without DATABASE_URL."""

    def __init__(self) -> None:
        super().__init__(
            "DATABASE_URL is not configured. Set it to your Supabase PostgreSQL connection string."
        )


class TradingPipelineError(AppError):
    """Base for future trade-pipeline violations (risk, validation, routing)."""

    def __init__(self, message: str, *, code: str = "trading_pipeline_error") -> None:
        super().__init__(message, code=code)


class BrokerError(AppError):
    """Base for future broker-adapter failures."""

    def __init__(self, message: str, *, code: str = "broker_error") -> None:
        super().__init__(message, code=code)
