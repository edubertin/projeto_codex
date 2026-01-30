import json
import logging
import time
import uuid
from threading import Lock
from typing import Callable, Dict, Tuple

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(",")
    if settings.allowed_origins
    else ["*"],
    allow_credentials=True,
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


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next: Callable):
    if not settings.enable_rate_limit:
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


@app.get("/api/hello")
def hello() -> dict:
    return {"message": get_llm_response()}


@app.get("/metrics")
def metrics() -> Response:
    if not settings.enable_metrics:
        return Response(status_code=404)
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    return {"status": "ready"}
