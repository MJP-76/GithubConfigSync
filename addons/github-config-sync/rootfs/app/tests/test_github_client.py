from __future__ import annotations

import base64
import io
import json
import sys
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
    def __init__(self, body: bytes = b"") -> None:
        self._body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def _http_error(code: int, body: bytes = b"{}", reset: str | None = None) -> urllib.error.HTTPError:
    headers = Message()
    if reset is not None:
        headers["X-RateLimit-Reset"] = reset
    return urllib.error.HTTPError("https://api.github.com/x", code, "msg", headers, io.BytesIO(body))


def _client(repository: str = "owner/repo") -> GitHubClient:
    return GitHubClient(repository=repository, branch="main", token="token")


class TransportTests(unittest.TestCase):
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
        waiting = mock_sleep.call_args.args[0]
        self.assertGreaterEqual(waiting, 1.0)
        self.assertLessEqual(waiting, 300)

    def test_rate_limit_without_reset_exhausts(self) -> None:
        client = _client()
        errors = [_http_error(403, b'{"message":"API rate limit exceeded"}') for _ in range(5)]
        with patch("sync.github_client.time.sleep"):
            with patch("sync.github_client.urllib.request.urlopen", side_effect=errors):
                with self.assertRaises(SyncError) as ctx:
                    client._request_any("GET", "https://api.github.com/x")
        self.assertIn("rate limit exceeded after 5 retries", str(ctx.exception))

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