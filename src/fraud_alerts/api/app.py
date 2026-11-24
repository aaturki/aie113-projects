"""The web entry point: builds the app, loads the model once at start-up, and wires the routes.

    uvicorn fraud_alerts.api.app:create_app --factory --port 8000

This is the composition root: the one place that knows every layer. It picks the real model
adapter, hands it to the service, and turns web requests into domain payments.
"""
import re
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from fraud_alerts.adapters.model_bundle import ModelBundle
from fraud_alerts.api import errors, logs
from fraud_alerts.api.schemas import (
    Alive,
    AssessmentResponse,
    ErrorResponse,
    NotReady,
    PaymentRequest,
    Ready,
    ReasonOut,
)
from fraud_alerts.config import Settings
from fraud_alerts.domain.payment import Payment, hour_on_clock
from fraud_alerts.service.alerts import AlertService
from fraud_alerts.service.interfaces import FraudModel

API_VERSION = "1.0.0"
TRACE_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
MAX_BODY_BYTES = 16_384        # one payment is about 1 KB
ERRORS: dict[int | str, dict[str, object]] = {
    422: {"model": ErrorResponse, "description": "The request does not match the contract"},
    503: {"model": ErrorResponse, "description": "The model is not loaded"},
}
DESCRIPTION = """Scores one card payment for fraud, decides allow, review or block, and explains
every alert with its top reasons. A teaching service (SDA-AIE-113, SDAIA Academy) trained on
2013 data: never block a card or accuse anyone without a person checking."""

log = structlog.get_logger()


def create_app(settings: Settings | None = None, model: FraudModel | None = None) -> FastAPI:
    """By default the real model is loaded from settings.model_dir; tests pass a stand-in."""
    settings = settings or Settings()
    logs.configure(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Load the model once, at start-up, never per request.
        app.state.service = None
        try:
            loaded = model if model is not None else ModelBundle.load(settings.model_dir)
            app.state.service = AlertService(model=loaded,
                                             block_threshold=settings.block_threshold)
        except Exception as error:  # stay up and say why: /v1/ready answers 503
            log.error("model_not_loaded", error=f"{type(error).__name__}: {error}")
        else:
            log.info("model_loaded", model_version=loaded.version,
                     review_threshold=loaded.review_threshold,
                     block_threshold=settings.block_threshold,
                     bank_timezone=settings.bank_timezone)
        yield

    app = FastAPI(title="Fraud alerts", version=API_VERSION, description=DESCRIPTION,
                  lifespan=lifespan)
    errors.install(app)

    @app.middleware("http")
    async def trace_and_log(request: Request,
                            call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Give every request a trace id (the client's, if it sent a sensible one), refuse
        oversized bodies before reading them, and log one line per request."""
        given = request.headers.get("x-trace-id", "")
        trace_id = given if TRACE_ID.fullmatch(given) else uuid.uuid4().hex
        request.state.trace_id = trace_id
        started = time.perf_counter()
        with structlog.contextvars.bound_contextvars(trace_id=trace_id):
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > MAX_BODY_BYTES:
                response: Response = errors.envelope(request, 413, "too_large",
                                                     errors.MESSAGES[413])
            else:
                response = await call_next(request)
            response.headers["X-Trace-Id"] = trace_id
            log.info("request", method=request.method, path=request.url.path,
                     status=response.status_code,
                     ms=round((time.perf_counter() - started) * 1000, 1))
        return response

    @app.post("/v1/assess", response_model=AssessmentResponse, responses=ERRORS,
              summary="Assess one payment: score, decision and reasons")
    def assess(body: PaymentRequest, request: Request) -> AssessmentResponse:
        service: AlertService | None = request.app.state.service
        if service is None:
            raise HTTPException(status_code=503)
        hour = hour_on_clock(body.timestamp, settings.bank_clock)
        result = service.assess(Payment(hour=hour, amount=body.Amount, v=body.v()))
        log.info("assessed", decision=result.decision.value, score=round(result.score, 3),
                 reasons=[reason.input for reason in result.reasons],
                 model_version=result.model_version)
        return AssessmentResponse(
            score=result.score, decision=result.decision,
            review_threshold=result.thresholds.review_at,
            block_threshold=result.thresholds.block_at, hour=int(hour),
            reasons=[ReasonOut(**reason.model_dump()) for reason in result.reasons],
            model_version=result.model_version, trace_id=request.state.trace_id)

    @app.get("/v1/health", response_model=Alive, summary="Is the process alive?")
    def health() -> Alive:
        return Alive()

    @app.get("/v1/ready", response_model=Ready, responses={503: {"model": NotReady}},
             summary="Is the model loaded, and with which thresholds?")
    def ready(request: Request) -> Ready | JSONResponse:
        service: AlertService | None = request.app.state.service
        if service is None:
            reason = NotReady(reason="the model is not loaded; the service log says why")
            return JSONResponse(status_code=503, content=reason.model_dump())
        return Ready(model_version=service.model.version,
                     review_threshold=service.thresholds.review_at,
                     block_threshold=service.thresholds.block_at,
                     bank_timezone=settings.bank_timezone)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"service": "fraud alerts", "contract": "/docs", "ready": "/v1/ready"}

    return app
