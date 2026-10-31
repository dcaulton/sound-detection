FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      libsndfile1 \
      curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    AUDIO_TMP_ROOT=/data/tmp

COPY pyproject.toml uv.lock ./
COPY src ./src
COPY alembic.ini ./
COPY src/sound_detection/db/migrations ./src/sound_detection/db/migrations
COPY README.md ./

RUN uv sync --frozen --no-dev --no-install-project \
    && uv pip install --no-deps -e .

VOLUME ["/data/tmp", "/app/src/sound_detection/ml/perch"]

EXPOSE 8000

CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn src.sound_detection.main:app --host 0.0.0.0 --port 8000"]
