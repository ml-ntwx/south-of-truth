"""
GLM-OCR Provider — self-hosted via vLLM (Jetson Orin or RunPod).
OpenAI-compatible API format. Use when OCR_PROVIDER=glm_ocr.
"""
import os
import base64
import time
import logging
import json
from typing import Dict, Any
import aiohttp
from .ocr_interface import BaseOCRProvider, OCRResult, factory

logger = logging.getLogger(__name__)

GLM4_PROPERTY_PROMPT = """Extract Australian property document data from this image and return JSON.
Fields: document_type, title_reference, registered_proprietor(names, address, tenancy_type), 
property(lot, plan, address, lga, state), encumbrances(type, registered_number, to, amount, registered_date), 
abn, ocr_confidence. Use null for missing fields. Return ONLY JSON."""


class GLMOCRProvider(BaseOCRProvider):
    def __init__(self):
        self.base_url = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
        self.model = os.getenv("VLLM_MODEL", "zai-org/GLM-OCR")
        self.api_key = os.getenv("VLLM_API_KEY", "not-needed")
        logger.info(f"GLM-OCR provider initialized. URL={self.base_url}, model={self.model}")

    def _encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    async def extract(self, image_path: str, mime_type: str = "image/png") -> OCRResult:
        start = time.time()
        logger.info(f"GLM-OCR processing: {image_path}")

        try:
            base64_image = self._encode_image(image_path)
            
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": GLM4_PROPERTY_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}",
                                    "detail": "auto"
                                }
                            }
                        ]
                    }
                ],
                "temperature": 0.0,
                "max_tokens": 4096,
                "response_format": {"type": "json_object"}
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    if response.status != 200:
                        text = await response.text()
                        raise RuntimeError(f"GLM-OCR API error {response.status}: {text}")
                    
                    result = await response.json()
            
            raw_text = result["choices"][0]["message"]["content"]
            data = json.loads(raw_text)
            
            # Ensure confidence field
            if "ocr_confidence" not in data:
                data["ocr_confidence"] = 0.80
            
            usage = result.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            
            elapsed = int((time.time() - start) * 1000)
            logger.info(f"GLM-OCR completed in {elapsed}ms. Tokens: {prompt_tokens + completion_tokens}")

            return OCRResult(
                raw_text=raw_text,
                structured_data=data,
                confidence=data.get("ocr_confidence", 0.80),
                provider=self.name,
                pages_processed=1,
                processing_time_ms=elapsed
            )

        except json.JSONDecodeError as e:
            logger.error(f"GLM-OCR returned invalid JSON: {e}")
            raise
        except Exception as e:
            logger.error(f"GLM-OCR processing failed: {e}")
            raise

    def health_check(self) -> Dict[str, Any]:
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            
            async def _check():
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{self.base_url}/models",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        if response.status == 200:
                            return {"status": "healthy", "provider": self.name, "url": self.base_url}
                        return {"status": "unhealthy", "provider": self.name, "http_status": response.status}
            
            return loop.run_until_complete(_check())
        except Exception as e:
            return {"status": "unhealthy", "provider": self.name, "error": str(e)}

    @property
    def name(self) -> str:
        return "glm_ocr"

    @property
    def is_local(self) -> bool:
        return True


factory.register("glm_ocr", GLMOCRProvider)
