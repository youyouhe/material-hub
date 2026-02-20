"""MaterialHub API server entry point."""

import logging
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

app = FastAPI(title="MaterialHub", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    init_db()


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "MaterialHub"}


if __name__ == "__main__":
    import uvicorn
    import os

    port = int(os.getenv("PORT", "8201"))
    uvicorn.run(app, host="0.0.0.0", port=port)
