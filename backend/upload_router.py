"""
Upload Router — /upload, /status, /results endpoints.
Uses SQLite for session persistence (survives server restarts).
"""
import os
import uuid
import json
import logging
import asyncio
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["upload"])


# ── SQLite Session Store ──
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "south_of_truth.db")


def _init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            stage TEXT,
            filename TEXT,
            page_count INTEGER,
            current_page INTEGER,
            ocr_provider TEXT,
            started_at TEXT,
            completed_at TEXT,
            processing_time_ms INTEGER,
            results TEXT,
            error TEXT,
            extracted_data TEXT
        )
    """)
    conn.commit()
    conn.close()


def _save_session(session: dict):
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO sessions
        (session_id, stage, filename, page_count, current_page, ocr_provider,
         started_at, completed_at, processing_time_ms, results, error, extracted_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session["session_id"],
        session.get("stage", "unknown"),
        session.get("filename", ""),
        session.get("page_count", 0),
        session.get("current_page", 0),
        session.get("ocr_provider", "mock"),
        session.get("started_at", datetime.utcnow().isoformat()),
        session.get("completed_at"),
        session.get("processing_time_ms", 0),
        json.dumps(session.get("results", {})),
        session.get("error"),
        json.dumps(session.get("extracted_data", {}))
    ))
    conn.commit()
    conn.close()


def _get_session(session_id: str) -> dict:
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        return None
    
    return {
        "session_id": row[0],
        "stage": row[1],
        "filename": row[2],
        "page_count": row[3],
        "current_page": row[4],
        "ocr_provider": row[5],
        "started_at": row[6],
        "completed_at": row[7],
        "processing_time_ms": row[8],
        "results": json.loads(row[9]) if row[9] else {},
        "error": row[10],
        "extracted_data": json.loads(row[11]) if row[11] else {}
    }


# ── Routes ──

@router.post("/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...)
):
    """Upload a property document and start processing."""
    if not file.content_type or "pdf" not in file.content_type:
        raise HTTPException(400, "Only PDF files are accepted")
    
    max_size = int(os.getenv("MAX_UPLOAD_SIZE", "52428800"))
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(413, f"File too large. Max: {max_size/1024/1024:.1f}MB")
    
    upload_dir = os.getenv("UPLOAD_DIR", "./uploads")
    os.makedirs(upload_dir, exist_ok=True)
    
    session_id = str(uuid.uuid4())
    file_path = os.path.join(upload_dir, f"{session_id}_{file.filename}")
    
    with open(file_path, "wb") as f:
        f.write(content)
    
    # Save initial session immediately
    session = {
        "session_id": session_id,
        "stage": "uploaded",
        "filename": file.filename,
        "page_count": 0,
        "current_page": 0,
        "ocr_provider": os.getenv("OCR_PROVIDER", "mock"),
        "started_at": datetime.utcnow().isoformat(),
        "results": {},
        "error": None,
        "extracted_data": {}
    }
    _save_session(session)
    
    # Start pipeline in background
    from .pipeline_orchestrator import PipelineOrchestrator
    redis = getattr(request.app.state, "redis", None)
    orchestrator = PipelineOrchestrator(redis_client=redis)
    
    asyncio.create_task(
        _run_pipeline_async(orchestrator, file_path, file.filename, session_id)
    )
    
    return JSONResponse({
        "session_id": session_id,
        "filename": file.filename,
        "status": "uploaded",
        "ocr_provider": os.getenv("OCR_PROVIDER", "mock")
    })


async def _run_pipeline_async(orchestrator, file_path, filename, session_id):
    """Run pipeline and persist results."""
    try:
        result = await orchestrator.run_full_pipeline(file_path, filename, session_id=session_id)
        _save_session(result)
        logger.info(f"Pipeline completed: {session_id}")
    except Exception as e:
        logger.error(f"Pipeline failed for {session_id}: {e}")
        session = _get_session(session_id) or {}
        session["stage"] = "failed"
        session["error"] = str(e)
        _save_session(session)


@router.get("/status/{session_id}")
async def get_status(session_id: str):
    """Get current pipeline status."""
    session = _get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session


@router.get("/results/{session_id}")
async def get_results(session_id: str):
    """Get final extracted results."""
    session = _get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    
    if session.get("stage") not in ("completed", "failed"):
        return JSONResponse({
            "session_id": session_id,
            "stage": session["stage"],
            "message": "Processing not complete. Check /status."
        }, status_code=202)
    
    return session


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    _init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
    
    upload_dir = os.getenv("UPLOAD_DIR", "./uploads")
    for f in os.listdir(upload_dir):
        if f.startswith(session_id):
            os.remove(os.path.join(upload_dir, f))
    
    return {"deleted": session_id}


@router.get("/stream/{session_id}")
async def status_stream(session_id: str):
    """SSE endpoint for real-time updates."""
    async def event_generator():
        last_stage = None
        for _ in range(300):
            session = _get_session(session_id) or {}
            current = session.get("stage", "unknown")
            
            if current != last_stage:
                last_stage = current
                yield f"data: {json.dumps({'stage': current, 'session_id': session_id})}\n\n"
            
            if current in ("completed", "failed"):
                yield f"data: {json.dumps({'stage': current, 'done': True})}\n\n"
                break
            
            await asyncio.sleep(1)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


@router.get("/providers")
async def list_providers():
    from .ocr_interface import factory
    return factory.list_providers()
