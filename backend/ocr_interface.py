"""OCR Provider Interface — Abstract factory for all OCR backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict
import os


@dataclass
class OCRResult:
    """Structured OCR extraction result."""
    raw_text: str
    structured_data: Dict[str, Any]
    confidence: float
    provider: str
    pages_processed: int = 1
    processing_time_ms: int = 0


class BaseOCRProvider(ABC):
    """Base class all OCR providers must implement."""

    @abstractmethod
    async def extract(self, image_path: str, mime_type: str = "image/png") -> OCRResult:
        """Extract data from a single image."""

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Return health status."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier."""

    @property
    @abstractmethod
    def is_local(self) -> bool:
        """Whether this provider runs locally."""


class _ProviderRegistry:
    """Plugin registry — providers self-register via factory.register()."""

    def __init__(self):
        self._providers: Dict[str, type] = {}

    def register(self, name: str, cls: type):
        self._providers[name] = cls

    def __call__(self, name: str) -> BaseOCRProvider:
        if name not in self._providers:
            available = list(self._providers.keys())
            raise ValueError(f"Unknown OCR provider: {name}. Available: {available}")
        return self._providers[name]()

    def get_provider(self) -> BaseOCRProvider:
        """Get the active provider from env var."""
        name = os.getenv("OCR_PROVIDER", "tesseract")
        return self(name)

    @property
    def available(self):
        return list(self._providers.keys())


factory = _ProviderRegistry()


class _ProviderFactoryWrapper:
    """Backward-compatible wrapper for main.py."""

    @staticmethod
    def list_providers():
        return {
            "available": factory.available,
            "active": os.getenv("OCR_PROVIDER", "tesseract")
        }

    @staticmethod
    def get_provider():
        return factory.get_provider()


get_ocr_provider = _ProviderFactoryWrapper()
