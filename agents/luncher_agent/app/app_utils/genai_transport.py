# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""An httpx transport that reaches Agent Runtime through the genai client.

Under Agent Identity the credential is bound, so a bearer header built from ADC
is 401'd and no IAM grant helps -- the fix is the transport, not the credential.
Exposing the genai client's ``_api_client.request()`` as a transport keeps card
resolution, the JSON-RPC envelope and part conversion in ADK's ``RemoteA2aAgent``.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlsplit

import anyio.to_thread
import httpx

logger = logging.getLogger(__name__)

# Engine routes look like
#   https://{loc}-aiplatform.googleapis.com/reasoningEngines/v1/{resource}/api/...
# where the version prefix is not the aiplatform API's plain `v1`.
_RESOURCE_MARKER = "/projects/"

# Hop-by-hop headers and ones the genai client sets itself; forwarding them
# would duplicate or corrupt its request.
_DROPPED_REQUEST_HEADERS = frozenset(
    {
        "authorization",
        "connection",
        "content-length",
        "host",
        "keep-alive",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "x-goog-api-client",
        "x-goog-user-project",
    }
)

# The genai client decompresses the body before handing it back, so passing the
# original encoding/length through would describe the payload incorrectly.
_DROPPED_RESPONSE_HEADERS = frozenset(
    {"content-encoding", "content-length", "transfer-encoding"}
)


def split_engine_url(url: str) -> tuple[str, str, str, str]:
    """Splits an Agent Runtime URL into the parts the genai client needs.

    Returns ``(base_url, api_version, project, location)`` for a URL of the form
    ``https://{loc}-aiplatform.googleapis.com/{api_version}/projects/{p}/locations/{l}/...``.

    ``api_version`` is everything between the host and the resource path because
    Agent Runtime's is ``reasoningEngines/v1`` -- two segments, so it cannot be
    recovered by taking a single path element.

    Raises:
        ValueError: if the URL does not contain a ``/projects/...`` resource path.
    """
    parts = urlsplit(url)
    marker = parts.path.find(_RESOURCE_MARKER)
    if marker == -1:
        raise ValueError(
            f"Not an Agent Runtime resource URL (no '{_RESOURCE_MARKER}' segment): {url}"
        )

    base_url = f"{parts.scheme}://{parts.netloc}"
    api_version = parts.path[:marker].strip("/")
    resource_path = parts.path[marker + 1 :]

    segments = resource_path.split("/")
    project = _segment_after(segments, "projects")
    location = _segment_after(segments, "locations")
    if not project or not location:
        raise ValueError(f"Could not read project/location from: {url}")

    return base_url, api_version, project, location


def _segment_after(segments: list[str], key: str) -> str | None:
    try:
        return segments[segments.index(key) + 1]
    except (ValueError, IndexError):
        return None


class GenaiApiTransport(httpx.AsyncBaseTransport):
    """Routes httpx requests through the genai client's authenticated transport.

    The URL prefix is fixed at construction: every request this transport serves
    is expected to sit under the same ``{base_url}/{api_version}`` as the engine
    it was built for, and the remainder becomes the ``path`` the genai client is
    given. A request outside that prefix is a bug rather than something to fall
    back on, so it fails loudly.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_version: str,
        project: str,
        location: str,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_version = api_version.strip("/")
        self._project = project
        self._location = location
        self._prefix = f"{self._base_url}/{self._api_version}/"
        self._api_client: Any | None = None

    @classmethod
    def from_url(cls, url: str) -> "GenaiApiTransport":
        """Builds a transport for the engine that ``url`` addresses."""
        base_url, api_version, project, location = split_engine_url(url)
        return cls(
            base_url=base_url,
            api_version=api_version,
            project=project,
            location=location,
        )

    def _client(self) -> Any:
        """The genai API client, built once on first use.

        Deferred rather than built in ``__init__`` so that importing the agent
        module does not require credentials -- tests and local runs import it
        without any, and construction resolves ADC.
        """
        if self._api_client is None:
            import vertexai

            self._api_client = vertexai.Client(
                project=self._project,
                location=self._location,
                http_options={
                    "base_url": self._base_url,
                    "api_version": self._api_version,
                },
            )._api_client
        return self._api_client

    def _path_for(self, url: httpx.URL) -> str:
        target = str(url)
        if not target.startswith(self._prefix):
            raise ValueError(
                f"{type(self).__name__} is bound to {self._prefix!r} "
                f"and cannot serve {target!r}"
            )
        return target[len(self._prefix) :]

    def _send(self, request: httpx.Request) -> httpx.Response:
        """Performs the request synchronously; ``request()`` does blocking I/O."""
        from google.genai import errors

        path = self._path_for(request.url)
        body: dict[str, Any] = {}
        if request.content:
            try:
                body = json.loads(request.content)
            except ValueError as e:
                raise ValueError(
                    f"Only JSON bodies can be sent through {type(self).__name__}: {e}"
                ) from e

        headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in _DROPPED_REQUEST_HEADERS
        }

        try:
            response = self._client().request(
                request.method.lower(), path, body, {"headers": headers}
            )
        except errors.APIError as e:
            # Surface the real status rather than an exception, so ADK's A2A
            # client reports "401 from the card fetch" the same way it would for
            # any other transport instead of a transport-specific failure.
            logger.warning(
                "Agent Runtime call to %s failed: %s %s", path, e.code, e.message
            )
            return httpx.Response(
                status_code=e.code,
                headers={"content-type": "application/json"},
                content=json.dumps({"error": {"code": e.code, "message": e.message}}),
                request=request,
            )

        raw = getattr(response, "body", None) or ""
        content = raw.encode() if isinstance(raw, str) else bytes(raw)
        headers_out = {
            k: v
            for k, v in (getattr(response, "headers", None) or {}).items()
            if k.lower() not in _DROPPED_RESPONSE_HEADERS
        }
        headers_out.setdefault("content-type", "application/json")
        return httpx.Response(
            status_code=200, headers=headers_out, content=content, request=request
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # `request()` is blocking (it owns its own retry loop and credential
        # refresh), so it must not run on the event loop.
        await request.aread()
        return await anyio.to_thread.run_sync(self._send, request)
