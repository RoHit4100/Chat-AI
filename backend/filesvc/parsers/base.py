from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ParsedResult:
    """Standardized result returned by file parsers."""
    text: str = ""
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    structured_data: Any = None
    image_info: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert result to serializable dictionary for parsed_path storage."""
        return {
            "text": self.text,
            "summary": self.summary,
            "metadata": self.metadata,
            "structured_data": self.structured_data,
            "image_info": self.image_info,
        }

class BaseParser(ABC):
    """Abstract base class for all file parsers."""

    @abstractmethod
    def parse(self, file_path: str, original_filename: str) -> ParsedResult:
        """Parse file content from disk and return a ParsedResult."""
        pass
