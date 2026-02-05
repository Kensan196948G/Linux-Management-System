"""
Linux Management System - FastAPI Backend

セキュリティファースト設計の Linux 管理 WebUI バックエンド
"""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ..core import settings
from .routes import auth, logs, services, system

# ログ設定
logging.basicConfig(
    level=getattr(logging, settings.logging.level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

# ===================================================================
# FastAPI アプリケーション初期化
# ===================================================================

app = FastAPI(
    title="Linux Management System API",
    description="Secure Linux Management WebUI with sudo allowlist control",
    version="0.1.0",
    docs_url="/api/docs" if settings.features.api_docs_enabled else None,
    redoc_url="/api/redoc" if settings.features.api_docs_enabled else None,
)

# ===================================================================
# CORS 設定
# ===================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===================================================================
# ルーターの登録
# ===================================================================

app.include_router(auth.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(services.router, prefix="/api")
app.include_router(logs.router, prefix="/api")

# ===================================================================
# 静的ファイル配信
# ===================================================================

# フロントエンドディレクトリ
frontend_dir = Path(__file__).parent.parent.parent / "frontend"

# CSS, JS ファイルの配信
app.mount("/css", StaticFiles(directory=str(frontend_dir / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(frontend_dir / "js")), name="js")

# dev, prod ディレクトリの配信
app.mount("/dev", StaticFiles(directory=str(frontend_dir / "dev"), html=True), name="dev")
app.mount("/prod", StaticFiles(directory=str(frontend_dir / "prod"), html=True), name="prod")

# ===================================================================
# ミドルウェア
# ===================================================================


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    全リクエストをログ記録
    """
    logger.info(f"Request: {request.method} {request.url.path}")

    response = await call_next(request)

    logger.info(f"Response: {request.method} {request.url.path} - {response.status_code}")

    return response


# ===================================================================
# エラーハンドラ
# ===================================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP 例外ハンドラ"""
    logger.warning(f"HTTP Exception: {exc.status_code} - {exc.detail}")

    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": exc.detail},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """一般例外ハンドラ"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "message": "Internal server error",
            "detail": str(exc) if settings.features.debug_mode else None,
        },
    )


# ===================================================================
# ヘルスチェック
# ===================================================================


@app.get("/health")
async def health_check():
    """
    ヘルスチェックエンドポイント

    監視システムやロードバランサーから使用
    """
    return {
        "status": "healthy",
        "environment": settings.environment,
        "version": "0.1.0",
    }


@app.get("/")
async def root():
    """
    ルートエンドポイント
    """
    return {
        "message": "Linux Management System API",
        "environment": settings.environment,
        "version": "0.1.0",
        "docs_url": "/api/docs" if settings.features.api_docs_enabled else None,
    }


# ===================================================================
# 起動時処理
# ===================================================================


@app.on_event("startup")
async def startup_event():
    """
    アプリケーション起動時の処理
    """
    logger.info("=" * 60)
    logger.info("Linux Management System Backend Starting...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"HTTP Port: {settings.server.http_port}")
    logger.info(f"HTTPS Port: {settings.server.https_port}")
    logger.info(f"SSL Enabled: {settings.server.ssl_enabled}")
    logger.info(f"Debug Mode: {settings.features.debug_mode}")
    logger.info(f"API Docs: {settings.features.api_docs_enabled}")
    logger.info("=" * 60)

    # ログディレクトリの作成
    log_file = Path(settings.logging.file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # 監査ログディレクトリの作成
    audit_dir = log_file.parent / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    logger.info("✅ Backend started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """
    アプリケーション終了時の処理
    """
    logger.info("Linux Management System Backend Shutting down...")
