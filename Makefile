.PHONY: help install install-cuda install-tensorflow dev test lint clean

help:
	@echo "sound-detection — Bioacoustics ML service"
	@echo ""
	@echo "make install          → full setup (Torch + TensorFlow)"
	@echo "make dev              → start FastAPI dev server"
	@echo "make test             → run tests"
	@echo "make lint             → ruff + mypy"

install:
	uv sync --all-extras
	$(MAKE) install-cuda
	$(MAKE) install-tensorflow
	uv pip install -e .
	@echo "✅ All dependencies installed! Run 'make dev' to start."

install-cuda:
	@echo "🔧 Installing Torch + Torchaudio with CUDA 12.6 (5080 + 1080Ti)..."
	uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126

install-tensorflow:
	@echo "🔧 Installing tensorflow-cpu (lighter, sufficient for BirdNET TFLite)..."
	uv pip install tensorflow-cpu

dev:
	uv run uvicorn sound_detection.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format .
	uv run mypy src

clean:
	rm -rf .venv uv.lock __pycache__ .pytest_cache .ruff_cache
	uv cache clean
