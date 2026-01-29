import json
import logging
import time
import uuid
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from settings import get_settings

settings = get_settings()

logging.basicConfig(
    level=logging.INFO,
    format='{"level":"%(levelname)s","message":%(message)s}',
)
logger = logging.getLogger("app")

app = FastAPI(
    title="LangChain Hello World",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(",")
    if settings.allowed_origins
    else ["*"],
    allow_credentials=True,
    allow_methods=["*"] ,
    allow_headers=["*"] ,
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.middleware("http")
async def request_id_middleware(request: Request, call_next: Callable):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    start = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)
    response.headers["x-request-id"] = request_id
    logger.info(
        json.dumps(
            {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            }
        )
    )
    return response


def get_llm_response() -> str:
    llm = ChatOpenAI(
        model=settings.model,
        temperature=settings.temperature,
        request_timeout=settings.request_timeout,
        max_retries=settings.max_retries,
    )
    response = llm.invoke(
        [HumanMessage(content="Responda com 'Hello, world!' em portugues e em ingles.")]
    )
    return response.content


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/hello")
def hello() -> dict:
    return {"message": get_llm_response()}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    return {"status": "ready"}
