# LangChain Hello World (FastAPI)

![CI](https://github.com/edubertin/projeto_codex/actions/workflows/ci.yml/badge.svg)

## Overview
Starter kit with FastAPI + LangChain + Docker, ready for local use and CI.

## Requirements
- Docker Desktop
- Python 3.11+ (optional for local dev)

## Quickstart
1. Copy `.env.example` to `.env` and set `OPENAI_API_KEY`.
2. Run with Docker:

```bash
docker compose up --build
```

Open `http://localhost:8000/`.

## Endpoints
- `/` Static page
- `/api/hello` LLM response
- `/docs` Swagger
- `/redoc` ReDoc
- `/health` Healthcheck
- `/ready` Readiness

## Development
```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

## Security
Do not commit secrets. Use `.env` (gitignored) and `.env.example` as template.
