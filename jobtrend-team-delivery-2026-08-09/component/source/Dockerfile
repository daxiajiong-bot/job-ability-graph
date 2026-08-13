FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.lock pyproject.toml README.md ./
COPY src ./src
COPY config ./config
COPY schemas ./schemas

RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements.lock && \
    python -m pip install --no-deps .

RUN useradd --create-home --uid 10001 jobtrend && \
    mkdir -p /input /kg /output /data && \
    chown -R jobtrend:jobtrend /input /kg /output /data /app

USER jobtrend
ENTRYPOINT ["jobtrend"]
CMD ["--help"]
