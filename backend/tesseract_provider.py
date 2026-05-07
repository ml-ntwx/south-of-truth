"""
Tesseract OCR Provider — CPU-based, offline fallback.
Lower accuracy but works without internet or API keys.
"""
import os
import re
import time
import logging
from typing import Dict, Any
from PIL import Image
import pytesseract
from .ocr_interface import BaseOCRProvider, OCRResult, factory
from .validators import detect_document_type

logger = logging.getLogger(__name__)


class TesseractProvider(BaseOCRProvider):
    """Tesseract CPU OCR with AU property field heuristics."""

    def __init__(self):
        self.lang = os.getenv("TESSERACT_LANG", "eng")
        self.cmd = os.getenv("TESSERACT_CMD", None)
        if self.cmd:
            pytesseract.pytesseract.tesseract_cmd = self.cmd
        logger.info(f"Tesseract provider initialized (lang={self.lang})")

    def _extract_title_reference(self, text: str) -> str:
        """Extract title reference using regex patterns."""
        patterns = [
            r"(?:Vol(?:ume)?\s+\d+\s+Fol(?:io)?\s+\d+)",
            r"(?:LP\s*\d+)",
            r"(?:DP\s*\d+)",
            r"(?:SP\s*\d+)",
            r"(?:CT\s*\d+)",
            r"(?:Lot\s+\d+\s+on\s+(?:SP|RP|CP)\s*\d+)",
            r"(?:\d+\s*/\s*\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return match.group(0).strip()
        return ""

    def _extract_abn(self, text: str) -> str:
        """Extract 11-digit ABN."""
        match = re.search(r"\b\d{2}\s*\d{3}\s*\d{3}\s*\d{3}\b", text)
        if match:
            return re.sub(r"\s+", "", match.group(0))
        return ""

    def _extract_names(self, text: str) -> list:
        """Heuristic name extraction from proprietor sections."""
        names = []
        # Look for patterns like "Jane Smith" or "J. E. Smith"
        name_pattern = re.compile(r"([A-Z][a-z]+(?:\s+[A-Z]\.?)*\s+[A-Z][a-z]+)")
        for match in name_pattern.finditer(text):
            name = match.group(1).strip()
            if len(name) > 3 and name not in names:
                names.append(name)
        return names[:5]  # Limit to 5 names

    def _extract_address(self, text: str) -> str:
        """Extract Australian address patterns."""
        # Look for street number + street name + suburb + state + postcode
        pattern = re.compile(
            r"(\d+[a-zA-Z]?\s+[A-Za-z\s]+(?:Street|St|Road|Rd|Avenue|Ave|Drive|Dr|Lane|Ln|Place|Pl|Court|Ct|Way|Highway|Hwy)\s*,?\s*[A-Za-z\s]+(?:NSW|VIC|QLD|SA|WA|TAS|ACT|NT)\s*\d{4})",
            re.I
        )
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
        return ""

    async def extract(self, image_path: str, mime_type: str = "image/png") -> OCRResult:
        start = time.time()
        logger.info(f"Tesseract processing: {image_path}")

        try:
            img = Image.open(image_path)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            # Run OCR
            raw_text = pytesseract.image_to_string(img, lang=self.lang)
            
            # Extract fields using heuristics
            doc_type = detect_document_type(raw_text)
            title_ref = self._extract_title_reference(raw_text)
            abn = self._extract_abn(raw_text)
            names = self._extract_names(raw_text)
            address = self._extract_address(raw_text)
            
            # Build structured data
            data = {
                "document_type": doc_type,
                "title_reference": title_ref,
                "registered_proprietor": {
                    "names": names,
                    "address": address,
                    "tenancy": "Unknown"
                },
                "property": {
                    "lot": "",
                    "plan": "",
                    "address": address,
                    "lga": "",
                    "state": ""
                },
                "encumbrances": [],
                "abn": abn if abn else None,
                "ocr_confidence": 0.55  # Tesseract baseline confidence
            }

            elapsed = int((time.time() - start) * 1000)
            logger.info(f"Tesseract completed in {elapsed}ms. Text length: {len(raw_text)}")

            return OCRResult(
                raw_text=raw_text,
                structured_data=data,
                confidence=0.55,
                provider=self.name,
                pages_processed=1,
                processing_time_ms=elapsed
            )

        except Exception as e:
            logger.error(f"Tesseract processing failed: {e}")
            raise

    def health_check(self) -> Dict[str, Any]:
        try:
            # Quick test to verify tesseract is installed
            pytesseract.get_tesseract_version()
            return {"status": "healthy", "provider": self.name, "version": str(pytesseract.get_tesseract_version())}
        except Exception as e:
            return {"status": "unhealthy", "provider": self.name, "error": str(e)}

    @property
    def name(self) -> str:
        return "tesseract"

    @property
    def is_local(self) -> bool:
        return True


factory.register("tesseract", TesseractProvider)
