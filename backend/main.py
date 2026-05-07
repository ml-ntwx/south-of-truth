"""
South of Truth — FastAPI Application Entry Point.
Orchestrates upload, OCR pipeline, validation, and export.
"""
import os
import logging
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# ── Import all providers to trigger factory registration ──
from .ocr_interface import get_ocr_provider
from . import gpt4o_provider
from . import glm_ocr_provider
from . import tesseract_provider
from . import mock_provider
from . import gemini_provider

# Import routers
from .upload_router import router as upload_router
from .results_router import router as results_router


# ── App State / Lifespan ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: connect Redis. Shutdown: cleanup."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_client = None
    
    try:
        import redis.asyncio as redis
        redis_client = redis.from_url(redis_url, decode_responses=True)
        await redis_client.ping()
        logger.info(f"Redis connected: {redis_url}")
    except Exception as e:
        logger.warning(f"Redis unavailable ({e}). Running with in-memory fallback.")
    
    app.state.redis = redis_client
    
    # Log available providers
    providers = get_ocr_provider.list_providers()
    logger.info(f"OCR Providers available: {providers['available']}")
    logger.info(f"Active OCR provider: {providers['active']}")
    
    yield
    
    # Shutdown
    if redis_client:
        await redis_client.close()
        logger.info("Redis disconnected")


# ── Create App ──
app = FastAPI(
    title="South of Truth — Property Document Verification API",
    description="Australian property document OCR, extraction, validation, and tokenization pipeline.",
    version="2.0.0",
    lifespan=lifespan
)

# ── CORS ──
cors_origins = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://localhost:5173,http://127.0.0.1:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Request-ID"]
)

# ── Request ID Middleware ──
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ── Include Routers ──
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

