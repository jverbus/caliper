class CaliperError(Exception):
    """Base exception for Caliper."""


class NotFoundError(CaliperError):
    """Raised when an expected resource is missing."""


class InvalidTransitionError(CaliperError):
    """Raised when a state transition is invalid."""
