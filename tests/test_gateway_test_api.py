from fastapi.testclient import TestClient

import main
from services.staging_write_freeze import RouteClass, classify_route


def test_gateway_test_route_is_exempt_from_staging_write_freeze() -> None:
    assert (
        classify_route("POST", "/api/test-gateway")
        == RouteClass.EXEMPT_INTERNAL_IF_REQUIRED
    )


def test_gateway_test_endpoint_accepts_authenticated_json(monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_TOKEN", "demo-token")
    client = TestClient(main.app)
    payload = {
        "node_id": "MCU01",
        "label": "drone",
        "confidence": 0.92,
        "vendor_extra": {"raw": 123},
    }

    response = client.post(
        "/api/test-gateway",
        headers={"x-upload-token": "demo-token"},
        json=payload,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["message"] == "gateway payload received"
    assert isinstance(body["received_at_ms"], int)
    assert body["received"] == payload


def test_gateway_test_endpoint_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_TOKEN", "demo-token")
    client = TestClient(main.app)

    response = client.post("/api/test-gateway", json={"hello": "world"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid upload token"
