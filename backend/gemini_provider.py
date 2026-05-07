"""
Gemini Flash OCR Provider — google.genai SDK (new package).
Handles PDF → image → Gemini → structured JSON extraction.
Replaces deprecated google.generativeai package.
"""
import os
import json
import time
import logging
from typing import Dict, Any

from google import genai
from google.genai.types import Part

from .ocr_interface import BaseOCRProvider, OCRResult, factory

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are an expert Australian property document data extraction system.

Extract ALL visible fields and return them as JSON. Use null for missing fields.

Required JSON fields:
{
  "document_type": "certificate_of_title | contract_of_sale | strata_title | section_32 | settlement_statement | transfer_of_land | mortgage | other",
  "title_reference": "title ref string or null",
  "registered_proprietor": {
    "names": ["Name One", "Name Two"],
    "address": "address string or null",
    "tenancy_type": "joint_tenants | tenants_in_common | sole | null"
  },
  "property": {
    "lot": "lot or null",
    "plan": "plan or null",
    "address": "full address or null",
    "lga": "local government area or null",
    "state": "NSW|VIC|QLD|SA|WA|TAS|ACT|NT or null"
  },
  "encumbrances": [
    {"type": "Mortgage|Caveat|Easement|Covenant|Lease", "registered_number": "string", "to": "string", "amount": number|null, "registered_date": "YYYY-MM-DD|null"}
  ],
  "abn": "11-digit ABN or null",
  "ocr_confidence": 0.0-1.0
}

Rules:
1. Return ONLY valid JSON. No markdown fences, no explanation, no text before or after.
2. State must be Australian state abbreviation (NSW, VIC, QLD, SA, WA, TAS, ACT, NT).
3. ABN is exactly 11 digits if present, null otherwise.
4. ocr_confidence: your estimated confidence 0.0-1.0 based on how clearly you can read this document.
5. Be precise with names and addresses as they appear in the document."""


class GeminiProvider(BaseOCRProvider):
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")

        self.client = genai.Client(api_key=self.api_key)

        # Try env var first, then fall back to known-stable models
        env_model = os.getenv("GEMINI_MODEL", "")
        self.model_names = [env_model] if env_model else []
        self.model_names += [
            "gemini-2.0-flash",
            "gemini-1.5-flash",
        ]
        # Deduplicate while preserving order
        seen = set()
        self.model_names = [x for x in self.model_names if not (x in seen or seen.add(x))]

        logger.info(f"Gemini provider initialized. Models: {self.model_names}")

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "provider": self.name,
            "models": self.model_names,
            "package": "google.genai"
        }

    async def extract(self, image_path: str, mime_type: str = "image/png", document_type: str = None) -> OCRResult:
        start = time.time()

        from .document_types import get_prompt
        base_prompt = get_prompt(document_type) if document_type else EXTRACTION_PROMPT

        try:
            with open(image_path, "rb") as f:
                img_bytes = f.read()
            logger.info(f"Gemini processing: {image_path} ({len(img_bytes)//1024} KB)")
        except Exception as e:
            raise RuntimeError(f"Failed to read image {image_path}: {e}")

        raw_text = ""
        last_error = None

        # Try each model in sequence
        for model_name in self.model_names:
            try:
                # Build contents as a list: prompt string + image Part
                contents = [
                    base_prompt,
                    Part.from_bytes(data=img_bytes, mime_type=mime_type),
                ]

                # Generate with JSON mode via config
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config={
                        "temperature": 0.0,
                        "response_mime_type": "application/json",
                    }
                )

                raw_text = response.text or ""

                # Clean any accidental markdown fences
                cleaned = raw_text.strip()
                for fence in ("```json", "```json\n", "```", "```\n"):
                    if cleaned.startswith(fence):
                        cleaned = cleaned[len(fence):]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

                if not cleaned:
                    logger.warning(f"Model {model_name} returned empty response")
                    continue

                # Parse JSON
                try:
                    data = json.loads(cleaned)
                    logger.info(f"Model {model_name} succeeded, parsed JSON")
                    break
                except json.JSONDecodeError as e:
                    logger.warning(f"Model {model_name} returned invalid JSON: {e}")
                    last_error = e
                    continue

            except Exception as e:
                logger.warning(f"Model {model_name} failed: {e}")
                last_error = e
                continue

        else:
            # All models failed
            raise RuntimeError(
                f"All Gemini models failed. Last error: {last_error}. "
                f"Check: API key is valid, quota not exhausted, network connectivity."
            )

        # Ensure required fields
        if "ocr_confidence" not in data or data.get("ocr_confidence") is None:
            data["ocr_confidence"] = 0.7

        elapsed = int((time.time() - start) * 1000)
        logger.info(f"Gemini done in {elapsed}ms. Confidence: {data.get('ocr_confidence')}")

        return OCRResult(
            raw_text=raw_text,
            structured_data=data,
            confidence=data.get("ocr_confidence", 0.7),
            provider=self.name,
            pages_processed=1,
            processing_time_ms=elapsed,
        )

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def is_local(self) -> bool:
        return False


factory.register("gemini", GeminiProvider)