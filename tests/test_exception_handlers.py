from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend.exceptions.api_exception import ApiException
from backend.exceptions.exception_handler import register_exception_handlers


def build_test_app():
    app = FastAPI()
    register_exception_handlers(app)

    class Payload(BaseModel):
        name: str

    @app.get("/boom-api-exception")
    def boom_api_exception():
        raise ApiException(message="custom failure", status_code=418)

    @app.get("/boom-generic")
    def boom_generic():
        raise RuntimeError("unexpected failure")

    @app.post("/validated")
    def validated(payload: Payload):
        return {"name": payload.name}

    return app


client = TestClient(build_test_app(), raise_server_exceptions=False)


def test_api_exception_is_formatted():
    response = client.get("/boom-api-exception")

    assert response.status_code == 418
    assert response.json() == {"status": "error", "message": "custom failure"}


def test_generic_exception_is_formatted():
    response = client.get("/boom-generic")

    assert response.status_code == 500
    body = response.json()
    assert body["status"] == "error"
    assert body["message"] == "Internal Server Error"


def test_generic_exception_does_not_leak_internals(caplog):
    # str(exc) used to be returned to the client, exposing server paths and
    # internal state to anyone able to trigger a 500.
    response = client.get("/boom-generic")

    body = response.json()
    assert "details" not in body
    assert "unexpected failure" not in response.text

    # ... but it must still be recoverable from the logs.
    assert "unexpected failure" in caplog.text


def test_validation_error_is_formatted():
    response = client.post("/validated", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "error"
    assert body["message"] == "Invalid request parameters."
    assert isinstance(body["details"], list)
    assert body["details"][0]["loc"] == ["body", "name"]
