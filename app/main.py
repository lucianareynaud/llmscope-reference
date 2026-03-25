"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from llmscope import setup_otel, shutdown_otel
from app.api import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager with OTEL setup/shutdown."""
    # Startup
    setup_otel()
    FastAPIInstrumentor.instrument_app(app)
    yield
    # Shutdown
    shutdown_otel()


app = FastAPI(
    title="llmscope-reference",
    description="Reference workload for runtime economics and operational governance",
    version="0.1.0",
    lifespan=lifespan,
)

# Include API router
app.include_router(router)


@app.get("/healthz")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
