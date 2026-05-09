"""Exception types raised by the grader."""


class SdrGraderError(Exception):
    """Base class for all sdr-grader errors."""


class InvalidSnapshotError(SdrGraderError):
    """Snapshot JSON does not conform to the expected shape."""


class UnknownPlatformError(SdrGraderError):
    """Auto-detection could not identify the platform; pass --platform to override."""


class RubricValidationError(SdrGraderError):
    """Rubric YAML is malformed or references unknown check functions."""
