"""
6-Stage Pipeline Orchestrator for South of Truth.
Stages: upload → rasterize → ocr → extract → validate → export
"""
import os
import uuid
import json
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Manages document processing through all pipeline stages."""
    
    def __init__(self, redis_client=None, db_session=None):
        self.redis = redis_client
        self.db = db_session
        self.upload_dir = os.getenv("UPLOAD_DIR", "./uploads")
        os.makedirs(self.upload_dir, exist_ok=True)
        
        # Import SQLite functions from upload_router
        try:
            from .upload_router import _save_session, _get_session
            self._store_save = _save_session
            self._store_get = _get_session
        except ImportError:
            # Fallback if functions not available
            self._store_save = lambda s: None
            self._store_get = lambda sid: None

    async def initialize_session(self, filename: str, file_path: str, session_id: str = None) -> Dict[str, Any]:
        """Stage 1: Initialize session after upload."""
        session = {
            "session_id": session_id or str(uuid.uuid4()),
            "stage": "uploaded",
            "filename": filename,
            "page_count": 0,
            "current_page": 0,
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": None,
            "ocr_provider": os.getenv("OCR_PROVIDER", "mock"),
            "processing_time_ms": 0,
            "results": {},
            "error": None,
            "extracted_data": {}
        }
        
        # Count PDF pages
        try:
            import fitz
            doc = fitz.open(file_path)
            session["page_count"] = len(doc)
            doc.close()
        except Exception:
            session["page_count"] = 1
        
        self._store_save(session)
        logger.info(f"Session initialized: {session['session_id']} for {filename}")
        return session

    async def rasterize(self, session: Dict[str, Any], file_path: str) -> Dict[str, Any]:
        """Stage 2: Convert PDF pages to images."""
        session["stage"] = "rasterizing"
        self._store_save(session)
        
        image_paths = []
        
        try:
            from pdf2image import convert_from_path
            images = convert_from_path(file_path, dpi=200, fmt="png", output_folder=self.upload_dir, paths_only=True)
            
            for idx, img_path in enumerate(images):
                new_path = os.path.join(self.upload_dir, f"{session['session_id']}_page_{idx}.png")
                os.rename(img_path, new_path)
                image_paths.append(new_path)
            
            session["current_page"] = len(image_paths)
            logger.info(f"Rasterized {len(image_paths)} pages")
            
        except Exception as e:
            logger.warning(f"pdf2image failed: {e}, trying PyMuPDF")
            try:
                import fitz
                doc = fitz.open(file_path)
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    pix = page.get_pixmap(dpi=200)
                    img_path = os.path.join(self.upload_dir, f"{session['session_id']}_page_{page_num}.png")
                    pix.save(img_path)
                    image_paths.append(img_path)
                doc.close()
                session["current_page"] = len(image_paths)
            except Exception as e2:
                logger.error(f"Rasterization failed: {e2}")
                session["stage"] = "failed"
                session["error"] = f"Rasterization failed: {e2}"
                self._store_save(session)
                raise
        
        self._store_save(session)
        return {"session": session, "image_paths": image_paths}

    async def process_ocr(self, session: Dict[str, Any], image_paths: list, document_type: str = None) -> Dict[str, Any]:
        """Stage 3: Run OCR on all pages with document type hint."""
        session["stage"] = "ocr_processing"
        self._store_save(session)
        
        from .ocr_interface import factory
        provider = factory.get_provider()
        
        all_results = []
        start_time = asyncio.get_event_loop().time()
        
        for idx, img_path in enumerate(image_paths):
            try:
                result = await provider.extract(img_path, mime_type="image/png", document_type=document_type)
                all_results.append({
                    "page": idx + 1,
                    "provider": result.provider,
                    "confidence": result.confidence,
                    "data": result.structured_data,
                    "processing_time_ms": result.processing_time_ms
                })
                session["current_page"] = idx + 1
                self._store_save(session)
                
            except Exception as e:
                logger.error(f"OCR failed on page {idx + 1}: {e}")
                all_results.append({"page": idx + 1, "error": str(e), "data": {}})
        
        elapsed = int((asyncio.get_event_loop().time() - start_time) * 1000)
        session["processing_time_ms"] = elapsed
        
        # Try to find a page that matched the document type hint
        if document_type:
            for r in all_results:
                if r.get("data", {}).get("document_type") == document_type:
                    merged_data = r.get("data", {})
                    logger.info(f"Used document_type match: {document_type}")
                    break
            else:
                # No match found — use highest confidence
                best = max(all_results, key=lambda x: x.get("confidence", 0) if "confidence" in x else 0)
                merged_data = best.get("data", {})
                logger.info(f"No document_type match for {document_type}, using best effort")
        else:
            best = max(all_results, key=lambda x: x.get("confidence", 0) if "confidence" in x else 0)
            merged_data = best.get("data", {})
        
        self._store_save(session)
        return {"session": session, "ocr_results": all_results, "merged_data": merged_data}

    async def extract(self, session: Dict[str, Any], merged_data: Dict[str, Any]) -> Dict[str, Any]:
        """Stage 4: Structure extraction."""
        session["stage"] = "extracting"
        session["extracted_data"] = merged_data
        self._store_save(session)
        return {"session": session, "extracted_data": merged_data}

    async def validate(self, session: Dict[str, Any], extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """Stage 5: Validate extracted data using type-specific validators."""
        session["stage"] = "validating"
        self._store_save(session)
        
        from .document_types import get_validator
        document_type = session.get("document_type", "unknown")
        validator = get_validator(document_type)
        
        # Run type-specific validation
        if callable(validator):
            type_errors = validator(extracted_data)
        else:
            type_errors = []
        
        # Generic validation only fires for unknown/unnamed types
        # or for document types that don't have their own validator
        from .validators import validate_extracted_data
        if document_type in ("unknown", None, ""):
            generic_errors = validate_extracted_data(extracted_data)
        else:
            # For typed documents, only run generic checks that don't overlap
            # with type-specific fields (skip registered_proprietor/property.address
            # for documents that use vendor_name/property_address instead)
            all_generic = validate_extracted_data(extracted_data)
            generic_errors = []
            # Map of generic field -> settlement_statement equivalent
            skip_fields = {
                "title_reference",  # not relevant for settlement statements
                "abn",              # not always present
                "registered_proprietor",  # use vendor_name instead
                "property.address",  # use property_address instead
            }
            for g in all_generic:
                # Only skip if the type-specific validator already handled that area
                if g["field"] in skip_fields and type_errors:
                    continue
                generic_errors.append(g)
        
        # Combine — deduplicate by field name
        seen_fields = {e["field"] for e in type_errors}
        combined = list(type_errors)
        for g in generic_errors:
            if g["field"] not in seen_fields:
                combined.append(g)
                seen_fields.add(g["field"])
        
        validation_results = combined
        
        errors = [v for v in validation_results if v["severity"] == "error"]
        warnings = [v for v in validation_results if v["severity"] == "warning"]
        
        session["results"] = {
            "validation": validation_results,
            "document_type": document_type,
            "summary": {
                "total_checks": len(validation_results),
                "errors": len(errors),
                "warnings": len(warnings),
                "passed": len(validation_results) - len(errors) - len(warnings),
                "is_valid": len(errors) == 0
            }
        }
        
        self._store_save(session)
        return {"session": session, "validation": validation_results}

    async def export(self, session: Dict[str, Any], extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """Stage 6: Finalize and store results."""
        session["stage"] = "completed"
        session["completed_at"] = datetime.utcnow().isoformat()
        session["results"]["extracted_data"] = extracted_data
        self._store_save(session)
        logger.info(f"Pipeline completed: {session['session_id']}")
        return {"session": session}

    async def run_full_pipeline(self, file_path: str, filename: str, session_id: str = None, document_type: str = None) -> Dict[str, Any]:
        """Run the complete 6-stage pipeline.
        
        Args:
            file_path: path to uploaded PDF
            filename: original filename
            session_id: optional session ID
            document_type: settlement_statement|form_2_1|contract_of_sale|certificate_of_title|section_32|trust_account_statement|final_letter
        """
        try:
            session = await self.initialize_session(filename, file_path, session_id=session_id)
            session["document_type"] = document_type or "unknown"
            self._store_save(session)
            raster = await self.rasterize(session, file_path)
            ocr = await self.process_ocr(raster["session"], raster["image_paths"], document_type=document_type)
            extract = await self.extract(ocr["session"], ocr["merged_data"])
            validate = await self.validate(extract["session"], extract["extracted_data"])
            final = await self.export(validate["session"], extract["extracted_data"])
            return final["session"]
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            if 'session' in locals():
                session["stage"] = "failed"
                session["error"] = str(e)
                self._store_save(session)
                return session
            raise
