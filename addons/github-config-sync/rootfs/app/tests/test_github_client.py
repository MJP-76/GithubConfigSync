from __future__ import annotations

import base64
import io
import json
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from sync import github_client
from sync.errors import SyncError
from sync.github_client import GitHubClient


class FakeResponse:
    def __init__(self, body: bytes = b"", headers: dict[str, str] | None = None) -> None:
        self._body = body
        self.headers = headers or {}

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def _http_error(
    code: int,
    body: bytes = b"{}",
    reset: str | None = None,
    retry_after: str | None = None,
) -> urllib.error.HTTPError:
    headers = Message()
    if reset is not None:
        headers["X-RateLimit-Reset"] = reset
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://api.github.com/x", code, "msg", headers, io.BytesIO(body))


def _client(repository: str = "owner/repo") -> GitHubClient:
    return GitHubClient(repository=repository, branch="main", token="token")


class TransportTests(unittest.TestCase):
    """Each client owns its rate-limit gate, so these need no global reset.

    The gate used to be module-global and every test had to clear it in setUp.
    A test that forgot to leaked a half-hour backoff into the next one.
    """

    def test_get_returns_decoded_json(self) -> None:
        client = _client()
        with patch(
            "sync.github_client.urllib.request.urlopen",
            return_value=FakeResponse(json.dumps({"full_name": "owner/repo"}).encode()),
        ) as mock_urlopen:
            result = client._request_any("GET", "https://api.github.com/repos/owner/repo")

        self.assertEqual(result, {"full_name": "owner/repo"})
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.full_url, "https://api.github.com/repos/owner/repo")
        self.assertEqual(request.headers.get("Authorization"), "Bearer token")

    def test_post_sends_json_payload(self) -> None:
        client = _client()
        with patch(
            "sync.github_client.urllib.request.urlopen",
            return_value=FakeResponse(b"{}"),
        ) as mock_urlopen:
            client._request_any("PUT", "https://api.github.com/repos/owner/repo/contents/x.yaml",
                                payload={"message": "m", "content": "cG9pbnQ="})

        request = mock_urlopen.call_args.args[0]
        sent = json.loads(request.data)
        self.assertEqual(request.method, "PUT")
        self.assertEqual(request.headers.get("Content-type"), "application/json")
        self.assertEqual(sent, {"message": "m", "content": "cG9pbnQ="})

    def test_empty_response_decodes_to_empty_dict(self) -> None:
        client = _client()
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(b"")):
            self.assertEqual(client._request_any("GET", "https://api.github.com/x"), {})

    def test_plain_error_raises_with_http_code_and_body(self) -> None:
        client = _client()
        with self.assertRaises(SyncError) as ctx:
            with patch(
                "sync.github_client.urllib.request.urlopen",
                side_effect=_http_error(404, b'{"message":"nope"}'),
            ):
                client._request_any("GET", "https://api.github.com/repos/owner/repo")
        message = str(ctx.exception)
        self.assertIn("HTTP 404", message)
        self.assertIn("nope", message)

    def test_transient_5xx_retries_then_succeeds(self) -> None:
        client = _client()
        responses = [
            _http_error(500, b'{"message":"boom"}'),
            FakeResponse(b'{"ok":true}'),
        ]
        with patch("sync.github_client.time.sleep") as mock_sleep:
            with patch("sync.github_client.urllib.request.urlopen", side_effect=responses) as mock_urlopen:
                result = client._request_any("GET", "https://api.github.com/x")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once_with(1)

    def test_transient_5xx_exhausts_and_raises(self) -> None:
        client = _client()
        errors = [_http_error(503, b'{"message":"down"}') for _ in range(5)]
        with patch("sync.github_client.time.sleep"):
            with patch("sync.github_client.urllib.request.urlopen", side_effect=errors):
                with self.assertRaises(SyncError) as ctx:
                    client._request_any("GET", "https://api.github.com/x")
        self.assertIn("HTTP 503", str(ctx.exception))

    def test_rate_limit_403_waits_retry_after_then_succeeds(self) -> None:
        client = _client()
        reset_epoch = str(int(time.time()) + 120)
        responses = [
            _http_error(403, b'{"message":"API rate limit exceeded"}', reset=reset_epoch),
            FakeResponse(b'{"ok":true}'),
        ]
        with patch("sync.github_client.time.sleep") as mock_sleep:
            with patch("sync.github_client.urllib.request.urlopen", side_effect=responses) as mock_urlopen:
                result = client._request_any("GET", "https://api.github.com/x")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(mock_urlopen.call_count, 2)
        # Any sleep may now be last (the release stagger is), so look for the
        # one that honoured X-RateLimit-Reset rather than assuming its position.
        waits = [call.args[0] for call in mock_sleep.call_args_list if call.args]
        self.assertTrue(
            any(1.0 <= w <= 300 for w in waits),
            f"expected a wait near the reset time, got {waits}",
        )

    def test_rate_limit_that_never_clears_fails_instead_of_retrying_forever(self) -> None:
        """A refusal retrying cannot fix has to surface, not spin silently.

        The request loop had no ceiling, so a permanently-refused request
        retried for hours: no error, no result, repository untouched, and
        nothing in the log saying why. Honouring the wait is still correct -
        giving up before the wait GitHub asked for would fail healthy syncs.
        """
        client = _client()
        responses = [
            _http_error(403, b'{"message":"API rate limit exceeded for 198.51.100.9."}')
            for _ in range(8)
        ]
        with patch("sync.github_client.time.sleep"):
            with patch(
                "sync.github_client.urllib.request.urlopen", side_effect=responses
            ) as mock_urlopen:
                with self.assertRaises(SyncError) as caught:
                    client._request_any("GET", "https://api.github.com/x")

        # The initial attempt plus the retry ceiling, and not one more.
        self.assertEqual(
            mock_urlopen.call_count, github_client._RATE_LIMIT_MAX_RETRIES + 1
        )
        # GitHub's own explanation has to survive into the error, or the failure
        # is exactly as undiagnosable as the hang it replaced.
        self.assertIn("API rate limit exceeded", str(caught.exception))

    def test_a_rate_limit_body_that_names_the_offending_token_is_kept(self) -> None:
        """Distinguishes an exhausted quota from a token that cannot reach the repo."""
        client = _client()
        body = b'{"message":"Resource not accessible by integration"}'
        responses = [_http_error(403, body) for _ in range(8)]
        with patch("sync.github_client.time.sleep"):
            with patch("sync.github_client.urllib.request.urlopen", side_effect=responses):
                with self.assertRaises(SyncError) as caught:
                    client._request_any("GET", "https://api.github.com/repos/o/r/git/blobs")

        self.assertIn("Resource not accessible by integration", str(caught.exception))

    def test_rate_limit_429_with_retry_after_waits_then_succeeds(self) -> None:
        client = _client()
        responses = [
            _http_error(
                429,
                b'{"message":"You have triggered an abuse detection mechanism"}',
                retry_after="2",
            ),
            FakeResponse(b'{"ok":true}'),
        ]
        with patch("sync.github_client.time.sleep") as mock_sleep:
            with patch("sync.github_client.urllib.request.urlopen", side_effect=responses) as mock_urlopen:
                result = client._request_any("GET", "https://api.github.com/x")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(mock_urlopen.call_count, 2)
        self.assertGreaterEqual(mock_sleep.call_args.args[0], 2.0)

    def test_rate_limit_wait_aborts_on_cancel_hook(self) -> None:
        client = _client()
        client.register_rate_limit_hooks(cancel_check=lambda: True)
        with patch("sync.github_client.time.sleep"):
            with patch(
                "sync.github_client.urllib.request.urlopen",
                side_effect=_http_error(429, b"{}", retry_after="900"),
            ) as mock_urlopen:
                with self.assertRaises(SyncError) as ctx:
                    client._request_any("GET", "https://api.github.com/x")

        self.assertIn("cancelled", str(ctx.exception))
        self.assertEqual(mock_urlopen.call_count, 1)

    def test_url_error_becomes_sync_error(self) -> None:
        client = _client()
        with patch(
            "sync.github_client.urllib.request.urlopen",
            side_effect=urllib.error.URLError("no route to host"),
        ):
            with self.assertRaises(SyncError) as ctx:
                client._request_any("GET", "https://api.github.com/x")
        self.assertIn("no route to host", str(ctx.exception))

    def test_request_json_rejects_non_object(self) -> None:
        client = _client()
        with patch(
            "sync.github_client.urllib.request.urlopen",
            return_value=FakeResponse(b'["a", "b"]'),
        ):
            with self.assertRaises(SyncError) as ctx:
                client._request_json("GET", "https://api.github.com/x")
        self.assertIn("non-object JSON", str(ctx.exception))


