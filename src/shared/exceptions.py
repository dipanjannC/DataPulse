"""DataPulse exception hierarchy."""


class DataPulseError(Exception):
    """Base exception for all DataPulse errors."""


class DataLoadError(DataPulseError):
    """Raised when data loading or parsing fails."""


class GraphBuildError(DataPulseError):
    """Raised when graph construction fails."""


class QueryError(DataPulseError):
    """Raised when query resolution fails."""
