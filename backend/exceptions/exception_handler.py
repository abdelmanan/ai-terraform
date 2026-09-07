import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.exceptions.api_exception import ApiException

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI):

    @app.exception_handler(ApiException)
    async def api_exception_handler(
        request: Request,
        exc: ApiException
    ):
        logger.warning(
            "%s %s -> %d: %s",
            request.method, request.url.path, exc.status_code, exc.message
        )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "message": exc.message
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError
    ):
        return JSONResponse(
            status_code=422,
            content={
                "status": "error",
                "message": "Invalid request parameters.",
                "details": jsonable_encoder(exc.errors())
            }
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request,
        exc: Exception
    ):
        # The traceback goes to the logs, never to the client: str(exc) leaked
        # server paths and internals to anyone able to trigger a 500.
        logger.exception(
            "Unhandled error on %s %s", request.method, request.url.path
        )

        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Internal Server Error"
            }
        )