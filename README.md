# Sound Detection

A production-leaning, local-first bioacoustics platform for continuous wildlife monitoring using AudioMoth recorders, custom ML models, and rich ecological reporting.

## What It Does

Sound Detection ingests audio from edge recorders (primarily AudioMoth), runs them through a multi-stage ML pipeline, and turns raw detections into meaningful ecological insights.

Recent work added a **criteria-driven BiomeSummaryService**. Species are filtered and scored against a user-supplied taxonomy criteria (any rank, any clade, or none) instead of a fixed list of bird families. Confirmed detections (BirdNET + Perch agreement) drive the primary narrative; single-analyzer detections are treated as speculated.

## Key Features

- **Audio ingestion & detection pipeline** — Handles continuous recordings from multiple AudioMoth devices.
- **Species knowledge graph** — Neo4j-backed knowledge base with structured data (range, habitat, diet, interesting facts) + Wikipedia RAG chunks.
- **Taxonomy hierarchy** — GBIF rank harvesting with `PARENT_OF` edges so every species carries its ancestry.
- **Criteria-driven filtering & scoring** — `in_scope` and `interest_weight` applied to the ancestry chain; no hardcoded species groups.
- **Confirmed vs. speculated detections** — Primary buckets use multi-model agreement counts; single-analyzer rows are secondary.
- **LangChain-powered enrichment** — Per-species contextual summaries + dual narratives (machine + human-readable).
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
   ├── Phase 1: Gather + Filter (ancestry + criteria)
   ├── Phase 2: Species Enrichment (Retriever + LangChain)
   └── Phase 3: Narrative Generation (LangChain)
       ↓
Neo4j (species knowledge + RAG chunks + taxonomy edges)
       ↓
Rich ecological narrative reports
```

## Project Status (October 2026)

- Core detection pipeline is stable and running in production on real hardware.
- BiomeSummaryService uses criteria-driven clade scoring and dual narratives.
- Taxonomy edges (GBIF ranks, `PARENT_OF`) are populated for known species.
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

Building tools for ecological monitoring, local AI, and self-reliant systems.

---

*This project is under active development. Feedback and collaboration welcome.*
