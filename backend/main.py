"""MaterialHub API server entry point."""

import os
import logging
import signal
import sys
import atexit
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database import init_db, get_session
from routers import documents, materials, companies, persons, auth
from auth import validate_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

logger = logging.getLogger("materialhub.main")

app = FastAPI(title="MaterialHub", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== 信号处理器：记录收到的信号 ==========
def signal_handler(signum, frame):
    """记录接收到的信号"""
    signal_name = signal.Signals(signum).name
    logger.warning(f"🚨 收到信号: {signal_name} (信号编号: {signum})")
    logger.warning(f"   帧信息: {frame}")
    # 不阻止默认处理，让uvicorn正常处理信号
    sys.exit(0)


def exit_handler():
    """程序退出时的处理"""
    logger.warning("🛑 程序正在退出...")
    logger.warning(f"   退出码即将设置")


# 注册信号处理器
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGHUP, signal_handler)

# 注册退出处理器
atexit.register(exit_handler)

logger.info("✅ 信号处理器已注册: SIGTERM, SIGINT, SIGHUP")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Authentication middleware to protect API endpoints."""
    # Exempt paths that don't require authentication
    exempt_paths = ["/api/auth/login", "/health", "/docs", "/openapi.json", "/redoc"]

    if request.url.path in exempt_paths:
        return await call_next(request)

    # Exempt static file serving (images)
    # Users must still be logged in to access the web app and see image URLs
    if request.url.path.startswith("/api/files/"):
        return await call_next(request)

    # Protect all /api/* paths except auth/login and files
    if request.url.path.startswith("/api/"):
        authorization = request.headers.get("authorization")

        if not authorization or not authorization.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"}
            )

        token = authorization.replace("Bearer ", "")

        with get_session() as db:
            user = validate_session(db, token)
            if not user:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or expired session"}
                )

    return await call_next(request)


app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(materials.router)
app.include_router(companies.router)
app.include_router(persons.router)


@app.on_event("startup")
def startup():
    """应用启动事件"""
    logger.info("🚀 MaterialHub 启动中...")
    logger.info(f"   进程ID: {os.getpid()}")
    logger.info(f"   父进程ID: {os.getppid()}")

    init_db()

    logger.info("✅ MaterialHub 启动完成")


@app.on_event("shutdown")
def shutdown():
    """应用关闭事件"""
    logger.warning("🛑 MaterialHub 收到关闭事件")
    logger.warning("   正在清理资源...")


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "MaterialHub"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8201"))

    logger.info("=" * 60)
    logger.info("MaterialHub Backend Server")
    logger.info("=" * 60)
    logger.info(f"进程ID: {os.getpid()}")
    logger.info(f"父进程ID: {os.getppid()}")
    logger.info(f"会话ID: {os.getsid(0)}")
    logger.info(f"进程组ID: {os.getpgrp()}")
    logger.info(f"监听端口: {port}")
    logger.info("=" * 60)

    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_level="info",
            access_log=True,
            # 显式配置超时参数
            timeout_keep_alive=5,
            timeout_graceful_shutdown=None,  # 不设置优雅关闭超时
            # 不限制最大请求数
            limit_max_requests=None,
        )
    except KeyboardInterrupt:
        logger.info("收到键盘中断 (Ctrl+C)")
    except Exception as e:
        logger.error(f"服务器异常退出: {e}", exc_info=True)
    finally:
        logger.warning("📊 服务器已停止")
