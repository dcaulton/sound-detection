.PHONY: help install install-cuda install-tensorflow dev test lint clean db-upgrade db-downgrade

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
	@if [ ! -d ".venv" ]; then \
		echo "🔧 No virtual environment found. Running 'make install' first..."; \
		$(MAKE) install; \
	fi
	DATABASE_URL=postgresql://sound:sound@localhost:5433/sound_detection \
	uv run uvicorn src.sound_detection.main:app --reload

test:
	uv run pytest -v

lint:
	uv run ruff check .
	uv run ruff format .
	uv run mypy src

clean:
	rm -rf .venv uv.lock __pycache__ .pytest_cache .ruff_cache
	uv cache clean

db-upgrade:
	uv run alembic upgrade head

db-downgrade:
	uv run alembic downgrade -1