class DeviceFlowTests(unittest.TestCase):
    def test_start_device_flow_posts_scope_and_client_id(self) -> None:
        body = json.dumps({"device_code": "dc", "user_code": "uc", "verification_uri": "example", "interval": 5}).encode()
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(body)) as mock_urlopen:
            result = _client().start_device_flow("client-123", scope="repo")

        self.assertEqual(result["device_code"], "dc")
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://github.com/login/device/code")
        sent = json.loads(request.data)
        self.assertEqual(sent, {"client_id": "client-123", "scope": "repo"})

    def test_exchange_device_flow_polls_then_returns_token(self) -> None:
        pending = json.dumps({"error": "authorization_pending", "error_description": "waiting"}).encode()
        granted = json.dumps({"access_token": "gho_token", "token_type": "bearer"}).encode()
        with patch(
            "sync.github_client.urllib.request.urlopen",
            side_effect=[FakeResponse(pending), FakeResponse(granted)],
        ) as mock_urlopen:
            with patch("sync.github_client.time.sleep") as mock_sleep:
                token = _client().exchange_device_code("client-123", "dc", interval=5)

        self.assertEqual(token, "gho_token")
        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once_with(5)

    def test_exchange_device_flow_slow_down_increases_interval(self) -> None:
        slow = json.dumps({"error": "slow_down", "error_description": "too fast"}).encode()
        granted = json.dumps({"access_token": "gho_token"}).encode()
        with patch(
            "sync.github_client.urllib.request.urlopen",
            side_effect=[FakeResponse(slow), FakeResponse(slow), FakeResponse(granted)],
        ):
            with patch("sync.github_client.time.sleep") as mock_sleep:
                token = _client().exchange_device_code("client-123", "dc", interval=5)

        self.assertEqual(token, "gho_token")
        self.assertEqual(mock_sleep.call_count, 2)
        self.assertEqual(mock_sleep.call_args_list[0].args[0], 10)

    def test_exchange_device_flow_expired_raises_with_description(self) -> None:
        expired = json.dumps({"error": "expired_token", "error_description": "code has expired"}).encode()
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(expired)):
            with self.assertRaises(SyncError) as ctx:
                _client().exchange_device_code("client-123", "dc")
        self.assertIn("code has expired", str(ctx.exception))

    def test_exchange_device_flow_times_out_on_pending(self) -> None:
        pending = json.dumps({"error": "authorization_pending"}).encode()
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(pending)):
            with patch("sync.github_client.time.sleep"):
                with patch("sync.github_client.time.monotonic", side_effect=[0, 601]):
                    with self.assertRaises(SyncError) as ctx:
                        _client().exchange_device_code("client-123", "dc", timeout=600)
        self.assertIn("Timed out", str(ctx.exception))

    def test_exchange_device_flow_too_many_slow_down(self) -> None:
        slow = json.dumps({"error": "slow_down"}).encode()
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(slow)):
            with patch("sync.github_client.time.sleep"):
                with patch("sync.github_client.time.monotonic", return_value=0):
                    with self.assertRaises(SyncError) as ctx:
                        _client().exchange_device_code("client-123", "dc")
        self.assertIn("too many slow_down responses", str(ctx.exception))

    def test_exchange_device_flow_http_error_raises(self) -> None:
        with patch(
            "sync.github_client.urllib.request.urlopen",
            side_effect=_http_error(400, b'{"error":"invalid_grant"}'),
        ):
            with self.assertRaises(SyncError) as ctx:
                _client().exchange_device_code("client-123", "dc")
        self.assertIn("HTTP 400", str(ctx.exception))


