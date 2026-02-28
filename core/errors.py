from __future__ import annotations


class AivudaError(Exception):
    """Base for all domain errors."""


class NotFoundError(AivudaError):
    """Resource not found."""


class AuthenticationError(AivudaError):
    """Invalid credentials or expired session."""


class ConfigVersionConflictError(AivudaError):
    """Optimistic lock failure on config write."""


class InstallTaskConflictError(AivudaError):
    """An install task is already running for this app."""


class AppNotInstalledError(NotFoundError):
    """App is not installed."""


class AppRuntimeError(AivudaError):
    """Runtime operation (start/stop/container) failed."""


class RuntimeNotAvailableError(AivudaError):
    """Required runtime (docker/podman) is not installed."""


class ArtifactVerificationError(AivudaError):
    """SHA256 mismatch on downloaded artifact."""


class InvalidConfigError(AivudaError):
    """Config validation failed."""


class PackageFormatError(AivudaError):
    """App package format is invalid or missing manifest."""
