"""One error shape for every failure, and nothing private in it.

Every error answers {"error": {"code", "message", "problems"}, "trace_id"}. It names the fields
that are wrong and why, and never repeats the values that were sent: error messages end up in
client logs and support tickets, where a payment's details do not belong.
"""
import re
from collections.abc import Sequence

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from fraud_alerts.api.schemas import ErrorBody, ErrorResponse, Problem

# A field name comes from the client too, and can carry data ("card_4111111111111111"): an
# unknown name is shown only if it is short and holds no run of four or more digits.
SAFE_FIELD = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,31}")
DIGIT_RUN = re.compile(r"\d{4,}")
CODES = {404: "not_found", 405: "method_not_allowed", 413: "too_large", 503: "not_ready"}
MESSAGES = {
    404: "There is nothing at this address. The contract is at /docs.",
    405: "This address does not accept this method. The contract is at /docs.",
    413: "The request is too large to be one payment.",
    503: "The service is not ready: the model is not loaded.",
}

log = structlog.get_logger()


def envelope(request: Request, status: int, code: str, message: str,
             problems: Sequence[Problem] = ()) -> JSONResponse:
    trace_id = str(getattr(request.state, "trace_id", "unknown"))
    body = ErrorResponse(error=ErrorBody(code=code, message=message, problems=list(problems)),
                         trace_id=trace_id)
    return JSONResponse(status_code=status, content=body.model_dump(),
                        headers={"X-Trace-Id": trace_id})


def problems_of(error: RequestValidationError) -> list[Problem]:
    """Which field, and what is wrong with it: never the value that was sent."""
    found = []
    for item in error.errors():
        where = ".".join(str(part) for part in item.get("loc", ()) if part != "body")
        kind = item.get("type")
        if kind == "json_invalid":
            found.append(Problem(field="(the whole body)", problem="is not valid JSON"))
        elif kind == "extra_forbidden":
            safe = SAFE_FIELD.fullmatch(where) and not DIGIT_RUN.search(where)
            shown = where if safe else "(an unknown field, name not shown)"
            found.append(Problem(field=shown, problem="is not part of the contract"))
        else:
            found.append(Problem(field=where or "(the whole body)",
                                 problem=str(item.get("msg", "is not valid"))))
    return found


def install(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        problems = problems_of(error)
        log.info("rejected", fields=[problem.field for problem in problems])
        return envelope(request, 422, "invalid_request",
                        "The request does not match the contract: see problems, and /docs.",
                        problems)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        status = error.status_code
        return envelope(request, status, CODES.get(status, "http_error"),
                        MESSAGES.get(status, "The request could not be served."))

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception) -> JSONResponse:
        log.exception("unexpected_error")   # the details go to our log, never to the client
        return envelope(request, 500, "internal_error",
                        "Something went wrong on our side. Quote the trace_id to report it.")