class RepositoryTests(unittest.TestCase):
    def test_list_user_repositories_filters_to_owned_and_query(self) -> None:
        payload = [
            {"full_name": "owner/alpha", "name": "alpha"},
            {"full_name": "owner/beta", "name": "beta"},
            {"full_name": 123, "name": "broken"},
            "not-a-dict",
        ]
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(json.dumps(payload).encode())):
            repos = _client().list_user_repositories(query="ALPHA")

        self.assertEqual(repos, [{"full_name": "owner/alpha", "name": "alpha"}])

    def test_list_user_repositories_rejects_non_list(self) -> None:
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(b'{"repos":[]}')):
            with self.assertRaises(SyncError) as ctx:
                _client().list_user_repositories()
        self.assertIn("was not a list", str(ctx.exception))

    def test_create_repository_builds_payload(self) -> None:
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(b'{"full_name":"owner/new"}')) as mock_urlopen:
            created = _client().create_repository("new", private=True, description="  my repo  ")

        self.assertEqual(created["full_name"], "owner/new")
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.github.com/user/repos")
        sent = json.loads(request.data)
        self.assertEqual(sent, {"name": "new", "private": True, "auto_init": True, "description": "my repo"})

    def test_create_repository_incomplete_payload_raises(self) -> None:
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(b'{"id":1}')):
            with self.assertRaises(SyncError) as ctx:
                _client().create_repository("new")
        self.assertIn("incomplete payload", str(ctx.exception))

    def test_probe_repository_success(self) -> None:
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(b'{"full_name":"owner/repo"}')):
            ok, message = _client().probe_repository()
        self.assertTrue(ok)
        self.assertEqual(message, "Repository probe succeeded")

    def test_probe_repository_auth_error(self) -> None:
        with patch("sync.github_client.urllib.request.urlopen", side_effect=_http_error(401, b'{"message":"bad creds"}')):
            ok, message = _client().probe_repository()
        self.assertFalse(ok)
        self.assertEqual(message, "Repository probe failed with an auth error")

    def test_probe_repository_not_found(self) -> None:
        with patch("sync.github_client.urllib.request.urlopen", side_effect=_http_error(404, b'{"message":"gone"}')):
            ok, message = _client().probe_repository()
        self.assertFalse(ok)
        self.assertEqual(message, "Repository probe failed with a not-found error")

    def test_probe_repository_incomplete_payload(self) -> None:
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(b'{"id":1}')):
            ok, message = _client().probe_repository()
        self.assertFalse(ok)
        self.assertEqual(message, "Repository probe returned incomplete payload")


