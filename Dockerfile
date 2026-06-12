FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Сначала зависимости — лучше кэшируется
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

# Затем код
COPY bot ./bot
COPY config ./config
COPY scripts ./scripts

# Том для SQLite
RUN mkdir -p /app/data

CMD ["python", "-m", "bot.main"]
