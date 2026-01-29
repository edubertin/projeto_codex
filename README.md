# LangChain Hello World (FastAPI)

## Requisitos
- Docker Desktop

## Configuracao
1. Edite `.env` e preencha `OPENAI_API_KEY`.

## Rodar
```bash
docker compose up --build
```

## Endpoints
- `/` pagina estatica
- `/api/hello` retorna a resposta do LLM
- `/docs` Swagger
- `/redoc` ReDoc
- `/health` healthcheck
- `/ready` readiness

## Observabilidade
- Logs incluem `x-request-id` e duracao da requisicao.
