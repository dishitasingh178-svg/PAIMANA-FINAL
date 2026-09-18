import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database import engine, Base
import api.models.models

from api.routers import (
    projects,
    predictions,
    dashboard,
    analytics,
    alerts,
    assistant,
)

import ml_package.predictor as predictor

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):

    print("[STARTUP] Connecting to database and verifying schema...")

    Base.metadata.create_all(bind=engine)

    print("[STARTUP] Preloading ML model artifacts and pipelines into RAM...")

    if hasattr(predictor, "load_artifacts"):
        try:
            predictor.load_artifacts()
            print("[STARTUP] Models and pipelines loaded successfully.")
        except Exception as e:
            print(f"[STARTUP WARNING] Could not load ML artifacts: {e}")

    yield

    print("[SHUTDOWN] Application shutting down cleanly.")


app = FastAPI(
    title="PAIMANA AI Platform API",
    version="1.0.0",
    lifespan=lifespan,
)


# 1. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 2. API Routers
app.include_router(projects.router)
app.include_router(predictions.router)
app.include_router(dashboard.router)
app.include_router(analytics.router)
app.include_router(alerts.router)
app.include_router(assistant.router)


# 3. Static Assets
if (FRONTEND_DIR / "css").exists():
    app.mount(
        "/css",
        StaticFiles(directory=FRONTEND_DIR / "css"),
        name="css",
    )

if (FRONTEND_DIR / "js").exists():
    app.mount(
        "/js",
        StaticFiles(directory=FRONTEND_DIR / "js"),
        name="js",
    )


# 4. Frontend HTML Page Routes
@app.get("/", include_in_schema=False)
async def serve_index():

    index_file = FRONTEND_DIR / "index.html"

    if index_file.exists():
        return FileResponse(index_file)

    dashboard_file = FRONTEND_DIR / "dashboard.html"

    if dashboard_file.exists():
        return FileResponse(dashboard_file)

    return JSONResponse(
        {"message": "PAIMANA Backend Online"}
    )


@app.get("/{page_name}.html", include_in_schema=False)
async def serve_page(page_name: str):

    file_path = FRONTEND_DIR / f"{page_name}.html"

    if file_path.exists():
        return FileResponse(file_path)

    return FileResponse(
        FRONTEND_DIR / "dashboard.html"
    )


# 5. Health Check
@app.get("/health", tags=["Health"])
def health_check():

    return {
        "status": "online",
        "model_version": getattr(
            predictor,
            "manifest",
            {},
        ).get(
            "package_version",
            "1.0.0",
        ),
    }


# 6. Exception Handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):

    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": "VALIDATION_ERROR",
            "details": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(
    request: Request,
    exc: Exception,
):

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected server error occurred.",
        },
    )