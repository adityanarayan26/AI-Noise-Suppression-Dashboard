import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from app.routers import health, metrics, audio, ws_audio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup diagnostics then yield to serve requests."""
    # ── Startup ──────────────────────────────────────────────────────────
    try:
        import df  # noqa: F401
        from df.enhance import init_df
        logger.info("══════════════════════════════════════════════════════")
        logger.info("  DeepFilterNet package:  ✓ INSTALLED")
        _model, _state, _ = init_df()
        logger.info("  DeepFilterNet model:    ✓ LOADED SUCCESSFULLY")
        del _model, _state
        logger.info("══════════════════════════════════════════════════════")
    except ImportError:
        logger.warning("══════════════════════════════════════════════════════")
        logger.warning("  DeepFilterNet package:  ✗ NOT INSTALLED")
        logger.warning("  Install with:  pip install deepfilternet")
        logger.warning("  Falling back to spectral subtraction.")
        logger.warning("══════════════════════════════════════════════════════")
    except Exception as exc:
        logger.error("══════════════════════════════════════════════════════")
        logger.error("  DeepFilterNet package:  ✓ installed")
        logger.error("  DeepFilterNet model:    ✗ FAILED TO LOAD")
        logger.error("  Error: %s", exc)
        logger.error("══════════════════════════════════════════════════════")

    yield  # Application is running
    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info("Server shutting down.")


app = FastAPI(
    title="AI Interview Audio Monitoring Backend",
    description="Backend API for the audio monitoring dashboard.",
    version="1.0.0",
    lifespan=lifespan,
)


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files from the uploads directory
os.makedirs("uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="uploads"), name="static")

# Include Routers
app.include_router(health.router)
app.include_router(metrics.router)
app.include_router(audio.router)
app.include_router(ws_audio.router)


@app.get("/api/deepfilter/status", tags=["Diagnostics"])
def deepfilter_status():
    """
    Check whether DeepFilterNet is installed and can initialise.
    This is a lightweight probe — it does NOT keep the model in memory.
    """
    status = {
        "package_installed": False,
        "model_loadable": False,
        "engine": "spectral_subtraction",
        "error": None,
    }
    try:
        import df  # noqa: F401
        status["package_installed"] = True
        from df.enhance import init_df
        _model, _state, _ = init_df()
        del _model, _state
        status["model_loadable"] = True
        status["engine"] = "deepfilternet"
    except ImportError as e:
        status["error"] = f"Package not installed: {e}"
    except Exception as e:
        status["error"] = f"Model load failed: {e}"
    return status