class ContentTests(unittest.TestCase):
    def test_get_content_returns_none_on_404(self) -> None:
        with patch("sync.github_client.urllib.request.urlopen", side_effect=_http_error(404, b'{"message":"no"}')):
            self.assertIsNone(_client().get_content("a/b.yaml"))
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(b'{"sha":"s1"}')):
            self.assertEqual(_client().get_content("a/b.yaml"), {"sha": "s1"})

    def test_get_content_raises_on_non_404(self) -> None:
        # The 5xx backoff is 1+2+4+8s. Patch the sleep: this asserts the error,
        # not that the test suite is slow.
        with patch("sync.github_client.time.sleep"):
            with patch("sync.github_client.urllib.request.urlopen", side_effect=_http_error(500, b'{"message":"boom"}')):
                with self.assertRaises(SyncError):
                    _client().get_content("a/b.yaml")

    def test_put_content_encodes_base64(self) -> None:
        with patch(
            "sync.github_client.urllib.request.urlopen",
            return_value=FakeResponse(b'{"content":{}}'),
        ) as mock_urlopen:
            result = _client().put_content("a/b.yaml", b"hello", "sync message")

        self.assertEqual(result, {"content": {}})
        self.assertEqual(mock_urlopen.call_count, 1)
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.method, "PUT")
        self.assertIn("a%2Fb.yaml", request.full_url)
        self.assertEqual(json.loads(request.data)["content"], base64.b64encode(b"hello").decode("ascii"))
        self.assertEqual(json.loads(request.data)["branch"], "main")

    def test_put_content_retries_sha_conflict_with_refreshed_sha(self) -> None:
        client = _client()
        sequence = [
            SyncError("GitHub API error HTTP 409 for PUT x: conflict"),
            {"sha": "fresh-sha"},
            {"content": {}},
        ]
        with patch("sync.github_client.time.sleep") as mock_sleep:
            with patch.object(GitHubClient, "_request_json", side_effect=sequence) as mock_request:
                result = client.put_content("a/b.yaml", b"hello", "m", sha="stale")

        self.assertEqual(result, {"content": {}})
        self.assertEqual(mock_request.call_count, 3)
        methods = [call.args[0] for call in mock_request.call_args_list]
        self.assertEqual(methods, ["PUT", "GET", "PUT"])
        self.assertEqual(mock_request.call_args_list[2].kwargs["payload"]["sha"], "fresh-sha")
        mock_sleep.assert_called_once()

    def test_put_content_recovers_from_422_missing_sha(self) -> None:
        client = _client()
        sequence = [
            SyncError(
                'GitHub API error HTTP 422 for PUT .github-config-sync-addon.json: '
                '{"message":"Invalid request.\\n\\n\\"sha\\" wasn\'t supplied.","status":"422"}'
            ),
            {"sha": "fresh-sha"},
            {"content": {}},
        ]
        with patch("sync.github_client.time.sleep") as mock_sleep:
            with patch.object(GitHubClient, "_request_json", side_effect=sequence) as mock_request:
                result = client.put_content(".github-config-sync-addon.json", b"{}", "sync: add repo marker")

        self.assertEqual(result, {"content": {}})
        self.assertEqual(mock_request.call_count, 3)
        methods = [call.args[0] for call in mock_request.call_args_list]
        self.assertEqual(methods, ["PUT", "GET", "PUT"])
        self.assertEqual(mock_request.call_args_list[2].kwargs["payload"]["sha"], "fresh-sha")
        mock_sleep.assert_called_once()

    def test_write_repo_marker_passes_existing_sha(self) -> None:
        client = _client()
        with patch.object(GitHubClient, "get_content", return_value={"sha": "marker-sha"}) as mock_get:
            with patch.object(GitHubClient, "put_content", return_value={"content": {}}) as mock_put:
                result = client.write_repo_marker()

        self.assertEqual(result, {"content": {}})
        mock_get.assert_called_once_with(".github-config-sync-addon.json")
        mock_put.assert_called_once()
        kwargs = mock_put.call_args.kwargs
        self.assertEqual(kwargs["sha"], "marker-sha")
        self.assertEqual(kwargs["message"], "sync: add repo marker")
        self.assertEqual(
            kwargs["content"],
            json.dumps({"created_by": "github-config-sync-addon"}, indent=2, sort_keys=True).encode("utf-8"),
        )

    def test_write_repo_marker_without_existing_file_omits_sha(self) -> None:
        client = _client()
        with patch.object(GitHubClient, "get_content", return_value=None) as mock_get:
            with patch.object(GitHubClient, "put_content", return_value={"content": {}}) as mock_put:
                client.write_repo_marker({"created_by": "custom"})

        mock_get.assert_called_once_with(".github-config-sync-addon.json")
        self.assertIsNone(mock_put.call_args.kwargs["sha"])
        self.assertEqual(mock_put.call_args.kwargs["content"],
                         json.dumps({"created_by": "custom"}, indent=2, sort_keys=True).encode("utf-8"))

    def test_put_content_sha_conflict_persists_and_raises(self) -> None:
        client = _client()
        conflict = SyncError("GitHub API error HTTP 409 for PUT x: conflict")
        sequence = [
            conflict, {"sha": "s1"},
            conflict, {"sha": "s2"},
            conflict, {"sha": "s3"},
        ]
        with patch("sync.github_client.time.sleep"):
            with patch.object(GitHubClient, "_request_json", side_effect=sequence):
                with self.assertRaises(SyncError) as ctx:
                    client.put_content("a/b.yaml", b"hello", "m", sha="stale")
        self.assertIn("HTTP 409", str(ctx.exception))

    def test_delete_content_refreshes_sha_on_conflict(self) -> None:
        client = _client()
        sequence = [
            SyncError("GitHub API error HTTP 409 for DELETE x: conflict"),
            {"sha": "fresh-sha"},
            {"deleted": True},
        ]
        with patch("sync.github_client.time.sleep"):
            with patch.object(GitHubClient, "_request_json", side_effect=sequence) as mock_request:
                result = client.delete_content("a/b.yaml", "stale", "remove")

        self.assertEqual(result, {"deleted": True})
        self.assertEqual(mock_request.call_args_list[2].kwargs["payload"]["sha"], "fresh-sha")
        methods = [call.args[0] for call in mock_request.call_args_list]
        self.assertEqual(methods, ["DELETE", "GET", "DELETE"])

    def test_delete_content_missing_after_conflict_raises(self) -> None:
        client = _client()
        sequence = [
            SyncError("GitHub API error HTTP 409 for DELETE x: conflict"),
            None,
        ]
        with patch("sync.github_client.time.sleep"):
            with patch.object(GitHubClient, "_request_json", side_effect=sequence):
                with self.assertRaises(SyncError) as ctx:
                    client.delete_content("a/b.yaml", "stale", "remove")
        self.assertIn("HTTP 409", str(ctx.exception))

    def test_list_directory_contents_handles_404_and_filters(self) -> None:
        with patch("sync.github_client.urllib.request.urlopen", side_effect=_http_error(404, b'{}')):
            self.assertEqual(_client().list_directory_contents("missing"), [])
        payload = [{"path": "a", "type": "file"}, {"path": "b"}]
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(json.dumps(payload).encode())):
            self.assertEqual(_client().list_directory_contents(), payload)
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(b'{"not":"a list"}')):
            with self.assertRaises(SyncError):
                _client().list_directory_contents()


