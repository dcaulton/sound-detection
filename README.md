# sound-detection

Bioacoustics monitoring service for native yard restoration. Detects birds, bats, and noisy insects from outdoor microphone recordings using BirdNET.

## Architecture Notes

This project uses **FastAPI (async)** at the API layer with `BackgroundTasks` for audio analysis.

The database repository layer is intentionally written to support **both sync and async sessions**. This compromise was made so we could have stable, simple tests using synchronous SQLAlchemy + testcontainers (matching the pattern used in the sibling project `birdseye`). 

While this adds some complexity and type ignores, it significantly improved test reliability and reduced divergence between local development and CI. We may revisit a cleaner async-only data layer later once the core domain is more mature.

## Project Structure
src/sound_detection/
├── api/
│   └── v1/
│       └── routers/
│           ├── detections.py
│           ├── microphones.py
│           └── sites.py
├── db/
│   ├── models.py
│   ├── repositories.py
│   └── session.py
├── ml/
│   └── inference.py
├── schemas/
├── core/
│   └── config.py
└── main.py

## Quick Start (Development)

git clone https://github.com/dcaulton/sound-detection.git
cd sound-detection
make install          # ← this installs Torch correctly for your GPU
make dev              # starts FastAPI at http://localhost:8000



## Key Endpoints

- `POST /v1/detections/analyze` — Upload audio → background analysis
- `GET /v1/detections/recordings` — List recordings
- CRUD for Sites and Microphones under `/v1/sites` and `/v1/microphones`
- Analytical queries (e.g. species counts over time)

## Running Tests
Tests use a fresh Postgres container via testcontainers and run with synchronous SQLAlchemy sessions for reliability.


