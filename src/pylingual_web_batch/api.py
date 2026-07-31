from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .errors import ApiResponseError, PermanentDecompilerError

_RETRY_DELAYS = (0.3, 0.6, 1.2)
_POSITION = re.compile(r"waiting_for_decompiler\(pos=(\d+)\)")
_COMPLETED_STAGES = {"done", "completed", "complete", "finished"}


@dataclass(frozen=True)
class UploadResponse:
    identifier: str
    success: bool
    message: str | None = None


@dataclass(frozen=True)
class ProgressResponse:
    identifier: str | None
    stage: str | None
    position: int | None
    success: bool | None
    message: str | None = None


@dataclass(frozen=True)
class SourceResponse:
    source: str
    decompilation_successful: bool


class PylingualClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 90.0,
        user_agent: str = "pylingual-web-batch/0.1",
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._sleep = sleep
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers={
                "Accept": "*/*",
                "Origin": "https://www.pylingual.io",
                "Referer": "https://www.pylingual.io/",
                "User-Agent": user_agent,
            },
        )

    def upload(self, path: Path) -> UploadResponse:
        path = Path(path)
        with path.open("rb") as handle:
            payload = self._request_json(
                "POST",
                "/upload",
                files={"file": (path.name, handle, "application/octet-stream")},
                data={"fileName": path.name},
            )
        identifier = payload.get("identifier")
        success = payload.get("success")
        if success is not True or not isinstance(identifier, str) or not identifier:
            raise ApiResponseError(_message(payload, "upload response lacks an identifier"))
        return UploadResponse(identifier, True, _optional_str(payload.get("message")))

    def poll(self, identifier: str) -> ProgressResponse:
        payload = self._request_json("GET", "/get_progress", params={"identifier": identifier})
        stage = _optional_str(payload.get("stage"))
        success = payload.get("success")
        message = _optional_str(payload.get("message"))
        if success is False and (stage or "").lower() not in _COMPLETED_STAGES:
            raise PermanentDecompilerError(message or "decompiler failed")
        position = payload.get("position")
        if not isinstance(position, int) or isinstance(position, bool):
            match = _POSITION.search(stage or "")
            position = int(match.group(1)) if match else None
        response_identifier = _optional_str(payload.get("identifier")) or identifier
        return ProgressResponse(response_identifier, stage, position, success, message)

    def fetch_source(self, identifier: str) -> SourceResponse:
        payload = self._request_json("GET", "/view_chimera", params={"identifier": identifier})
        try:
            source = payload["editor_content"]["file_raw_python"]["editor_content"]
        except (KeyError, TypeError) as exc:
            raise ApiResponseError("source response lacks editor content") from exc
        if not isinstance(source, str):
            raise ApiResponseError("source editor content is not a string")
        successful = payload.get("decompilation_successful", True)
        if not isinstance(successful, bool):
            raise ApiResponseError("decompilation_successful is not a boolean")
        return SourceResponse(source, successful)

    def _request_json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        for attempt in range(4):
            try:
                response = self._client.request(method, url, **kwargs)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 3:
                        self._rewind_files(kwargs.get("files"))
                        self._sleep(_RETRY_DELAYS[attempt])
                        continue
                if response.is_error:
                    raise ApiResponseError(f"HTTP {response.status_code} from pylingual")
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ApiResponseError("pylingual response is not an object")
                return payload
            except httpx.TransportError as exc:
                if attempt == 3:
                    raise ApiResponseError(f"pylingual request failed: {exc}") from exc
                self._rewind_files(kwargs.get("files"))
                self._sleep(_RETRY_DELAYS[attempt])
            except ValueError as exc:
                raise ApiResponseError("pylingual response is not valid JSON") from exc
        raise ApiResponseError("pylingual request failed")

    @staticmethod
    def _rewind_files(files: Any) -> None:
        if not isinstance(files, dict):
            return
        for value in files.values():
            if isinstance(value, tuple) and len(value) >= 2 and hasattr(value[1], "seek"):
                value[1].seek(0)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PylingualClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _message(payload: dict[str, Any], fallback: str) -> str:
    return _optional_str(payload.get("message")) or fallback
