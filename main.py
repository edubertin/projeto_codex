import json
import logging
import time
import uuid
from threading import Lock
from typing import Callable, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_postgres import PGVector
from pydantic import BaseModel
import psycopg
import redis
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

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

origins = (
    settings.allowed_origins.split(",")
    if settings.allowed_origins
    else ["*"]
)
allow_credentials = "*" not in origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
)

_rate_lock = Lock()
_rate_state: Dict[str, Tuple[float, int]] = {}
_vector_lock = Lock()
_vector_store: Optional[PGVector] = None
_redis_client: Optional[redis.Redis] = None


def setup_tracing(app_instance: FastAPI) -> None:
    if not settings.enable_tracing:
        return
    if not settings.otel_exporter_otlp_endpoint:
        return

    resource = Resource(attributes={"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app_instance)


setup_tracing(app)


class IngestRequest(BaseModel):
    texts: List[str]
    metadatas: Optional[List[Dict]] = None


class QueryRequest(BaseModel):
    query: str
    k: int = 4


def _psycopg_url() -> str:
    if settings.database_url.startswith("postgresql+psycopg://"):
        return settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return settings.database_url


def ensure_pgvector() -> None:
    with psycopg.connect(_psycopg_url()) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        conn.commit()


def get_vector_store() -> PGVector:
    global _vector_store
    if _vector_store is not None:
        return _vector_store
    with _vector_lock:
        if _vector_store is not None:
            return _vector_store
        ensure_pgvector()
        embeddings = OpenAIEmbeddings(model=settings.embedding_model)
        _vector_store = PGVector(
            embeddings=embeddings,
            collection_name=settings.rag_collection,
            connection=settings.database_url,
            use_jsonb=True,
        )
        return _vector_store


def get_redis() -> Optional[redis.Redis]:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        _redis_client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        _redis_client.ping()
        return _redis_client
    except Exception:
        return None


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def should_rate_limit(path: str) -> bool:
    return path.startswith("/v1/")


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next: Callable):
    if not settings.enable_rate_limit or not should_rate_limit(request.url.path):
        return await call_next(request)

    key = get_client_ip(request)
    now = time.time()

    with _rate_lock:
        window_start, count = _rate_state.get(key, (now, 0))

        if now - window_start >= 60:
            window_start, count = now, 0

        if count >= settings.rate_limit_per_minute:
            return JSONResponse(
                status_code=429,
                content={"detail": "rate limit exceeded"},
            )

        _rate_state[key] = (window_start, count + 1)

    return await call_next(request)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next: Callable):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    start = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)
    response.headers["x-request-id"] = request_id

    if settings.enable_metrics:
        path = request.url.path
        REQUEST_COUNT.labels(request.method, path, response.status_code).inc()
        REQUEST_LATENCY.labels(request.method, path).observe(
            (time.time() - start)
        )

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


@app.post("/v1/ingest")
def ingest(req: IngestRequest) -> dict:
    if not req.texts:
        raise HTTPException(status_code=400, detail="texts is required")
    metadatas = req.metadatas or [{} for _ in req.texts]
    if len(metadatas) != len(req.texts):
        raise HTTPException(status_code=400, detail="metadatas length mismatch")

    docs = [
        Document(page_content=text, metadata=meta or {})
        for text, meta in zip(req.texts, metadatas)
    ]
    store = get_vector_store()
    ids = store.add_documents(docs)
    return {"ingested": len(ids)}


@app.post("/v1/query")
def query(req: QueryRequest) -> dict:
    cache_key = f"rag:query:{req.query}:{req.k}"
    r = get_redis()
    if r:
        cached = r.get(cache_key)
        if cached:
            return json.loads(cached)

    store = get_vector_store()
    results = store.similarity_search_with_score(req.query, k=req.k)
    payload = [
        {"text": doc.page_content, "metadata": doc.metadata, "score": score}
        for doc, score in results
    ]
    response = {"query": req.query, "results": payload}
    if r:
        r.setex(cache_key, settings.cache_ttl_seconds, json.dumps(response))
    return response


@app.get("/v1/hello")
def hello_v1() -> dict:
    return {"message": get_llm_response(), "version": "v1"}


@app.get("/api/hello")
def hello_legacy() -> dict:
    return {"message": get_llm_response(), "deprecated": True}


@app.get("/metrics")
def metrics() -> Response:
    if not settings.enable_metrics:
        return Response(status_code=404)
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@app.get("/api/dashboard")
def dashboard() -> dict:
    r = get_redis()
    cache_ok = False
    if r:
        try:
            r.ping()
            cache_ok = True
        except Exception:
            cache_ok = False
    return {
        "cache": {
            "enabled": r is not None,
            "healthy": cache_ok,
            "ttl_seconds": settings.cache_ttl_seconds,
        },
        "rag": {
            "collection": settings.rag_collection,
        },
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    return {"status": "ready"}