class GitTreeTests(unittest.TestCase):
    def test_branch_head_sha(self) -> None:
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(b'{"object":{"sha":"abc123"}}')) as mock_urlopen:
            self.assertEqual(_client().get_branch_head_sha(), "abc123")
        self.assertIn("/git/ref/heads/main", mock_urlopen.call_args.args[0].full_url)
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(b'{"object":{}}')):
            with self.assertRaises(SyncError) as ctx:
                _client().get_branch_head_sha()
        self.assertIn("incomplete", str(ctx.exception))

    def test_commit_tree_and_new_tree_and_commit_and_ref(self) -> None:
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(b'{"tree":{"sha":"tree1"}}')):
            self.assertEqual(_client().get_commit_tree_sha("commit1"), "tree1")

        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(b'{"sha":"new-tree"}')) as mock_urlopen:
            result = _client().create_git_tree(base_tree="base1", tree=[{"path": "a", "mode": "100644"}])
        self.assertEqual(result, {"sha": "new-tree"})
        sent = json.loads(mock_urlopen.call_args.args[0].data)
        self.assertEqual(sent, {"base_tree": "base1", "tree": [{"path": "a", "mode": "100644"}]})

        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(b'{"sha":"commit2"}')) as mock_urlopen:
            result = _client().create_git_commit("msg", "tree1", "parent1")
        sent = json.loads(mock_urlopen.call_args.args[0].data)
        self.assertEqual(sent, {"message": "msg", "tree": "tree1", "parents": ["parent1"]})

        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(b'{"ref":"refs/heads/main"}')) as mock_urlopen:
            _client().update_branch_ref("commit2")
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.method, "PATCH")
        self.assertEqual(json.loads(request.data), {"sha": "commit2", "force": True})


