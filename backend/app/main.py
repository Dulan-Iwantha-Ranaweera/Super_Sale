"""Super Sale — Supermarket Store Management System API."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError, PyMongoError

from .config import get_settings
from .database import close_mongo_connection, connect_to_mongo
from .routers import auth, customers, dashboard, ipf, products, reports, returns, sales, store

logger = logging.getLogger("supersale")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await connect_to_mongo()
    logger.info("Connected to MongoDB database %r and ensured indexes", settings.db_name)
    yield
    await close_mongo_connection()
    logger.info("MongoDB connection closed")


app = FastAPI(
    title="Super Sale API",
    description="Supermarket store management: inventory, POS, CRM and analytics.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Turn Pydantic errors into a single readable sentence for the UI."""
    messages = []
    for error in exc.errors():
        location = " -> ".join(str(part) for part in error.get("loc", []) if part != "body")
        messages.append(f"{location or 'payload'}: {error.get('msg', 'invalid value')}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "; ".join(messages) or "Invalid request payload"},
    )


@app.exception_handler(DuplicateKeyError)
async def duplicate_key_handler(request: Request, exc: DuplicateKeyError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "That value already exists and must be unique"},
    )


@app.exception_handler(PyMongoError)
async def mongo_error_handler(request: Request, exc: PyMongoError) -> JSONResponse:
    """Database faults become a clean 503 instead of an unhandled traceback."""
    logger.exception("Database error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "The database is unavailable. Please try again."},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Something went wrong while processing the request"},
    )


app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(products.router)
app.include_router(returns.router)
app.include_router(sales.router)
app.include_router(customers.router)
app.include_router(reports.router)
app.include_router(ipf.router)
app.include_router(store.router)


@app.get("/api/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "super-sale-api"}
