import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .database import Base, engine
from .routers import auth, patient, games, caregiver, doctor, authorization, family, sync, consent, demo, ledger

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Sukoon API",
    description="AI-powered cognitive assistance, memory-care and caregiver-support platform "
                "for elderly dementia/cognitive-impairment patients in NER. "
                "Sukoon does not diagnose or treat dementia — it is a support and monitoring tool.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # relaxed for prototype/demo; restrict to known origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(patient.router)
app.include_router(games.router)
app.include_router(caregiver.router)
app.include_router(doctor.router)
app.include_router(authorization.router)
app.include_router(family.router)
app.include_router(sync.router)
app.include_router(consent.router)
app.include_router(demo.router)
app.include_router(ledger.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "sukoon-api"}


# ---------------------------------------------------------------------------
# Serve the static frontend from the same process (simplest deploy story for
# a hackathon demo — one process, one port, works great on Replit too).
# ---------------------------------------------------------------------------
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "static")

if os.path.isdir(STATIC_DIR):
    app.mount("/app", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    @app.get("/")
    def root():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    @app.get("/favicon.ico")
    def favicon():
        fav = os.path.join(STATIC_DIR, "assets", "favicon.ico")
        if os.path.exists(fav):
            return FileResponse(fav)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