class ReleaseTests(unittest.TestCase):
    def test_create_release_sends_stable_payload(self) -> None:
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(b'{"id":1}')) as mock_urlopen:
            result = _client().create_release("v1.0.0", "1.0.0", "notes")
        self.assertEqual(result, {"id": 1})
        sent = json.loads(mock_urlopen.call_args.args[0].data)
        self.assertEqual(sent["tag_name"], "v1.0.0")
        self.assertFalse(sent["draft"])
        self.assertFalse(sent["prerelease"])

    def test_list_releases_filters_to_dicts(self) -> None:
        payload = [{"tag_name": "v1"}, {"tag_name": "v2"}, "junk"]
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(json.dumps(payload).encode())):
            self.assertEqual(_client().list_releases(), [{"tag_name": "v1"}, {"tag_name": "v2"}])
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(b'{"not":true}')):
            self.assertEqual(_client().list_releases(), [])

    def test_delete_release_and_delete_tag(self) -> None:
        with patch("sync.github_client.urllib.request.urlopen", return_value=FakeResponse(b"")) as mock_urlopen:
            _client().delete_release(42)
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.method, "DELETE")
        self.assertIn("/releases/42", request.full_url)

        with patch("sync.github_client.urllib.request.urlopen", side_effect=_http_error(404, b'{}')) as mock_urlopen:
            _client().delete_tag("v1.0.0")
        mock_urlopen.assert_called_once()

        with patch("sync.github_client.time.sleep"):
            with patch("sync.github_client.urllib.request.urlopen", side_effect=_http_error(500, b'{}')):
                with self.assertRaises(SyncError):
                    _client().delete_tag("v1.0.0")


