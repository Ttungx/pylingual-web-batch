from pathlib import Path

import httpx
import pytest

from pylingual_web_batch.api import PylingualClient
from pylingual_web_batch.errors import ApiResponseError, PermanentDecompilerError


def response(request: httpx.Request, payload: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, request=request, json=payload)


def test_upload_sends_multipart_and_returns_identifier(tmp_path: Path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["content_type"] = request.headers["content-type"]
        seen["origin"] = request.headers["origin"]
        seen["body"] = request.read()
        return response(request, {"success": True, "identifier": "abc"})

    path = tmp_path / "module.pyc"
    path.write_bytes(b"pyc")
    with PylingualClient("https://example.test", transport=httpx.MockTransport(handler)) as client:
        result = client.upload(path)

    assert result.identifier == "abc"
    assert "multipart/form-data" in seen["content_type"]
    assert seen["origin"] == "https://www.pylingual.io"
    assert b"module.pyc" in seen["body"]


def test_progress_and_source_use_documented_endpoints():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.url.params.get("identifier")))
        if request.url.path == "/get_progress":
            return response(request, {"success": True, "stage": "working"})
        return response(
            request,
            {"editor_content": {"file_raw_python": {"editor_content": "source"}}},
        )

    with PylingualClient(
        "https://example.test", transport=httpx.MockTransport(handler)
    ) as client:
        client.poll("abc")
        client.fetch_source("abc")

    assert seen == [("/get_progress", "abc"), ("/view_chimera", "abc")]


def test_poll_extracts_queue_position_and_permanent_failure():
    replies = iter(
        [
            {"success": True, "stage": "waiting_for_decompiler(pos=12)"},
            {"success": False, "message": "IndexError"},
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return response(request, next(replies))

    with PylingualClient("https://example.test", transport=httpx.MockTransport(handler)) as client:
        assert client.poll("abc").position == 12
        with pytest.raises(PermanentDecompilerError, match="IndexError"):
            client.poll("abc")


def test_poll_rejects_false_success_before_completion():
    payload = {"success": False, "stage": "working", "message": "bad bytecode"}
    transport = httpx.MockTransport(lambda request: response(request, payload))
    with PylingualClient("https://example.test", transport=transport) as client:
        with pytest.raises(PermanentDecompilerError, match="bad bytecode"):
            client.poll("abc")


def test_completed_stage_with_false_success_is_still_fetchable():
    payload = {"success": False, "stage": "done", "message": "partial"}
    transport = httpx.MockTransport(lambda request: response(request, payload))
    with PylingualClient("https://example.test", transport=transport) as client:
        progress = client.poll("abc")
    assert progress.stage == "done"
    assert progress.success is False


def test_fetch_source_preserves_source():
    payload = {
        "editor_content": {"file_raw_python": {"editor_content": "print('x')\n"}},
        "decompilation_successful": True,
    }
    transport = httpx.MockTransport(lambda request: response(request, payload))
    with PylingualClient("https://example.test", transport=transport) as client:
        result = client.fetch_source("abc")
    assert result.source == "print('x')\n"
    assert result.decompilation_successful is True


def test_retry_upload_resends_file_content(tmp_path: Path):
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.read())
        if len(bodies) == 1:
            return response(request, {"message": "busy"}, 503)
        return response(request, {"success": True, "identifier": "abc"})

    path = tmp_path / "module.pyc"
    path.write_bytes(b"bytecode-content")
    with PylingualClient(
        "https://example.test",
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
    ) as client:
        client.upload(path)

    assert len(bodies) == 2
    assert all(b"bytecode-content" in body for body in bodies)


def test_retry_503_then_success_and_do_not_retry_400():
    calls = 0

    def retry_handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return response(request, {"message": "busy"}, 503)
        return response(request, {"success": True, "identifier": "abc"})

    transport = httpx.MockTransport(retry_handler)
    with PylingualClient(
        "https://example.test", transport=transport, sleep=lambda _: None
    ) as client:
        result = client.upload(Path(__file__))
    assert result.identifier == "abc"
    assert calls == 2

    calls = 0

    def bad_handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response(request, {"message": "bad"}, 400)

    with PylingualClient(
        "https://example.test",
        transport=httpx.MockTransport(bad_handler),
        sleep=lambda _: None,
    ) as client:
        with pytest.raises(ApiResponseError):
            client.upload(Path(__file__))
    assert calls == 1
