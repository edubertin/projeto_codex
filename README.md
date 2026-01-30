# LangChain Hello World (FastAPI)

![CI](https://github.com/edubertin/projeto_codex/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)

A minimal but production-ready starter with FastAPI + LangChain + Docker. Includes Swagger, health checks, CI, metrics, and tracing hooks.

## Features
- FastAPI app with Swagger/ReDoc
- LangChain + OpenAI ready
- Static `index.html`
- Health and readiness endpoints
- Prometheus metrics (`/metrics`)
- Optional OpenTelemetry tracing
- Simple rate limiting
- Structured logs + request-id
- Dockerized with non-root user + healthcheck
- CI with GitHub Actions (pytest)

## Tech Stack
- Python 3.11
- FastAPI + Uvicorn
- LangChain + OpenAI
- Docker + Docker Compose

## Project Structure
```
.
?? main.py
?? settings.py
?? static/
?  ?? index.html
?? tests/
?  ?? test_health.py
?? docker-compose.yml
?? Dockerfile
?? requirements.txt
?? requirements-dev.txt
?? .env.example
?? README.md
```

## Quickstart (Docker)
1. Copy `.env.example` to `.env` and set `OPENAI_API_KEY`.
2. Run:

```bash
docker compose up --build
```

Open `http://localhost:8000/`.

## Local Development
```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

## API Endpoints
- `/` Static page
- `/api/hello` LLM response
- `/docs` Swagger
- `/redoc` ReDoc
- `/metrics` Prometheus metrics
- `/health` Healthcheck
- `/ready` Readiness

## Configuration
Environment variables (see `.env.example`):
- `OPENAI_API_KEY`
- `MODEL` (default: `gpt-4o-mini`)
- `TEMPERATURE`
- `REQUEST_TIMEOUT`
- `MAX_RETRIES`
- `ALLOWED_ORIGINS`
- `ENABLE_RATE_LIMIT`
- `RATE_LIMIT_PER_MINUTE`
- `ENABLE_METRICS`
- `ENABLE_TRACING`
- `OTEL_SERVICE_NAME`
- `OTEL_EXPORTER_OTLP_ENDPOINT`

## Observability
- Metrics: scrape `http://localhost:8000/metrics` with Prometheus.
- Tracing: set `ENABLE_TRACING=true` and `OTEL_EXPORTER_OTLP_ENDPOINT` (OTLP/HTTP).

## Security
- Never commit secrets. Use `.env` (gitignored).
- Rotate keys if accidentally exposed.

## Contributing
See `.github/CONTRIBUTING.md`.

## License
MIT. See `LICENSE`.