class HelperTests(unittest.TestCase):
    def test_is_sha_conflict(self) -> None:
        self.assertTrue(github_client._is_sha_conflict(SyncError("HTTP 409 for x")))
        self.assertTrue(github_client._is_sha_conflict(SyncError('"status":"409"')))
        self.assertTrue(github_client._is_sha_conflict(SyncError('"status": "409"')))
        self.assertTrue(
            github_client._is_sha_conflict(
                SyncError('"status":"422" - "sha" wasn\'t supplied.')
            )
        )
        self.assertTrue(
            github_client._is_sha_conflict(
                SyncError('{"message":"Invalid request.\\n\\n\\"sha\\" wasn\'t supplied.","status":"422"}')
            )
        )
        self.assertFalse(github_client._is_sha_conflict(SyncError("HTTP 404 for x")))
        self.assertFalse(
            github_client._is_sha_conflict(
                SyncError('{"message":"wrong branch","status":"422"}')
            )
        )

    def test_parse_rate_limit_wait_uses_reset_header(self) -> None:
        with patch("sync.github_client.time.time", return_value=0):
            err = _http_error(403, b'{}', reset="60")
            wait = github_client._parse_rate_limit_wait(err, attempt=0)
        self.assertEqual(wait, 60.0)

    def test_parse_rate_limit_wait_caps_at_60(self) -> None:
        with patch("sync.github_client.time.time", return_value=0):
            err = _http_error(403, b'{}', reset="9999999999")
            wait = github_client._parse_rate_limit_wait(err, attempt=3)
        self.assertEqual(wait, 60.0)

    def test_parse_rate_limit_wait_falls_back_to_exponential(self) -> None:
        self.assertEqual(github_client._parse_rate_limit_wait(_http_error(403, b'{}'), attempt=0), 60.0)
        self.assertEqual(github_client._parse_rate_limit_wait(_http_error(403, b'{}'), attempt=1), 60.0)
        self.assertEqual(github_client._parse_rate_limit_wait(_http_error(403, b'{}'), attempt=3), 60.0)


class GateReleaseTests(unittest.TestCase):
    """Waiters must not all fire at GitHub on the same instant.

    Releasing them together is what draws a secondary rate limit, which re-arms
    the gate and starts the cycle again - so the backoff could never converge.
    """

    def test_the_release_offset_stays_within_its_window(self) -> None:
        for _ in range(50):
            offset = github_client._thread_stagger()
            self.assertGreaterEqual(offset, 0.0)
            self.assertLess(offset, github_client._GATE_STAGGER_MAX)

    def test_concurrent_threads_get_differing_offsets(self) -> None:
        offsets: list[float] = []
        lock = threading.Lock()

        def sample() -> None:
            value = github_client._thread_stagger()
            with lock:
                offsets.append(value)

        threads = [threading.Thread(target=sample) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(offsets), 8)
        # Every live thread must get its own slot. This is the assertion that
        # catches a stagger which reads as present but does nothing: a version
        # keyed on get_ident() % 16 returns 0.0 for every thread on aarch64,
        # because that value is pointer-aligned.
        self.assertEqual(len(set(offsets)), 8)

    def test_the_gate_wait_cannot_spin_forever(self) -> None:
        """A sleep that returns early must not hang the caller in a tight loop."""
        client = _client()
        client.gate.open(3600.0, reason="test")

        with patch("sync.github_client.time.sleep") as mock_sleep:
            client.gate.wait_out()

        self.assertEqual(mock_sleep.call_count, github_client._GATE_MAX_ROUNDS)


