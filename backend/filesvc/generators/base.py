from abc import ABC, abstractmethod

class BaseGenerator(ABC):
    """Abstract base class for file generators taking structured specs."""

    default_extension: str = ""

    @abstractmethod
    def generate(self, spec: dict, output_path: str) -> None:
        """Generate file at output_path from spec or raise ValueError."""
        pass

    def validate_spec(self, spec: dict) -> None:
        """Validate that spec contains necessary fields."""
        if not isinstance(spec, dict):
            raise ValueError("Spec must be a JSON object dictionary.")

    @abstractmethod
    def summarize_spec(self, spec: dict) -> str:
        """Return a concise, human-readable summary of the spec for the manifest."""
        pass
