"""Tests for the Agent Runtime transport (app.app_utils.genai_transport)."""

import json

import httpx
import pytest

from app.app_utils.genai_transport import GenaiApiTransport, split_engine_url

ENGINE_URL = (
    "https://us-central1-aiplatform.googleapis.com/reasoningEngines/v1"
    "/projects/luncher-poc/locations/us-central1/reasoningEngines/724588608064847872"
    "/api/a2a/app"
)
CARD_URL = f"{ENGINE_URL}/.well-known/agent-card.json"


class _FakeApiClient:
    """Stands in for the genai ``_api_client``, recording what it was asked."""

    def __init__(self, *, body="{}", headers=None, error=None):
        self.body = body
        self.headers = headers if headers is not None else {}
        self.error = error
        self.calls = []

    def request(self, method, path, request_dict, http_options):
        self.calls.append((method, path, request_dict, http_options))
        if self.error:
            raise self.error
        return _FakeResponse(self.body, self.headers)


class _FakeResponse:
    def __init__(self, body, headers):
        self.body = body
        self.headers = headers


def _transport(**kwargs) -> GenaiApiTransport:
    transport = GenaiApiTransport.from_url(ENGINE_URL)
    transport._api_client = _FakeApiClient(**kwargs)
    return transport


def _send(transport: GenaiApiTransport, request: httpx.Request) -> httpx.Response:
    async def run():
        return await transport.handle_async_request(request)

    import asyncio

    return asyncio.run(run())


# --- URL splitting ---------------------------------------------------------


def test_split_engine_url_keeps_the_two_segment_api_version() -> None:
    base_url, api_version, project, location = split_engine_url(ENGINE_URL)
    assert base_url == "https://us-central1-aiplatform.googleapis.com"
    # Agent Runtime's version prefix is two segments, not a bare "v1".
    assert api_version == "reasoningEngines/v1"
    assert project == "luncher-poc"
    assert location == "us-central1"


def test_split_engine_url_rejects_a_url_without_a_resource_path() -> None:
    with pytest.raises(ValueError, match="Not an Agent Runtime resource URL"):
        split_engine_url("https://sched-agent.us-central1.run.app/a2a/app")


def test_split_engine_url_rejects_a_resource_path_missing_its_location() -> None:
    with pytest.raises(ValueError, match="Could not read project/location"):
        split_engine_url("https://host/v1/projects/p/reasoningEngines/2")


# --- request translation ---------------------------------------------------


def test_the_prefix_is_stripped_so_only_the_resource_path_is_sent() -> None:
    transport = _transport()
    _send(transport, httpx.Request("GET", CARD_URL))
    method, path, _, _ = transport._api_client.calls[0]
    assert method == "get"
    assert path == (
        "projects/luncher-poc/locations/us-central1"
        "/reasoningEngines/724588608064847872/api/a2a/app/.well-known/agent-card.json"
    )


def test_a_json_body_is_forwarded_as_a_dict() -> None:
    transport = _transport()
    envelope = {"jsonrpc": "2.0", "id": "1", "method": "message/send"}
    _send(transport, httpx.Request("POST", ENGINE_URL, json=envelope))
    assert transport._api_client.calls[0][2] == envelope


def test_a_request_without_a_body_sends_an_empty_dict() -> None:
    transport = _transport()
    _send(transport, httpx.Request("GET", CARD_URL))
    assert transport._api_client.calls[0][2] == {}


def test_headers_the_genai_client_supplies_itself_are_not_forwarded() -> None:
    transport = _transport()
    _send(
        transport,
        httpx.Request(
            "POST",
            ENGINE_URL,
            json={},
            headers={"Authorization": "Bearer stale", "X-Custom": "keep"},
        ),
    )
    forwarded = transport._api_client.calls[0][3]["headers"]
    assert "authorization" not in {k.lower() for k in forwarded}
    assert "host" not in {k.lower() for k in forwarded}
    assert "content-length" not in {k.lower() for k in forwarded}
    assert forwarded["x-custom"] == "keep"


def test_a_url_outside_the_bound_prefix_is_refused() -> None:
    transport = _transport()
    with pytest.raises(ValueError, match="cannot serve"):
        _send(transport, httpx.Request("GET", "https://example.com/whatever"))


def test_a_non_json_body_is_refused() -> None:
    transport = _transport()
    with pytest.raises(ValueError, match="Only JSON bodies"):
        _send(transport, httpx.Request("POST", ENGINE_URL, content=b"not json"))


# --- response translation --------------------------------------------------


def test_a_successful_call_becomes_a_200_carrying_the_body() -> None:
    payload = {"jsonrpc": "2.0", "result": {"artifacts": []}}
    transport = _transport(body=json.dumps(payload))
    response = _send(transport, httpx.Request("POST", ENGINE_URL, json={}))
    assert response.status_code == 200
    assert response.json() == payload


def test_encoding_headers_are_dropped_because_the_body_is_already_decoded() -> None:
    transport = _transport(
        body='{"ok": true}',
        headers={"content-encoding": "gzip", "content-type": "application/json"},
    )
    response = _send(transport, httpx.Request("POST", ENGINE_URL, json={}))
    # Claiming gzip over an already-decompressed body makes the response unreadable.
    assert "content-encoding" not in response.headers
    assert response.json() == {"ok": True}


def test_an_empty_body_does_not_break_the_response() -> None:
    transport = _transport(body="")
    response = _send(transport, httpx.Request("POST", ENGINE_URL, json={}))
    assert response.status_code == 200
    assert response.content == b""


def test_an_api_error_becomes_a_response_carrying_its_status() -> None:
    from google.genai import errors

    error = errors.ClientError(403, {"error": {"message": "denied", "code": 403}}, None)
    transport = _transport(error=error)
    response = _send(transport, httpx.Request("POST", ENGINE_URL, json={}))
    # A status, not an exception: ADK reports it the way it would any transport.
    assert response.status_code == 403
    assert "denied" in response.text