class GateIsolationTests(unittest.TestCase):
    """Auxiliary work must not be able to stall authenticated work.

    The add-on's update check runs unauthenticated against a public repository,
    so it shares GitHub's 60/hour per-IP budget rather than the authenticated
    one. When that budget was spent it opened a half-hour backoff that a
    module-global gate applied to every client in the process, and a fully
    authenticated sync would sit behind it reporting itself as running while
    waiting on a limit it had not hit and could not clear.
    """

    def test_a_gate_opened_by_one_client_does_not_reach_another(self) -> None:
        auxiliary = _client("MJP-76/GithubConfigSync")
        syncing = _client("owner/config")
        auxiliary.gate.open(3600.0, reason="unauthenticated budget spent")

        self.assertAlmostEqual(auxiliary.gate.wait(), 3600.0, delta=1.0)
        self.assertEqual(syncing.gate.wait(), 0.0)

    def test_an_isolated_client_gives_up_instead_of_sleeping(self) -> None:
        client = GitHubClient(
            repository="owner/repo", branch="main", token="", isolate_rate_limits=True
        )
        with patch("sync.github_client.time.sleep") as mock_sleep:
            with patch(
                "sync.github_client.urllib.request.urlopen",
                side_effect=_http_error(403, b'{"message":"API rate limit exceeded"}'),
            ) as mock_urlopen:
                with self.assertRaises(SyncError) as ctx:
                    client._request_any("GET", "https://api.github.com/x")

        # One attempt, no sleep, and no shared gate left for anyone else.
        self.assertEqual(mock_urlopen.call_count, 1)
        self.assertEqual(mock_sleep.call_count, 0)
        self.assertEqual(client.gate.wait(), 0.0)
        self.assertIn("rate limit", str(ctx.exception))

    def test_a_normal_client_still_backs_off_and_retries(self) -> None:
        """Isolation is opt-in. The syncing client must keep its retry ceiling."""
        client = _client()
        with patch("sync.github_client.time.sleep"):
            with patch(
                "sync.github_client.urllib.request.urlopen",
                side_effect=_http_error(429, b"{}", retry_after="900"),
            ) as mock_urlopen:
                with self.assertRaises(SyncError):
                    client._request_any("GET", "https://api.github.com/x")

        self.assertEqual(mock_urlopen.call_count, 4)
        self.assertGreater(client.gate.wait(), 0.0)


class UpdateCheckClientTests(unittest.TestCase):
    """The production wiring, so the isolation flag cannot go missing quietly."""

    def test_the_update_check_client_is_unauthenticated_and_isolated(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "server.py").read_text(
            encoding="utf-8"
        )
        call = source[source.index("releases = client.list_releases") - 400 : source.index("releases = client.list_releases")]
        self.assertIn("token=\"\"", call)
        self.assertIn("isolate_rate_limits=True", call)


class RepoMarkerWriteTests(unittest.TestCase):
    """A sync that changed nothing must not commit anything.

    The contents API creates a commit whether or not the bytes differ, so an
    unconditional PUT meant every idle run left a "sync: add repo marker"
    commit behind - the no-op sync dirtying the history it had just left clean.
    """

    def _client(self) -> GitHubClient:
        return GitHubClient(repository="owner/repo", branch="main", token="token")

    def test_identical_marker_content_is_not_written_again(self) -> None:
        client = self._client()
        desired = json.dumps(
            {"created_by": "github-config-sync-addon", "repository": "owner/repo"},
            indent=2, sort_keys=True,
        ).encode()
        with patch.object(GitHubClient, "get_content",
                          return_value={"sha": "abc", "content": base64.b64encode(desired).decode()}):
            with patch.object(GitHubClient, "put_content") as put:
                result = client.write_repo_marker(
                    {"created_by": "github-config-sync-addon", "repository": "owner/repo"}
                )

        put.assert_not_called()
        self.assertEqual(result["sha"], "abc")

    def test_different_marker_content_is_written(self) -> None:
        client = self._client()
        with patch.object(GitHubClient, "get_content",
                          return_value={"sha": "abc", "content": base64.b64encode(b"{}").decode()}):
            with patch.object(GitHubClient, "put_content") as put:
                client.write_repo_marker(
                    {"created_by": "github-config-sync-addon", "repository": "owner/repo"}
                )

        put.assert_called_once()
        self.assertEqual(put.call_args.kwargs["sha"], "abc")

    def test_a_missing_marker_is_written(self) -> None:
        client = self._client()
        with patch.object(GitHubClient, "get_content", return_value=None):
            with patch.object(GitHubClient, "put_content") as put:
                client.write_repo_marker()

        put.assert_called_once()
        self.assertIsNone(put.call_args.kwargs["sha"])

    def test_undecodable_remote_content_falls_through_to_a_write(self) -> None:
        """A marker that cannot be compared must be rewritten, never trusted."""
        client = self._client()
        with patch.object(GitHubClient, "get_content",
                          return_value={"sha": "abc", "content": "not-base64!!"}):
            with patch.object(GitHubClient, "put_content") as put:
                client.write_repo_marker()

        put.assert_called_once()
