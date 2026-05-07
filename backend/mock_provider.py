"""
Mock OCR Provider — returns realistic property data without API calls.
Use for: testing, frontend development, demos without OpenAI credits.
"""
import os
import time
import logging
from typing import Dict, Any
from .ocr_interface import BaseOCRProvider, OCRResult, factory

logger = logging.getLogger(__name__)


class MockOCRProvider(BaseOCRProvider):
    """Pre-canned responses for rapid development and testing."""
    
    MOCK_RESPONSES = {
        "default": {
            "document_type": "certificate_of_title",
            "title_reference": "Vol 5678 Fol 90",
            "registered_proprietor": {
                "names": ["Jane Elizabeth Smith", "John Robert Smith"],
                "address": "42 Wallaby Way, Sydney NSW 2000",
                "tenancy": "Joint Tenants"
            },
            "property": {
                "lot": "42",
                "plan": "DP123456",
                "address": "42 Wallaby Way, Sydney NSW 2000",
                "lga": "City of Sydney",
                "state": "NSW"
            },
            "encumbrances": [
                {
                    "type": "Mortgage",
                    "registered_number": "M123456",
                    "to": "Commonwealth Bank of Australia",
                    "amount": 850000,
                    "registered_date": "2023-01-15"
                }
            ],
            "abn": "12345678901",
            "ocr_confidence": 0.92
        },
        "contract": {
            "document_type": "contract_of_sale",
            "title_reference": "LP12345",
            "vendor": {
                "names": ["Bruce Wayne Pty Ltd"],
                "abn": "98765432109"
            },
            "purchaser": {
                "names": ["Clark Kent", "Lois Lane"],
                "address": "1 Daily Planet Way, Metropolis VIC 3000"
            },
            "property": {
                "lot": "1",
                "plan": "SP987654",
                "address": "1 Daily Planet Way, Metropolis VIC 3000",
                "lga": "City of Metropolis",
                "state": "VIC"
            },
            "encumbrances": [],
            "settlement_date": "2024-06-30",
            "ocr_confidence": 0.88
        }
    }

    def __init__(self):
        self.response_type = os.getenv("MOCK_RESPONSE_TYPE", "default")
        logger.info(f"Mock provider initialized with response_type={self.response_type}")

    async def extract(self, image_path: str, mime_type: str = "image/png") -> OCRResult:
        start = time.time()
        logger.info(f"Mock OCR processing: {image_path}")
        time.sleep(0.5)  # Simulate brief processing
        
        data = self.MOCK_RESPONSES.get(self.response_type, self.MOCK_RESPONSES["default"]).copy()
        elapsed = int((time.time() - start) * 1000)
        
        return OCRResult(
            raw_text="[MOCK] Property document extracted successfully",
            structured_data=data,
            confidence=data.get("ocr_confidence", 0.92),
            provider=self.name,
            pages_processed=1,
            processing_time_ms=elapsed
        )

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "provider": self.name,
            "mode": "mock",
            "response_type": self.response_type
        }

    @property
    def name(self) -> str:
        return "mock"

    @property
    def is_local(self) -> bool:
        return True


# Register with factory
factory.register("mock", MockOCRProvider)