from fastapi.openapi.docs import get_swagger_ui_html

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="South of Truth",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
        swagger_favicon_url="",
        custom_css="""
        /* South of Truth — Glassmorphism Swagger Skin */
        body { background: #0c0c10 !important; }
        
        .swagger-ui { 
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important; 
            filter: invert(0) !important;
        }
        
        .swagger-ui .topbar { 
            background: linear-gradient(135deg, rgba(201,169,110,0.15), rgba(96,165,250,0.08)) !important; 
            border-bottom: 1px solid rgba(255,255,255,0.08) !important;
            backdrop-filter: blur(20px);
        }
        
        .swagger-ui .topbar .download-url-wrapper { display: none !important; }
        
        .swagger-ui .info { margin: 30px 0 !important; }
        .swagger-ui .info .title { 
            color: #c9a96e !important; 
            font-size: 34px !important; 
            font-weight: 600 !important;
        }
        .swagger-ui .info .title small { 
            background: rgba(201,169,110,0.15) !important; 
            border: 1px solid rgba(201,169,110,0.3) !important;
        }
        .swagger-ui .info .base-url { 
            color: #7a7a8a !important; 
            font-size: 15px !important; 
        }
        .swagger-ui .info .description { 
            color: #a0a0ac !important; 
            font-size: 17px !important; 
            line-height: 1.6 !important;
        }
        
        .swagger-ui .scheme-container { 
            background: rgba(255,255,255,0.03) !important; 
            border: 1px solid rgba(255,255,255,0.08) !important;
            border-radius: 12px !important;
            backdrop-filter: blur(20px);
            box-shadow: 0 8px 32px rgba(0,0,0,0.3) !important;
        }
        
        .swagger-ui .opblock { 
            background: rgba(255,255,255,0.03) !important; 
            border: 1px solid rgba(255,255,255,0.08) !important;
            border-radius: 12px !important;
            margin-bottom: 12px !important;
            backdrop-filter: blur(20px);
            box-shadow: 0 4px 16px rgba(0,0,0,0.2) !important;
        }
        
        .swagger-ui .opblock .opblock-summary { 
            padding: 16px 20px !important; 
            border-bottom: 1px solid rgba(255,255,255,0.06) !important;
        }
        
        .swagger-ui .opblock .opblock-summary-method { 
            font-weight: 700 !important; 
            font-size: 15px !important;
            border-radius: 6px !important;
            min-width: 80px !important;
            padding: 8px 0 !important;
        }
        
        .swagger-ui .opblock .opblock-summary-path { 
            font-size: 19px !important; 
            font-weight: 600 !important; 
            color: #f0f0f5 !important;
        }
        
        .swagger-ui .opblock .opblock-summary-description { 
            color: #7a7a8a !important; 
            font-size: 15px !important; 
        }
        
        .swagger-ui .opblock-tag { 
            font-size: 22px !important; 
            font-weight: 600 !important; 
            color: #f0f0f5 !important;
            border-bottom: 1px solid rgba(255,255,255,0.08) !important;
            padding: 24px 0 14px !important;
        }
        
        .swagger-ui .opblock-tag small { 
            color: #7a7a8a !important; 
            font-size: 15px !important; 
            font-weight: 400 !important;
        }
        
        .swagger-ui .opblock-body { background: transparent !important; }
        
        .swagger-ui .opblock-section-header { 
            background: rgba(255,255,255,0.02) !important; 
            border: none !important;
        }
        
        .swagger-ui .btn { 
            border-radius: 8px !important; 
            font-weight: 600 !important;
            transition: all 0.2s !important;
        }
        
        .swagger-ui .btn.execute { 
            background: linear-gradient(135deg, #c9a96e, #d4b87a) !important; 
            color: #1a1408 !important;
            border: none !important;
            box-shadow: 0 4px 16px rgba(201,169,110,0.3) !important;
        }
        
        .swagger-ui .btn.execute:hover { 
            box-shadow: 0 6px 20px rgba(201,169,110,0.4) !important; 
        }
        
        .swagger-ui .responses-inner, 
        .swagger-ui .table-container,
        .swagger-ui .opblock-description-wrapper,
        .swagger-ui .opblock-external-docs-wrapper,
        .swagger-ui .opblock-title_normal { 
            padding: 16px 20px !important; 
        }
        
        .swagger-ui table thead tr th { 
            color: #c9a96e !important; 
            font-size: 14px !important;
            text-transform: uppercase !important;
            letter-spacing: 0.8px !important;
            border-bottom: 1px solid rgba(255,255,255,0.08) !important;
            font-weight: 600 !important;
        }
        
        .swagger-ui table tbody tr td { 
            color: #a0a0ac !important; 
            font-size: 15px !important;
            border-bottom: 1px solid rgba(255,255,255,0.04) !important;
        }
        
        .swagger-ui .response-col_status { 
            font-weight: 700 !important; 
            color: #f0f0f5 !important;
        }
        
        .swagger-ui .response-col_links { display: none !important; }
        
        .swagger-ui .model { 
            font-size: 13px !important; 
            color: #a0a0ac !important;
        }
        
        .swagger-ui .prop-name { 
            color: #93c5fd !important; 
            font-weight: 600 !important;
        }
        
        .swagger-ui .prop-type { 
            color: #c9a96e !important; 
            font-weight: 500 !important;
        }
        
        .swagger-ui .highlight-code { 
            background: #12121a !important; 
            border-radius: 8px !important;
        }
        
        .swagger-ui .microlight { 
            font-size: 12px !important; 
            line-height: 1.7 !important;
        }
        
        .swagger-ui textarea, 
        .swagger-ui input[type=text],
        .swagger-ui select { 
            background: rgba(255,255,255,0.04) !important; 
            border: 1px solid rgba(255,255,255,0.08) !important;
            border-radius: 8px !important;
            color: #f0f0f5 !important;
            font-size: 13px !important;
            padding: 10px 14px !important;
        }
        
        .swagger-ui textarea:focus, 
        .swagger-ui input[type=text]:focus { 
            border-color: #c9a96e !important; 
            box-shadow: 0 0 0 3px rgba(201,169,110,0.1) !important;
        }
        
        .swagger-ui .parameter__name { 
            font-weight: 600 !important; 
            color: #f0f0f5 !important;
            font-size: 16px !important;
        }
        
        .swagger-ui .parameter__type { 
            color: #7a7a8a !important; 
            font-size: 14px !important;
        }
        
        .swagger-ui .parameters-col_description { 
            color: #a0a0ac !important; 
            font-size: 15px !important;
        }
        
        /* Scrollbar */
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }
        """
    )

app.include_router(upload_router)
app.include_router(results_router)


# ── Health Endpoints ──
@app.get("/health")
async def health():
    """Basic liveness check."""
    return {
        "status": "ok",
        "version": "2.0.0",
        "service": "south-of-truth-api"
    }


@app.get("/health/ready")
async def health_ready():
    """Deep readiness check — verifies Redis connectivity."""
    redis = getattr(app.state, "redis", None)
    redis_status = "connected" if redis else "unavailable"
    
    # Verify provider is loadable
    try:
        provider = get_ocr_provider.get_provider()
        provider_status = provider.name
    except Exception as e:
        provider_status = f"error: {e}"
    
    return {
        "status": "ready" if redis else "degraded",
        "checks": {
            "redis": redis_status,
            "ocr_provider": provider_status
        }
    }


@app.get("/health/live")
async def health_live():
    """Kubernetes-style liveness probe."""
    return {"status": "alive"}


# ── Global Exception Handler ──
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc),
            "request_id": getattr(request.state, "request_id", "unknown")
        }
    )


# ── Root ──
@app.get("/")
async def root():
    idx = os.path.join(static_dir, "index.html")
    if os.path.exists(idx):
        return FileResponse(idx)
    return {
        "service": "South of Truth API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
        "providers": "/providers",
        "upload": "POST /upload",
        "status": "GET /status/{session_id}",
        "results": "GET /results/{session_id}"
    }


logger.info("South of Truth API initialized")
