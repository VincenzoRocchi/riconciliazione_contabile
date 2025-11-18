import asyncio
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.routers import health, processing, test_ocr, home, results, debug_pdf, documentation
from app.routers.processing import cleanup_old_jobs
from app.core.config import settings

# Configura logging basato su settings
log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    force=True  # Forza la riconfigurazione anche se già configurato
)

# Imposta il livello per tutti i logger dell'applicazione
logger = logging.getLogger(__name__)
logger.setLevel(log_level)

# Imposta anche per uvicorn e altri logger comuni
logging.getLogger("uvicorn").setLevel(log_level)
logging.getLogger("uvicorn.access").setLevel(log_level)
logging.getLogger("uvicorn.error").setLevel(log_level)

logger.info(f"Logging configured with level: {settings.log_level}")

app = FastAPI(
    title="Riconciliazione Contabile",
    description="Sistema locale per riconciliazione tra estratto conto bancario e scheda contabile. Parsing PDF nativi con pdfplumber, matching deterministico.",
    version="1.0.0"
)

# CORS middleware per sviluppo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In produzione limitare agli origin specifici
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
# Include routers (l'ordine è importante - home deve essere prima per catturare "/")
app.include_router(home.router, tags=["Home"])
app.include_router(results.router, tags=["Results"])
app.include_router(health.router, tags=["Health"])
app.include_router(processing.router, prefix="/api/v1", tags=["Processing"])
app.include_router(test_ocr.router, tags=["Test OCR"])
app.include_router(debug_pdf.router, tags=["Debug"])  # Temporaneo per analisi PDF
app.include_router(documentation.router, tags=["Documentation"])


async def _daily_cleanup_loop():
    """Avvia una pulizia dei job alla mezzanotte di ogni giorno."""
    while True:
        now = datetime.now()
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        sleep_seconds = max(1, int((next_midnight - now).total_seconds()))
        await asyncio.sleep(sleep_seconds)
        removed = cleanup_old_jobs()
        logger.info(f"Daily cleanup executed, removed {removed} job(s)")


@app.on_event("startup")
async def _startup_events():
    # Esegue subito una pulizia per sicurezza e programma il job giornaliero
    cleanup_old_jobs()
    app.state.cleanup_task = asyncio.create_task(_daily_cleanup_loop())


@app.on_event("shutdown")
async def _shutdown_events():
    task = getattr(app.state, "cleanup_task", None)
    if task:
        task.cancel()

