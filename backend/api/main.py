"""
Linux Management System - FastAPI Backend

セキュリティファースト設計の Linux 管理 WebUI バックエンド
"""

import logging
import time
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from ..core import settings
from .routes import approval, audit, auth, bandwidth, bootup, cron, dbmonitor, filesystem, firewall, hardware, logs, network, packages, postfix, processes, quotas, servers, services, ssh, stream, system, system_time, users, apache

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
# Nginx リバースプロキシ対応
# - X-Forwarded-For, X-Forwarded-Proto ヘッダーを信頼
# - 本番環境では TRUSTED_PROXY_IPS 環境変数で制限可能
# ===================================================================

_trusted_hosts = getattr(settings, "trusted_hosts", ["*"])
if _trusted_hosts and _trusted_hosts != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_trusted_hosts)

# ===================================================================
# ルーターの登録
# ===================================================================

app.include_router(auth.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(services.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(processes.router, prefix="/api")
app.include_router(approval.router, prefix="/api")
app.include_router(cron.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(network.router, prefix="/api")
app.include_router(servers.router, prefix="/api")
app.include_router(hardware.router, prefix="/api")
app.include_router(firewall.router, prefix="/api")
app.include_router(filesystem.router, prefix="/api")
app.include_router(packages.router, prefix="/api")
app.include_router(ssh.router, prefix="/api")
app.include_router(audit.router, prefix="/api")
app.include_router(bootup.router, prefix="/api")
app.include_router(system_time.router, prefix="/api")
app.include_router(quotas.router, prefix="/api")
app.include_router(dbmonitor.router, prefix="/api")
app.include_router(bandwidth.router, prefix="/api")
app.include_router(apache.router, prefix="/api")
app.include_router(postfix.router, prefix="/api")
app.include_router(stream.router, prefix="/api")

# ===================================================================
# 静的ファイル配信
# ===================================================================

# フロントエンドディレクトリ
frontend_dir = Path(__file__).parent.parent.parent / "frontend"

# CSS, JS ファイルの配信
app.mount("/css", StaticFiles(directory=str(frontend_dir / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(frontend_dir / "js")), name="js")
app.mount("/vendor", StaticFiles(directory=str(frontend_dir / "vendor")), name="vendor")

# dev, prod ディレクトリの配信
app.mount(
    "/dev", StaticFiles(directory=str(frontend_dir / "dev"), html=True), name="dev"
)
app.mount(
    "/prod", StaticFiles(directory=str(frontend_dir / "prod"), html=True), name="prod"
)

# ===================================================================
# ミドルウェア
# ===================================================================

# レート制限ストレージ（インメモリ）
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_login_attempts: dict[str, list[float]] = defaultdict(list)

RATE_LIMIT_PER_MINUTE = 300  # 1分あたりのAPIリクエスト上限（ダッシュボード等複数呼び出し対応）
LOGIN_MAX_ATTEMPTS = 5  # ログイン試行上限
LOGIN_LOCKOUT_SECONDS = 900  # ロック時間（15分）


def _clear_rate_limit_state() -> None:
    """テスト用: レート制限ストレージをクリア"""
    _rate_limit_store.clear()
    _login_attempts.clear()


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """セキュリティヘッダーを付与"""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self' data:; "
        "img-src 'self' data:; "
        "connect-src 'self'"
    )
    if settings.security.require_https:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


@app.middleware("http")
async def rate_limiter(request: Request, call_next):
    """APIレート制限（1分あたり60リクエスト）"""
    # 静的ファイルとヘルスチェックは除外
    path = request.url.path
    if path.startswith("/static") or path == "/api/health":
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window_start = now - 60.0

    # ログインエンドポイントのブルートフォース対策
    if path == "/api/auth/login" and request.method == "POST":
        attempts = _login_attempts[client_ip]
        # ウィンドウ外の試行を削除
        _login_attempts[client_ip] = [t for t in attempts if t > window_start]
        if len(_login_attempts[client_ip]) >= LOGIN_MAX_ATTEMPTS:
            # ロック期間チェック
            oldest_attempt = _login_attempts[client_ip][0]
            if now - oldest_attempt < LOGIN_LOCKOUT_SECONDS:
                logger.warning(f"Login rate limit exceeded: {client_ip}")
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "status": "error",
                        "message": "Too many login attempts. Please try again in 15 minutes.",
                    },
                    headers={"Retry-After": str(LOGIN_LOCKOUT_SECONDS)},
                )
        _login_attempts[client_ip].append(now)

    # 通常のAPIレート制限
    requests_in_window = _rate_limit_store[client_ip]
    _rate_limit_store[client_ip] = [t for t in requests_in_window if t > window_start]
    if len(_rate_limit_store[client_ip]) >= RATE_LIMIT_PER_MINUTE:
        logger.warning(f"Rate limit exceeded: {client_ip}")
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"status": "error", "message": "Rate limit exceeded. Please slow down."},
            headers={"Retry-After": "60"},
        )
    _rate_limit_store[client_ip].append(now)

    return await call_next(request)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    全リクエストをログ記録
    """
    logger.info(f"Request: {request.method} {request.url.path}")

    response = await call_next(request)

    logger.info(
        f"Response: {request.method} {request.url.path} - {response.status_code}"
    )

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


@app.get("/api/info")
async def api_info():
    """
    サーバー情報・アクセスURLを返すエンドポイント

    フロントエンドが動的にAPIのベースURLを取得するために使用
    """
    ip = settings.detected_ip
    http_port = settings.server.http_port
    https_port = settings.server.https_port
    is_prod = settings.environment == "production"
    # 本番ではHTTP/HTTPS両方、開発はHTTPのみ
    api_base = f"https://{ip}:{https_port}/api" if (is_prod and settings.server.ssl_enabled) else f"http://{ip}:{http_port}/api"
    return {
        "environment": settings.environment,
        "version": "0.10.0",
        "detected_ip": ip,
        "urls": {
            "http": f"http://{ip}:{http_port}",
            "https": f"https://{ip}:{https_port}",
            "api_http": f"http://{ip}:{http_port}/api",
            "api_https": f"https://{ip}:{https_port}/api",
            "api_base": api_base,
            "docs": f"http://{ip}:{http_port}/api/docs" if settings.features.api_docs_enabled else None,
        },
        "ports": {
            "http": http_port,
            "https": https_port,
        },
        "ssl_enabled": settings.server.ssl_enabled,
    }


@app.get("/", response_class=HTMLResponse)
async def root():
    """
    ルートエンドポイント - ログインページを表示
    """
    html_path = frontend_dir / "dev" / "index.html"
    if not html_path.exists():
        # HTMLが見つからない場合はAPIメタデータを返す
        return JSONResponse(
            {
                "message": "Linux Management System API",
                "environment": settings.environment,
                "version": "0.1.0",
                "docs_url": "/api/docs" if settings.features.api_docs_enabled else None,
            }
        )
    return HTMLResponse(content=html_path.read_text(), status_code=200)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """
    ダッシュボードページ
    """
    html_path = frontend_dir / "dev" / "dashboard.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard page not found")
    return HTMLResponse(content=html_path.read_text(), status_code=200)


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
    logger.info(f"Detected IP: {settings.detected_ip}")
    logger.info(f"HTTP Port: {settings.server.http_port}")
    logger.info(f"HTTPS Port: {settings.server.https_port}")
    logger.info(f"Access URL (HTTP):  http://{settings.detected_ip}:{settings.server.http_port}")
    logger.info(f"Access URL (HTTPS): https://{settings.detected_ip}:{settings.server.https_port}")
    logger.info(f"API Base URL: {settings.frontend.api_base_url}")
    logger.info(f"SSL Enabled: {settings.server.ssl_enabled}")
    logger.info(f"Debug Mode: {settings.features.debug_mode}")
    logger.info(f"API Docs: {settings.features.api_docs_enabled}")
    logger.info("=" * 60)

    # Production環境のセキュリティ検証
    await validate_production_config()

    # ログディレクトリの作成
    log_file = Path(settings.logging.file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # 監査ログディレクトリの作成
    audit_dir = log_file.parent / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    logger.info("✅ Backend started successfully")


async def validate_production_config():
    """
    Production環境のセキュリティ設定を検証

    Raises:
        RuntimeError: クリティカルなセキュリティ設定が不正な場合
    """
    if settings.environment == "production":
        # JWT秘密鍵の検証
        if settings.jwt_secret_key == "change-this-in-production":
            raise RuntimeError(
                "CRITICAL: JWT_SECRET not configured for production! "
                "Set SESSION_SECRET environment variable."
            )

        # HTTPS必須の検証
        if not settings.security.require_https:
            raise RuntimeError("CRITICAL: HTTPS must be required in production!")

        # デバッグモードの検証
        if settings.features.debug_mode:
            raise RuntimeError("CRITICAL: Debug mode must be disabled in production!")

        # API ドキュメントの警告
        if settings.features.api_docs_enabled:
            logger.warning(
                "WARNING: API docs are enabled in production. "
                "Consider disabling for security."
            )

        # CORS設定の検証
        if "*" in settings.cors_origins:
            raise RuntimeError(
                "CRITICAL: Wildcard CORS origin (*) is not allowed in production! "
                "Specify explicit domains in prod.json."
            )

        logger.info("✅ Production security configuration validated")


@app.on_event("shutdown")
async def shutdown_event():
    """
    アプリケーション終了時の処理
    """
    logger.info("Linux Management System Backend Shutting down...")
