"""Typed project exceptions."""


class SwarmBaseException(Exception):
    """Base class for all swarm exceptions."""


class DataPipelineError(SwarmBaseException):
    """Data fetch or parsing failure."""


class StaleDataError(DataPipelineError):
    """Data exists but is too stale to use."""


class RegimeUnavailableError(SwarmBaseException):
    """Current regime missing or stale."""


class ConfluenceRejectedError(SwarmBaseException):
    """Signal confluence did not meet threshold."""


class ExecutionError(SwarmBaseException):
    """Execution path failed to submit or track order."""


class CircuitBreakerActiveError(SwarmBaseException):
    """Execution is paused because circuit breaker is active."""


class RiskLimitBreachedError(SwarmBaseException):
    """A hard risk limit would be exceeded."""
