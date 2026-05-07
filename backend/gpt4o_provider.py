"""
GPT-4o Vision OCR Provider — primary engine for South of Truth.
Handles PDF → image → base64 → GPT-4o Vision → structured JSON extraction.
"""
import os
import base64
import time
import logging
import json
from typing import Dict, Any
from openai import AsyncOpenAI
from .ocr_interface import BaseOCRProvider, OCRResult, factory

logger = logging.getLogger(__name__)

PROPERTY_EXTRACTION_PROMPT = """You are an expert Australian property document data extraction system.
Extract ALL fields from this property document image and return as JSON.

Required fields:
- document_type: (certificate_of_title | contract_of_sale | strata_title | section_32 | settlement_statement | transfer_of_land | mortgage | insurance_certificate | valuation_report | strata_by_laws)
- title_reference: string (Vol X Fol Y for VIC, LP number for VIC, DP/SP for NSW, Lot on Plan for QLD)
- registered_proprietor: {names: string[], address: string, tenancy_type: string}
- property: {lot: string, plan: string, address: string, lga: string, state: string (VIC|NSW|QLD|SA|WA|TAS|ACT|NT)}
- encumbrances: [{type: string, registered_number: string, to: string, amount: number|null, registered_date: string|null}]
- abn: string|null (11 digits if present)
- ocr_confidence: number 0-1 (your confidence in this extraction)

Rules:
1. Title reference must match the state format
2. ABN must be exactly 11 digits if present, null otherwise
3. All dates in ISO 8601 format (YYYY-MM-DD)
4. Use null (not empty string) for fields not visible
5. Return ONLY valid JSON, no markdown, no explanation
6. Be precise with names and addresses — exact spelling as shown
"""


class GPT4OProvider(BaseOCRProvider):
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        if not api_key or "your-key" in api_key:
            logger.error("OPENAI_API_KEY not set. Set it in .env or environment.")
            raise ValueError("OPENAI_API_KEY is required for GPT-4o provider")
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = os.getenv("GPT4O_MODEL", "gpt-4o")
        logger.info(f"GPT-4o provider initialized with model={self.model}")

    def _encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        # GPT-4o pricing: $2.50 / 1M input, $10.00 / 1M output
        input_cost = (input_tokens / 1_000_000) * 2.50
        output_cost = (output_tokens / 1_000_000) * 10.00
        return input_cost + output_cost

    def _estimate_confidence(self, data: Dict[str, Any]) -> float:
        """Estimate confidence from field completeness."""
        required = ["document_type", "title_reference", "registered_proprietor", "property"]
        score = 0
        for field in required:
            if data.get(field):
                score += 0.25
        
        # Bonus for high-detail fields
        if data.get("encumbrances") is not None:
            score += 0.15
        
        proprietor = data.get("registered_proprietor", {})
        if proprietor.get("names"):
            score += 0.15
        
        return min(score, 1.0)

    async def extract(self, image_path: str, mime_type: str = "image/png") -> OCRResult:
        start = time.time()
        logger.info(f"GPT-4o processing: {image_path}")
        
        try:
            base64_image = self._encode_image(image_path)
            
            # Determine image detail based on file size
            file_size = os.path.getsize(image_path)
            detail = "high" if file_size > 1_000_000 else "low"
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": PROPERTY_EXTRACTION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}",
                                    "detail": detail
                                }
                            }
                        ]
                    }
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=4096
            )
            
            raw_text = response.choices[0].message.content
            data = json.loads(raw_text)
            
            # Ensure ocr_confidence exists
            if "ocr_confidence" not in data:
                data["ocr_confidence"] = self._estimate_confidence(data)
            
            usage = response.usage
            cost = self._estimate_cost(usage.prompt_tokens, usage.completion_tokens)
            elapsed = int((time.time() - start) * 1000)
            
            logger.info(f"GPT-4o completed in {elapsed}ms. Tokens: {usage.total_tokens}, Cost: ${cost:.6f}")
            
            return OCRResult(
                raw_text=raw_text,
                structured_data=data,
                confidence=data.get("ocr_confidence", 0.85),
                provider=self.name,
                pages_processed=1,
                processing_time_ms=elapsed
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"GPT-4o returned invalid JSON: {e}")
            raise
        except Exception as e:
            logger.error(f"GPT-4o processing failed: {e}")
            raise

    def health_check(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "provider": self.name,
            "model": self.model,
            "api_url": self.client.base_url
        }

    @property
    def name(self) -> str:
        return "gpt4o"

    @property
    def is_local(self) -> bool:
        return False


factory.register("gpt4o", GPT4OProvider)
