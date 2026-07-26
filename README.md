# Sound Detection

A production-leaning, local-first bioacoustics platform for continuous wildlife monitoring using AudioMoth recorders, custom ML models, and rich ecological reporting.

## What It Does

Sound Detection ingests audio from edge recorders (primarily AudioMoth), runs them through a multi-stage ML pipeline, and turns raw detections into meaningful ecological insights.

Recent work added **BiomeSummaryService** — an automated narrative generator that produces long-form, human-readable reports about bird activity over a time window, complete with species enrichment via RAG and LangChain.

## Key Features

- **Audio ingestion & detection pipeline** — Handles continuous recordings from multiple AudioMoth devices.
- **Species knowledge graph** — Neo4j-backed knowledge base with structured data (range, habitat, diet, interesting facts) + Wikipedia RAG chunks.
- **Sliding-scale filtering** — Intelligent filtering of common vs. notable species based on detection volume.
- **LangChain-powered enrichment** — Per-species contextual summaries + full narrative report generation.
- **Local-first architecture** — Designed to run on-prem or at the edge with minimal cloud dependency.
- **FastAPI + async SQLAlchemy** — Modern, type-safe backend.
- **Kubernetes-ready** — Runs on MicroK8s with Traefik, Postgres, Neo4j, and MLflow.

## Tech Stack

| Layer              | Technology                              |
|--------------------|-----------------------------------------|
| Backend            | FastAPI, SQLAlchemy 2.0 (async), Pydantic |
| Database           | PostgreSQL + Neo4j                      |
| ML / Inference     | Custom models, Perch/BirdNET embeddings, YOLO/ViT via Frigate |
| LLM / Agents       | Ollama + LangChain (LCEL)               |
| Orchestration      | Kubernetes (MicroK8s), ArgoCD           |
| Storage            | TimescaleDB / PostGIS (planned)         |
| Frontend / Viz     | TBD (currently API + Obsidian notes)    |

## Current Architecture Highlights

```
AudioMoth devices
       ↓
Recording ingestion → Detection pipeline
       ↓
PostgreSQL (detections, recordings, sites)
       ↓
BiomeSummaryService
   ├── Phase 1: Gather + Filter (sliding scale)
   ├── Phase 2: Species Enrichment (Retriever + LangChain)
   └── Phase 3: Narrative Generation (LangChain)
       ↓
Neo4j (species knowledge + RAG chunks)
       ↓
Rich ecological narrative reports
```

## Project Status (June 2026)

- Core detection pipeline is stable and running in production on real hardware.
- `BiomeSummaryService` with full LangChain RAG + narrative generation is implemented and tested.
- Strong emphasis on local/self-hosted operation and data ownership.
- Actively used for ongoing beekeeping + native prairie restoration monitoring.

This project is approaching a state where it can be shared more broadly as both a practical tool and a portfolio piece for senior ML / MLOps engineering roles.

## Related Work

- **Weathervane** — Multi-modal environmental monitoring (weather + computer vision + audio) focused on beehive health and prairie ecology.
- **Yard Sage** — LangGraph agent for generating biome reports from Obsidian notes + local weather data.
- **Frigate + AudioMoth integration** — Real-time event detection and LLM-assisted classification.

## Getting Started (Coming Soon)

Full setup instructions, Docker Compose / Kubernetes manifests, and model deployment guides will be added as the project stabilizes for wider use.

## Author

Dave Caulton — Senior Software / ML Engineer  
Hinsdale, Illinois

Building tools for ecological monitoring, local AI, and self-reliant systems.

## Perch model weights (not in git)

Perch v2 SavedModel files are **not** committed (they exceed GitHub’s file size limits).

Place the **CPU** Perch v2 model under:

```text
src/sound_detection/ml/perch/
  saved_model.pb
  variables/
  assets/
    labels.csv
    perch_v2_ebird_classes.csv   # optional
---

*This project is under active development. Feedback and collaboration welcome.*

