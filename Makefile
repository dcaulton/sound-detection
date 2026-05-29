.PHONY: help install install-cuda dev test lint clean

help:
	@echo "sound-detection — Bioacoustics ML service"
	@echo ""
	@echo "make install      → install everything (including Torch for your GPU)"
	@echo "make dev          → start FastAPI dev server"
	@echo "make test         → run tests"
	@echo "make lint         → ruff + mypy"

install:
	uv sync --all-extras
	@echo "🔧 Installing Torch + Torchaudio with CUDA 12.6 (works on 5080 + 1080Ti)..."
	uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
	uv pip install -e .          # ← makes src/sound_detection importable
	@echo "✅ Done! Run 'make dev' to start the service."

install-cuda:
	uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126

dev:
	uv run uvicorn sound_detection.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run mypy src      # only src/ for now (tests/ will be added later)

clean:
	rm -rf .venv uv.lock __pycache__ .pytest_cache .ruff_cache
	uv cache clean
