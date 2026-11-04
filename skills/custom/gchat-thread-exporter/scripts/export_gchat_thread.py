#!/usr/bin/env python3
"""Export a Google Chat thread (messages + images/attachments) to Markdown.

Zero mandatory third-party dependencies (uses Python stdlib; uses `requests` automatically
if installed, otherwise falls back to `urllib.request`).

Supported modes:
1. Google Chat REST API v1 with OAuth 2.0 Desktop credentials (`credentials.json` -> `token.json`)
2. Browser JSON dump conversion (`--from-browser-json`) paired with `browser_extract.js`
   for personal `@gmail.com` accounts or admin-restricted Workspace orgs.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import html
import http.server
import json
import mimetypes
import os
import re
import secrets
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "gchat-thread-exporter"
DEFAULT_CREDENTIALS_PATH = DEFAULT_CONFIG_DIR / "credentials.json"
DEFAULT_TOKEN_PATH = DEFAULT_CONFIG_DIR / "token.json"
DEFAULT_PENDING_OAUTH_PATH = DEFAULT_CONFIG_DIR / "pending_oauth.json"

BASE_SCOPES = [
    "https://www.googleapis.com/auth/chat.messages.readonly",
    "https://www.googleapis.com/auth/chat.spaces.readonly",
    "https://www.googleapis.com/auth/directory.readonly",
    "https://www.googleapis.com/auth/contacts.readonly",
]
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"

CHAT_API_BASE = "https://chat.googleapis.com/v1"
PEOPLE_API_BASE = "https://people.googleapis.com/v1"
DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"


# ---------------------------------------------------------------------------
# HTTP Helper (uses `requests` if available, else `urllib.request`)
# ---------------------------------------------------------------------------

try:
    import requests as _requests  # type: ignore
except ImportError:
    _requests = None


class HttpError(RuntimeError):
    def __init__(self, status: int, body: str, url: str) -> None:
        self.status = status
        self.body = body
        self.url = url
        super().__init__(f"HTTP {status} for {url}: {body[:500]}")


def http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, str], bytes]:
    req_headers = dict(headers or {})
    if _requests is not None:
        resp = _requests.request(
            method=method,
            url=url,
            headers=req_headers,
            data=data,
            timeout=timeout,
        )
        norm_headers = {k.lower(): v for k, v in resp.headers.items()}
        if resp.status_code >= 400:
            raise HttpError(resp.status_code, resp.text, url)
        return resp.status_code, norm_headers, resp.content

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            norm_headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, norm_headers, raw
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise HttpError(exc.code, err_body, url) from exc


def http_get_json(url: str, access_token: str, timeout: int = 30) -> dict[str, Any]:
    _, _, raw = http_request(
        "GET",
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        timeout=timeout,
    )
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def http_get_bytes(url: str, access_token: str | None = None, timeout: int = 60) -> tuple[bytes, str]:
    headers: dict[str, str] = {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    _, resp_headers, raw = http_request("GET", url, headers=headers, timeout=timeout)
    content_type = resp_headers.get("content-type", "").split(";")[0].strip().lower()
    return raw, content_type


# ---------------------------------------------------------------------------
# URL & Resource Identifier Parsing
# ---------------------------------------------------------------------------


def parse_gchat_target(raw_input: str) -> dict[str, Any]:
    """Extract space_id, thread_id, and optional message_id from Google Chat URLs or resource names.

    Supported formats:
    - https://chat.google.com/u/0/app/chat/AAAA9sg0Pfc/topic/K2bBfiSrccc
    - https://chat.google.com/app/chat/AAAA9sg0Pfc/topic/K2bBfiSrccc
    - https://chat.google.com/u/0/app/chat/AAAA9sg0Pfc/thread/K2bBfiSrccc
    - https://chat.google.com/u/0/app/chat/AAAA9sg0Pfc/message/Mxyz123
    - https://mail.google.com/chat/u/0/#chat/space/AAAA9sg0Pfc/K2bBfiSrccc
    - https://chat.google.com/room/AAAA9sg0Pfc/K2bBfiSrccc[/Mxyz123]
    - spaces/AAAA9sg0Pfc/threads/K2bBfiSrccc
    - spaces/AAAA9sg0Pfc/messages/Mxyz123
    """
    value = raw_input.strip()
    if not value:
        raise ValueError("Empty Google Chat URL or identifier.")

    # Direct API resource name: spaces/{space}/threads/{thread}
    m = re.match(r"^spaces/([^/\s]+)/threads/([^/\s?#]+)$", value)
    if m:
        space_id, thread_id = m.group(1), m.group(2)
        return _build_target(value, space_id, thread_id)

    # Direct API message resource name: spaces/{space}/messages/{message}
    m = re.match(r"^spaces/([^/\s]+)/messages/([^/\s?#]+)$", value)
    if m:
        space_id, msg_id = m.group(1), m.group(2)
        return _build_target(value, space_id, msg_id, message_id=msg_id, is_message_lookup=True)

    parsed = urllib.parse.urlparse(value)
    combined_path = parsed.path or ""
    if parsed.fragment:
        combined_path = f"{combined_path}/{parsed.fragment.lstrip('/')}"

    # Pattern 1: /app/chat/{space}/(topic|thread|message)/{id}
    m = re.search(
        r"/app/(?:chat|space)/([^/\s?#]+)/(topic|thread|message)/([^/\s?#]+)",
        combined_path,
    )
    if m:
        space_id, kind, item_id = m.group(1), m.group(2), m.group(3)
        is_msg = kind == "message"
        return _build_target(
            value,
            space_id,
            item_id,
            message_id=item_id if is_msg else None,
            is_message_lookup=is_msg,
        )

    # Pattern 2: Gmail / Hash route: #chat/space/{space}/{thread}[/{message}]
    m = re.search(
        r"chat/(?:space|room)/([^/\s?#]+)/([^/\s?#]+)(?:/([^/\s?#]+))?",
        combined_path,
    )
    if m:
        space_id, thread_id, msg_id = m.group(1), m.group(2), m.group(3)
        return _build_target(value, space_id, thread_id, message_id=msg_id)

    # Pattern 3: Legacy /room/{space}/{thread}[/{message}] or /app/chat/{space}/{thread}
    m = re.search(
        r"/(?:room|space|app/chat)/([^/\s?#]+)/([^/\s?#]+)(?:/([^/\s?#]+))?",
        combined_path,
    )
    if m and m.group(2) not in {"topic", "thread", "message"}:
        space_id, thread_id, msg_id = m.group(1), m.group(2), m.group(3)
        return _build_target(value, space_id, thread_id, message_id=msg_id)

    # Pattern 4: Query param ?thread=... or ?topic=... on a space URL
    qs = urllib.parse.parse_qs(parsed.query)
    m_space = re.search(r"/(?:app/chat|space|room)/([^/\s?#]+)", combined_path)
    if m_space:
        space_id = m_space.group(1)
        t_param = (qs.get("thread") or qs.get("topic") or qs.get("threadId") or [None])[0]
        if t_param:
            t_clean = t_param.split("/")[-1]
            return _build_target(value, space_id, t_clean)
        raise ValueError(
            f"Found space '{space_id}' in URL, but no thread/topic ID. "
            "Open the specific thread ('Copy link to thread' or /topic/<ID>) and pass that URL."
        )

    raise ValueError(
        f"Cannot parse Google Chat space and thread ID from: {raw_input!r}. "
        "Expected URL like https://chat.google.com/u/0/app/chat/<SPACE>/topic/<THREAD> "
        "or resource name spaces/<SPACE>/threads/<THREAD>."
    )


def _build_target(
    original: str,
    space_id: str,
    thread_id: str,
    *,
    message_id: str | None = None,
    is_message_lookup: bool = False,
) -> dict[str, Any]:
    return {
        "input": original,
        "space_id": space_id,
        "thread_id": thread_id,
        "message_id": message_id,
        "is_message_lookup": is_message_lookup,
        "space_name": f"spaces/{space_id}",
        "thread_name": f"spaces/{space_id}/threads/{thread_id}",
    }


# ---------------------------------------------------------------------------
# OAuth 2.0 Desktop Flow (PKCE + Local Loopback OR Manual Redirect Paste)
# ---------------------------------------------------------------------------


def _secure_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        os.chmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        os.replace(tmp_name, path)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def load_client_config(credentials_path: Path) -> dict[str, Any]:
    if not credentials_path.exists():
        raise FileNotFoundError(
            f"OAuth credentials file not found at: {credentials_path}"
        )
    raw = json.loads(credentials_path.read_text(encoding="utf-8"))
    block = raw.get("installed") or raw.get("web")
    if not block or "client_id" not in block or "client_secret" not in block:
        raise ValueError(
            f"Invalid OAuth client file at {credentials_path}: expected Google OAuth "
            "'Desktop app' JSON containing 'installed.client_id' and 'installed.client_secret'."
        )
    return block


def generate_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_scopes(with_drive: bool = False) -> list[str]:
    scopes = list(BASE_SCOPES)
    if with_drive and DRIVE_SCOPE not in scopes:
        scopes.append(DRIVE_SCOPE)
    return scopes


def check_auth_status(credentials_path: Path, token_path: Path) -> dict[str, Any]:
    has_creds = credentials_path.exists()
    has_token = token_path.exists()
    token_valid = False
    has_refresh = False
    scopes: list[str] = []
    error_detail: str | None = None

    if has_token:
        try:
            tok = json.loads(token_path.read_text(encoding="utf-8"))
            scopes = tok.get("scopes") or (tok.get("scope", "").split() if tok.get("scope") else [])
            has_refresh = bool(tok.get("refresh_token"))
            expires_at = tok.get("expires_at", 0)
            now = dt.datetime.now(dt.timezone.utc).timestamp()
            token_valid = bool(tok.get("access_token")) and (expires_at > now + 60 or has_refresh)
        except Exception as exc:
            error_detail = f"Failed to parse token file: {exc}"

    return {
        "ready": token_valid,
        "credentials_path": str(credentials_path),
        "credentials_found": has_creds,
        "token_path": str(token_path),
        "token_found": has_token,
        "token_usable": token_valid,
        "has_refresh_token": has_refresh,
        "scopes": scopes,
        "error": error_detail,
    }


def create_manual_auth_url(
    credentials_path: Path,
    pending_path: Path,
    scopes: list[str],
    redirect_port: int = 8765,
) -> dict[str, str]:
    client = load_client_config(credentials_path)
    verifier, challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(24)
    redirect_uri = f"http://127.0.0.1:{redirect_port}"
    auth_uri = client.get("auth_uri", "https://accounts.google.com/o/oauth2/v2/auth")

    params = {
        "client_id": client["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = f"{auth_uri}?{urllib.parse.urlencode(params)}"
    _secure_write_json(
        pending_path,
        {
            "state": state,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "scopes": scopes,
            "credentials_path": str(credentials_path),
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
    )
    return {"auth_url": url, "redirect_uri": redirect_uri, "pending_path": str(pending_path)}


def _exchange_code_for_token(
    client: dict[str, Any],
    code: str,
    redirect_uri: str,
    code_verifier: str,
    scopes: list[str],
) -> dict[str, Any]:
    token_uri = client.get("token_uri", "https://oauth2.googleapis.com/token")
    form = urllib.parse.urlencode(
        {
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }
    ).encode("utf-8")
    _, _, raw = http_request(
        "POST",
        token_uri,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=form,
    )
    resp = json.loads(raw.decode("utf-8"))
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    expires_in = int(resp.get("expires_in", 3600))
    granted_scopes = resp.get("scope", "").split() or scopes
    return {
        "access_token": resp["access_token"],
        "refresh_token": resp.get("refresh_token"),
        "token_uri": token_uri,
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "scopes": granted_scopes,
        "expires_at": now + expires_in,
    }


def complete_manual_auth(
    redirect_url_or_code: str,
    pending_path: Path,
    token_path: Path,
    credentials_path: Path | None = None,
) -> dict[str, Any]:
    if not pending_path.exists():
        raise FileNotFoundError(
            f"No pending OAuth session at {pending_path}. Run `--print-auth-url` first."
        )
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    creds_file = credentials_path or Path(pending["credentials_path"])
    client = load_client_config(creds_file)

    raw_val = redirect_url_or_code.strip()
    if raw_val.startswith("http://") or raw_val.startswith("https://"):
        parsed = urllib.parse.urlparse(raw_val)
        qs = urllib.parse.parse_qs(parsed.query)
        if "error" in qs:
            raise RuntimeError(f"OAuth authorization returned error: {qs['error'][0]}")
        code = (qs.get("code") or [None])[0]
        state = (qs.get("state") or [None])[0]
        if state and pending.get("state") and state != pending["state"]:
            raise RuntimeError("OAuth state mismatch. Generate a fresh URL with `--print-auth-url`.")
        if not code:
            raise ValueError("No `code=` parameter found in the pasted redirect URL.")
    else:
        code = raw_val

    token_data = _exchange_code_for_token(
        client=client,
        code=code,
        redirect_uri=pending["redirect_uri"],
        code_verifier=pending["code_verifier"],
        scopes=pending["scopes"],
    )
    _secure_write_json(token_path, token_data)
    try:
        pending_path.unlink()
    except OSError:
        pass
    return token_data


def run_interactive_loopback_auth(
    credentials_path: Path,
    token_path: Path,
    scopes: list[str],
    open_browser: bool = True,
    timeout_sec: int = 300,
) -> dict[str, Any]:
    client = load_client_config(credentials_path)
    verifier, challenge = generate_pkce_pair()
    expected_state = secrets.token_urlsafe(24)
    captured: dict[str, str] = {}

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            qs = urllib.parse.parse_qs(parsed.query)
            if "error" in qs:
                captured["error"] = qs["error"][0]
            if "code" in qs:
                captured["code"] = qs["code"][0]
            if "state" in qs:
                captured["state"] = qs["state"][0]

            ok = "code" in captured and "error" not in captured
            status_code = 200 if ok else 400
            msg = (
                "Google Chat Exporter: Xac thuc thanh cong! Ban co the dong tab nay va quay lai Antigravity."
                if ok
                else f"Xac thuc that bai: {captured.get('error', 'Thieu ma code')}"
            )
            body = (
                f"<html><head><meta charset='utf-8'><title>OAuth</title></head>"
                f"<body style='font-family:sans-serif;padding:2rem;'><h2>{html.escape(msg)}</h2></body></html>"
            ).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), CallbackHandler)
    port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}"
    auth_uri = client.get("auth_uri", "https://accounts.google.com/o/oauth2/v2/auth")
    params = {
        "client_id": client["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": expected_state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{auth_uri}?{urllib.parse.urlencode(params)}"
    print(f"\n[OAuth] Open this URL in your browser to authorize:\n\n  {auth_url}\n", file=sys.stderr, flush=True)
    if open_browser:
        try:
            webbrowser.open(auth_url)
        except Exception:
            pass

    print(f"[OAuth] Waiting up to {timeout_sec}s for callback on {redirect_uri} ...", file=sys.stderr, flush=True)
    deadline = dt.datetime.now(dt.timezone.utc).timestamp() + timeout_sec
    try:
        while "code" not in captured and "error" not in captured:
            remaining = deadline - dt.datetime.now(dt.timezone.utc).timestamp()
            if remaining <= 0:
                break
            server.timeout = min(remaining, 5.0)
            server.handle_request()
    finally:
        server.server_close()

    if "error" in captured:
        raise RuntimeError(f"OAuth authorization failed: {captured['error']}")
    if "code" not in captured:
        raise TimeoutError(
            "Timed out waiting for OAuth browser callback. "
            "If running over SSH/remote machine, use `--print-auth-url` and `--complete-auth`."
        )
    if captured.get("state") != expected_state:
        raise RuntimeError("OAuth callback state mismatch.")

    token_data = _exchange_code_for_token(
        client=client,
        code=captured["code"],
        redirect_uri=redirect_uri,
        code_verifier=verifier,
        scopes=scopes,
    )
    _secure_write_json(token_path, token_data)
    return token_data


def get_valid_access_token(
    credentials_path: Path,
    token_path: Path,
    scopes: list[str],
    auto_interactive_auth: bool = False,
) -> str:
    if token_path.exists():
        tok = json.loads(token_path.read_text(encoding="utf-8"))
        now = dt.datetime.now(dt.timezone.utc).timestamp()
        if tok.get("access_token") and tok.get("expires_at", 0) > now + 60:
            return str(tok["access_token"])

        if tok.get("refresh_token"):
            client_id = tok.get("client_id")
            client_secret = tok.get("client_secret")
            token_uri = tok.get("token_uri", "https://oauth2.googleapis.com/token")
            if (not client_id or not client_secret) and credentials_path.exists():
                cfg = load_client_config(credentials_path)
                client_id = cfg["client_id"]
                client_secret = cfg["client_secret"]
            if client_id and client_secret:
                form = urllib.parse.urlencode(
                    {
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": tok["refresh_token"],
                        "grant_type": "refresh_token",
                    }
                ).encode("utf-8")
                _, _, raw = http_request(
                    "POST",
                    token_uri,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    data=form,
                )
                refreshed = json.loads(raw.decode("utf-8"))
                tok["access_token"] = refreshed["access_token"]
                tok["expires_at"] = now + int(refreshed.get("expires_in", 3600))
                if refreshed.get("refresh_token"):
                    tok["refresh_token"] = refreshed["refresh_token"]
                _secure_write_json(token_path, tok)
                return str(tok["access_token"])

    if auto_interactive_auth:
        tok = run_interactive_loopback_auth(credentials_path, token_path, scopes=scopes)
        return str(tok["access_token"])

    raise RuntimeError(
        f"No valid OAuth token found at {token_path}. "
        f"Check credentials at {credentials_path} and run `--auth` (or `--print-auth-url` + `--complete-auth`)."
    )


# ---------------------------------------------------------------------------
# Google Chat API Fetching + Friendly Error Diagnostics
# ---------------------------------------------------------------------------


def explain_google_api_error(exc: HttpError) -> str:
    body_lower = exc.body.lower()
    if exc.status == 404 and "google chat app not found" in body_lower:
        return (
            "Lỗi 404 'Google Chat app not found': Google Cloud Project của bạn đã bật Google Chat API "
            "nhưng CHƯA lưu tab Configuration.\n"
            "Cách sửa nhanh (1 phút):\n"
            "  1. Mở Google Cloud Console > APIs & Services > Enabled APIs & services > Google Chat API\n"
            "  2. Chọn tab 'Configuration'\n"
            "  3. Điền App name (vd: Thread Exporter), Avatar URL (vd: https://fonts.gstatic.com/s/i/short-term/release/googlesymbols/chat/default/24px.svg), Description bất kỳ\n"
            "  4. Ở Connection settings chọn HTTP endpoint URL và điền https://example.com (chỉ để thỏa form)\n"
            "  5. Bấm Save rồi chạy lại lệnh export."
        )
    if exc.status == 403 and ("accessnotconfigured" in body_lower or "has not been used in project" in body_lower):
        return (
            "Lỗi 403: Google Chat API chưa được bật (Enable) trên Google Cloud Project của bạn.\n"
            "Hãy vào APIs & Services > Library > tìm 'Google Chat API' > bấm Enable."
        )
    if exc.status in (400, 403) and (
        "google workspace" in body_lower
        or "not available for consumer" in body_lower
        or "domain policy" in body_lower
        or "admin_policy_enforced" in body_lower
    ):
        return (
            "Google Chat API chỉ hỗ trợ tài khoản Google Workspace (công ty/trường học) và có thể bị "
            "IT Admin giới hạn OAuth. Với tài khoản @gmail.com cá nhân hoặc Workspace bị chặn OAuth, "
            "hãy dùng chế độ dự phòng không cần key: `scripts/browser_extract.js` + `--from-browser-json` "
            "(xem `references/browser-fallback.md`)."
        )
    return f"Google API trả về lỗi HTTP {exc.status}: {exc.body[:600]}"


def fetch_space_metadata(space_name: str, access_token: str) -> dict[str, Any]:
    try:
        return http_get_json(f"{CHAT_API_BASE}/{space_name}", access_token)
    except HttpError:
        return {}


def fetch_thread_messages(target: dict[str, Any], access_token: str) -> tuple[list[dict[str, Any]], str]:
    """Fetch all messages in a thread, handling pagination and message-ID -> thread-ID fallback."""
    space_name = target["space_name"]
    thread_name = target["thread_name"]

    if target.get("is_message_lookup") and target.get("message_id"):
        resolved = _resolve_thread_from_message(space_name, target["message_id"], access_token)
        if resolved:
            thread_name = resolved

    messages = _list_messages_for_thread(space_name, thread_name, access_token)

    # Fallback: if 0 messages returned, the ID in URL might actually be a message ID
    if not messages:
        candidate_msg_id = target.get("message_id") or target["thread_id"]
        resolved = _resolve_thread_from_message(space_name, candidate_msg_id, access_token)
        if resolved and resolved != thread_name:
            thread_name = resolved
            messages = _list_messages_for_thread(space_name, thread_name, access_token)

    messages.sort(key=lambda m: m.get("createTime", ""))
    return messages, thread_name


def _resolve_thread_from_message(space_name: str, message_id: str, access_token: str) -> str | None:
    try:
        msg = http_get_json(f"{CHAT_API_BASE}/{space_name}/messages/{message_id}", access_token)
        return (msg.get("thread") or {}).get("name")
    except HttpError:
        return None


def _list_messages_for_thread(
    space_name: str,
    thread_name: str,
    access_token: str,
) -> list[dict[str, Any]]:
    filter_candidates = [
        f"thread.name = {thread_name}",
        f'thread.name = "{thread_name}"',
    ]
    last_err: HttpError | None = None
    for filter_expr in filter_candidates:
        try:
            all_msgs: list[dict[str, Any]] = []
            page_token: str | None = None
            while True:
                params: dict[str, str] = {
                    "filter": filter_expr,
                    "pageSize": "1000",
                    "orderBy": "createTime asc",
                    "markupSyntax": "MARKUP_SYNTAX_MARKDOWN",
                }
                if page_token:
                    params["pageToken"] = page_token
                url = f"{CHAT_API_BASE}/{space_name}/messages?{urllib.parse.urlencode(params)}"
                data = http_get_json(url, access_token)
                batch = data.get("messages") or []
                all_msgs.extend(batch)
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
            return all_msgs
        except HttpError as exc:
            last_err = exc
            if exc.status == 400 and "invalid_argument" in exc.body.lower():
                continue
            raise
    if last_err:
        raise last_err
    return []


# ---------------------------------------------------------------------------
# User Display Name Resolution (Chat payloads + People API batchGet)
# ---------------------------------------------------------------------------


def resolve_user_names(messages: list[dict[str, Any]], access_token: str) -> dict[str, str]:
    """Map `users/<id>` -> human-readable display name."""
    user_map: dict[str, str] = {}
    unresolved_human_ids: set[str] = set()

    for msg in messages:
        sender = msg.get("sender") or {}
        s_name = sender.get("name", "")
        s_disp = sender.get("displayName") or sender.get("email")
        if s_name and s_disp:
            user_map[s_name] = s_disp
        elif s_name.startswith("users/") and sender.get("type") != "BOT":
            unresolved_human_ids.add(s_name)

        for ann in msg.get("annotations") or []:
            um = (ann.get("userMention") or {}).get("user") or {}
            u_name = um.get("name", "")
            u_disp = um.get("displayName")
            if u_name and u_disp:
                user_map[u_name] = u_disp
            elif u_name.startswith("users/") and um.get("type") != "BOT":
                unresolved_human_ids.add(u_name)

        for raw_field in (msg.get("text") or "", msg.get("formattedText") or ""):
            for uid in re.findall(r"<(users/[0-9A-Za-z._-]+)>", raw_field):
                if uid not in user_map:
                    unresolved_human_ids.add(uid)
            for uid in re.findall(r'data-user=["\'](users/[0-9A-Za-z._-]+)["\']', raw_field):
                if uid not in user_map:
                    unresolved_human_ids.add(uid)

        q_sender = ((msg.get("quotedMessageMetadata") or {}).get("quotedMessageSnapshot") or {}).get("sender", "")
        if q_sender.startswith("users/") and q_sender not in user_map:
            unresolved_human_ids.add(q_sender)

    to_lookup = sorted(uid for uid in unresolved_human_ids if uid not in user_map)
    if not to_lookup:
        return user_map

    # Query Google People API in batches of up to 50 resourceNames
    for idx in range(0, len(to_lookup), 50):
        chunk = to_lookup[idx : idx + 50]
        query_pairs: list[tuple[str, str]] = [("personFields", "names,emailAddresses")]
        for uid in chunk:
            person_id = uid.split("/", 1)[1]
            query_pairs.append(("resourceNames", f"people/{person_id}"))
        url = f"{PEOPLE_API_BASE}/people:batchGet?{urllib.parse.urlencode(query_pairs)}"
        try:
            resp = http_get_json(url, access_token)
        except HttpError:
            break

        for item in resp.get("responses") or []:
            person = item.get("person") or {}
            res_name = item.get("requestedResourceName") or person.get("resourceName") or ""
            if not res_name.startswith("people/"):
                continue
            chat_key = f"users/{res_name.split('/', 1)[1]}"
            names = person.get("names") or []
            emails = person.get("emailAddresses") or []
            label = (
                (names[0].get("displayName") if names else None)
                or (emails[0].get("value") if emails else None)
            )
            if label:
                user_map[chat_key] = label

    return user_map


# ---------------------------------------------------------------------------
# Media & Image Downloading
# ---------------------------------------------------------------------------


def detect_extension(filename: str | None, content_type: str | None, data: bytes) -> str:
    if filename:
        ext = Path(filename).suffix.lower()
        if ext and 1 < len(ext) <= 6 and re.match(r"^\.[a-z0-9]+$", ext):
            return ext

    # Magic bytes inspection
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data.startswith(b"%PDF-"):
        return ".pdf"
    if data.startswith(b"<svg") or b"<svg" in data[:256]:
        return ".svg"

    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip().lower())
        if guessed:
            return ".jpg" if guessed == ".jpe" else guessed
    return ".bin"


def is_image_file(ext: str, content_type: str | None) -> bool:
    if content_type and content_type.lower().startswith("image/"):
        return True
    return ext.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".avif"}


def sanitize_filename(name: str) -> str:
    stem = Path(name).stem
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return (cleaned[:60] or "attachment")


def save_media_bytes(
    data: bytes,
    *,
    images_dir: Path,
    md_dir: Path,
    msg_index: int,
    item_index: int,
    original_name: str | None,
    content_type: str | None,
) -> tuple[str, bool, str]:
    ext = detect_extension(original_name, content_type, data)
    base = sanitize_filename(original_name or ("image" if is_image_file(ext, content_type) else "file"))
    filename = f"{msg_index:03d}_{item_index:02d}_{base}{ext}"
    images_dir.mkdir(parents=True, exist_ok=True)
    dest = images_dir / filename
    dest.write_bytes(data)
    rel_path = os.path.relpath(dest, md_dir).replace(os.sep, "/")
    display_label = original_name or f"{base}{ext}"
    return rel_path, is_image_file(ext, content_type), display_label


def download_message_media(
    msg: dict[str, Any],
    *,
    msg_index: int,
    access_token: str,
    images_dir: Path,
    md_dir: Path,
) -> list[str]:
    """Download attachments, GIFs, Drive files (when permitted), and card images for one message.

    Returns Markdown lines representing all media items on the message.
    """
    rendered_items: list[str] = []
    item_counter = 0

    attachments = msg.get("attachment") or msg.get("attachments") or []
    for att in attachments:
        item_counter += 1
        content_name = att.get("contentName")
        content_type = att.get("contentType")
        data_ref = att.get("attachmentDataRef") or {}
        resource_name = data_ref.get("resourceName")

        # Fetch attachment metadata if resourceName wasn't inline on messages.list
        if not resource_name and att.get("name") and att.get("source") != "DRIVE_FILE":
            try:
                att_meta = http_get_json(f"{CHAT_API_BASE}/{att['name']}", access_token)
                resource_name = (att_meta.get("attachmentDataRef") or {}).get("resourceName")
                content_name = content_name or att_meta.get("contentName")
                content_type = content_type or att_meta.get("contentType")
            except HttpError:
                pass

        if resource_name:
            safe_res = urllib.parse.quote(resource_name, safe="/:@!$&'()*+,;=-._~")
            media_url = f"{CHAT_API_BASE}/media/{safe_res}?alt=media"
            try:
                raw, resp_ct = http_get_bytes(media_url, access_token=access_token)
                rel_path, is_img, label = save_media_bytes(
                    raw,
                    images_dir=images_dir,
                    md_dir=md_dir,
                    msg_index=msg_index,
                    item_index=item_counter,
                    original_name=content_name,
                    content_type=content_type or resp_ct,
                )
                if is_img:
                    rendered_items.append(f"![{label}]({rel_path})")
                else:
                    rendered_items.append(f"- 📎 [{label}]({rel_path})")
                continue
            except HttpError as exc:
                fallback_uri = att.get("downloadUri") or att.get("thumbnailUri")
                note = f"*(Không tải được tệp qua API HTTP {exc.status})*"
                if fallback_uri:
                    rendered_items.append(f"- 📎 [{content_name or 'Tệp đính kèm'}]({fallback_uri}) {note}")
                else:
                    rendered_items.append(f"- 📎 `{content_name or 'attachment'}` {note}")
                continue

        # Google Drive attachment handling
        drive_id = (att.get("driveDataRef") or {}).get("driveFileId")
        if drive_id:
            drive_view_url = f"https://drive.google.com/file/d/{drive_id}/view"
            try:
                raw, resp_ct = http_get_bytes(
                    f"{DRIVE_API_BASE}/files/{urllib.parse.quote(drive_id)}?alt=media",
                    access_token=access_token,
                )
                rel_path, is_img, label = save_media_bytes(
                    raw,
                    images_dir=images_dir,
                    md_dir=md_dir,
                    msg_index=msg_index,
                    item_index=item_counter,
                    original_name=content_name,
                    content_type=content_type or resp_ct,
                )
                if is_img:
                    rendered_items.append(f"![{label}]({rel_path})")
                else:
                    rendered_items.append(f"- 📄 [{label}]({rel_path}) ([Google Drive]({drive_view_url}))")
            except HttpError:
                label = content_name or f"Google Drive ({drive_id})"
                rendered_items.append(f"- 📄 [{label}]({drive_view_url})")
            continue

        fallback_uri = att.get("downloadUri") or att.get("thumbnailUri")
        if fallback_uri:
            rendered_items.append(f"- 📎 [{content_name or 'Tệp đính kèm'}]({fallback_uri})")

    # Attached GIFs
    for gif in msg.get("attachedGifs") or []:
        uri = gif.get("uri")
        if not uri:
            continue
        item_counter += 1
        try:
            raw, resp_ct = http_get_bytes(uri, access_token=None)
            rel_path, _, _ = save_media_bytes(
                raw,
                images_dir=images_dir,
                md_dir=md_dir,
                msg_index=msg_index,
                item_index=item_counter,
                original_name="animated.gif",
                content_type=resp_ct or "image/gif",
            )
            rendered_items.append(f"![GIF]({rel_path})")
        except Exception:
            rendered_items.append(f"![GIF]({uri})")

    # Rich Drive link annotations not already in attachments
    seen_drive_urls = {line for line in rendered_items}
    for ann in msg.get("annotations") or []:
        if ann.get("type") == "RICH_LINK":
            rl = ann.get("richLinkMetadata") or {}
            uri = rl.get("uri")
            if uri and not any(uri in existing for existing in seen_drive_urls):
                drive_data = rl.get("driveLinkData") or {}
                mime = drive_data.get("mimeType", "")
                icon = "🖼️" if mime.startswith("image/") else "🔗"
                rendered_items.append(f"- {icon} [{uri}]({uri})")
                seen_drive_urls.add(uri)

    # Bot Cards (cardsV2 & legacy cards)
    card_lines = extract_card_markdown(
        msg,
        msg_index=msg_index,
        start_item_index=item_counter,
        images_dir=images_dir,
        md_dir=md_dir,
    )
    rendered_items.extend(card_lines)

    return rendered_items


def extract_card_markdown(
    msg: dict[str, Any],
    *,
    msg_index: int,
    start_item_index: int,
    images_dir: Path,
    md_dir: Path,
) -> list[str]:
    lines: list[str] = []
    counter = start_item_index

    cards_v2 = [c.get("card") or {} for c in (msg.get("cardsV2") or [])]
    legacy_cards = msg.get("cards") or []

    for card in [*cards_v2, *legacy_cards]:
        header = card.get("header") or {}
        if header.get("title"):
            subtitle = f" — *{header['subtitle']}*" if header.get("subtitle") else ""
            lines.append(f"> 🪪 **{header['title']}**{subtitle}")

        for section in card.get("sections") or []:
            if section.get("header"):
                lines.append(f"> **{section['header']}**")
            for widget in section.get("widgets") or []:
                if "textParagraph" in widget:
                    txt = _strip_basic_html((widget["textParagraph"] or {}).get("text", ""))
                    if txt:
                        lines.append(f"> {txt}")
                if "decoratedText" in widget:
                    dt_obj = widget["decoratedText"] or {}
                    top = dt_obj.get("topLabel")
                    body = _strip_basic_html(dt_obj.get("text", ""))
                    prefix = f"**{top}:** " if top else ""
                    if prefix or body:
                        lines.append(f"> {prefix}{body}")
                if "keyValue" in widget:
                    kv = widget["keyValue"] or {}
                    top = kv.get("topLabel")
                    body = _strip_basic_html(kv.get("content", ""))
                    prefix = f"**{top}:** " if top else ""
                    if prefix or body:
                        lines.append(f"> {prefix}{body}")
                if "image" in widget:
                    img_obj = widget["image"] or {}
                    img_url = img_obj.get("imageUrl")
                    alt = img_obj.get("altText") or "card-image"
                    if img_url:
                        counter += 1
                        try:
                            raw, resp_ct = http_get_bytes(img_url, access_token=None)
                            rel_path, _, label = save_media_bytes(
                                raw,
                                images_dir=images_dir,
                                md_dir=md_dir,
                                msg_index=msg_index,
                                item_index=counter,
                                original_name=f"{alt}.png",
                                content_type=resp_ct,
                            )
                            lines.append(f"![{label}]({rel_path})")
                        except Exception:
                            lines.append(f"![{alt}]({img_url})")
    return lines


def _strip_basic_html(raw: str) -> str:
    if not raw:
        return ""
    text = re.sub(r"<br\s*/?>", "\n> ", raw, flags=re.IGNORECASE)
    text = re.sub(r"<b>(.*?)</b>", r"**\1**", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<i>(.*?)</i>", r"*\1*", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<a\s+href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", r"[\2](\1)", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


# ---------------------------------------------------------------------------
# Text Formatting & Markdown Rendering
# ---------------------------------------------------------------------------


def convert_chat_text_to_markdown(
    raw_text: str,
    user_map: dict[str, str],
    is_already_markdown: bool = False,
    plain_text: str | None = None,
) -> str:
    if not raw_text:
        return ""

    # Preserve fenced code blocks and inline code spans before transforming markup
    placeholders: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        placeholders.append(match.group(0))
        return f"\x00CODE{len(placeholders) - 1}\x00"

    text = re.sub(r"```[\s\S]*?```|`[^`\n]+`", _stash, raw_text)

    # Fix Google Chat MARKUP_SYNTAX_MARKDOWN quirk where inline `<chat-user>` is preceded by a spurious `\n`
    if is_already_markdown and "<chat-user" in text:
        def _fix_inline_chat_user(match: re.Match[str]) -> str:
            uid = match.group(1)
            label = user_map.get(uid) or uid
            # Keep newline only if plain_text actually had a newline right before @label
            if plain_text and re.search(r"\n\u200b?@" + re.escape(label), plain_text):
                return f"\n**@{label}**"
            return f" **@{label}**"

        text = re.sub(
            r"[^\S\n]*\n\u200b?<chat-user\b[^>]*data-user=['\"](users/[^'\"]+)['\"][^>]*>\s*(?:</chat-user>)?",
            _fix_inline_chat_user,
            text,
        )

    # Replace remaining <chat-user data-user="users/12345"></chat-user> and <users/12345> mentions
    def _replace_user(match: re.Match[str]) -> str:
        uid = match.group(1)
        label = user_map.get(uid) or uid
        return f"**@{label}**"

    text = re.sub(
        r"\u200b?<chat-user\b[^>]*data-user=['\"](users/[^'\"]+)['\"][^>]*>\s*(?:</chat-user>)?",
        _replace_user,
        text,
    )
    text = re.sub(r"<(users/[0-9A-Za-z._-]+)>", _replace_user, text)

    # Replace custom workspace emoji tags <chat-emoji data-emoji-name=":foo:"></chat-emoji>
    text = re.sub(
        r"<chat-emoji\b[^>]*data-emoji-name=['\"]([^'\"]+)['\"][^>]*>\s*(?:</chat-emoji>)?",
        r"`\1`",
        text,
    )

    # Replace Google Chat links <https://example.com|Display Text> and <https://example.com>
    text = re.sub(r"<(https?://[^|>\s]+)\|([^>]+)>", r"[\2](\1)", text)
    text = re.sub(r"<(https?://[^>\s]+)>", r"\1", text)

    if not is_already_markdown:
        # Google Chat legacy markup: *bold* -> **bold**, ~strike~ -> ~~strike~~
        text = re.sub(r"(?<!\w)\*([^\s*](?:[^*\n]*?[^\s*])?)\*(?!\w)", r"**\1**", text)
        text = re.sub(r"(?<!\w)~([^\s~](?:[^~\n]*?[^\s~])?)~(?!\w)", r"~~\1~~", text)

    for idx, original in enumerate(placeholders):
        text = text.replace(f"\x00CODE{idx}\x00", original)

    return text.strip()


def format_timestamp(iso_str: str | None, tz: dt.tzinfo) -> str:
    if not iso_str:
        return ""
    try:
        cleaned = iso_str.replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        local_dt = parsed.astimezone(tz)
        return local_dt.strftime("%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        return iso_str


def render_thread_markdown(
    *,
    source_label: str,
    space_title: str,
    space_name: str,
    thread_name: str,
    messages: list[dict[str, Any]],
    media_per_message: list[list[str]],
    user_map: dict[str, str],
    tz: dt.tzinfo,
) -> str:
    participants: list[str] = []
    seen_participants: set[str] = set()
    total_media = sum(len(m) for m in media_per_message)

    for msg in messages:
        sender = msg.get("sender") or {}
        s_label = (
            sender.get("displayName")
            or user_map.get(sender.get("name", ""))
            or sender.get("name")
            or "Unknown"
        )
        if s_label not in seen_participants:
            seen_participants.add(s_label)
            participants.append(s_label)

    first_ts = format_timestamp(messages[0].get("createTime"), tz) if messages else "N/A"
    last_ts = format_timestamp(messages[-1].get("createTime"), tz) if messages else "N/A"
    exported_at = dt.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %z")
    thread_short = thread_name.split("/")[-1] if thread_name else "thread"

    header_lines = [
        f"# 💬 {space_title} — Thread `{thread_short}`",
        "",
        f"- **Nguồn:** {source_label}",
        f"- **Space:** `{space_name}` ({space_title})",
        f"- **Thread:** `{thread_name}`",
        f"- **Số tin nhắn:** {len(messages)} · **Người tham gia ({len(participants)}):** {', '.join(participants) if participants else 'N/A'} · **Hình ảnh / Đính kèm:** {total_media}",
        f"- **Khoảng thời gian:** `{first_ts}` → `{last_ts}`",
        f"- **Xuất lúc:** `{exported_at}`",
        "",
        "---",
        "",
    ]

    body_lines: list[str] = []
    for idx, (msg, media_lines) in enumerate(zip(messages, media_per_message), start=1):
        sender = msg.get("sender") or {}
        s_name = sender.get("name", "")
        sender_label = sender.get("displayName") or user_map.get(s_name) or s_name or "Unknown"
        bot_badge = " `[BOT]`" if sender.get("type") == "BOT" else ""
        created = format_timestamp(msg.get("createTime"), tz)
        edited = ""
        if msg.get("lastUpdateTime") and msg.get("lastUpdateTime") != msg.get("createTime"):
            edited = " *(đã chỉnh sửa)*"

        body_lines.append(f"### {idx}. **{sender_label}**{bot_badge} · `{created}`{edited}")
        body_lines.append("")

        # Quoted reply snapshot if present
        quoted = (msg.get("quotedMessageMetadata") or {}).get("quotedMessageSnapshot") or {}
        if quoted.get("text") or quoted.get("sender"):
            q_sender = user_map.get(quoted.get("sender", ""), quoted.get("sender") or "Tin nhắn trước")
            body_lines.append(f"> 💬 *Trả lời **{q_sender}**:*")
            for q_line in (quoted.get("text") or "").splitlines():
                body_lines.append(f"> {q_line}")
            body_lines.append("")

        formatted_text = msg.get("formattedText")
        raw_text = formatted_text or msg.get("text") or ""
        md_text = convert_chat_text_to_markdown(
            raw_text,
            user_map=user_map,
            is_already_markdown=bool(formatted_text),
            plain_text=msg.get("text"),
        )
        if md_text:
            body_lines.append(md_text)
            body_lines.append("")

        if media_lines:
            body_lines.extend(media_lines)
            body_lines.append("")

        # Emoji reactions
        reactions: list[str] = []
        for rx in msg.get("emojiReactionSummaries") or []:
            emoji_obj = rx.get("emoji") or {}
            symbol = emoji_obj.get("unicode") or (
                f":{(emoji_obj.get('customEmoji') or {}).get('emojiName', 'emoji')}:"
            )
            count = rx.get("reactionCount", 1)
            reactions.append(f"{symbol} {count}")
        if reactions:
            body_lines.append(" · ".join(reactions))
            body_lines.append("")

        body_lines.append("---")
        body_lines.append("")

    return "\n".join(header_lines + body_lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Browser JSON Dump Converter (`--from-browser-json`)
# ---------------------------------------------------------------------------


def convert_browser_dump_to_markdown(
    dump_path: Path,
    output_md_path: Path,
    images_dir: Path,
    tz: dt.tzinfo,
) -> dict[str, Any]:
    payload = json.loads(dump_path.read_text(encoding="utf-8"))
    url = payload.get("url") or str(dump_path)
    try:
        parsed_target = parse_gchat_target(url)
        space_name = parsed_target["space_name"]
        thread_name = parsed_target["thread_name"]
    except ValueError:
        space_name = payload.get("space_id") or "spaces/unknown"
        thread_name = payload.get("thread_id") or "threads/unknown"

    space_title = payload.get("space_title") or payload.get("title") or space_name
    raw_messages = payload.get("messages") or []

    normalized_msgs: list[dict[str, Any]] = []
    media_per_message: list[list[str]] = []
    saved_images = 0

    for idx, item in enumerate(raw_messages, start=1):
        normalized_msgs.append(
            {
                "sender": {
                    "displayName": item.get("sender") or "Unknown",
                    "type": "BOT" if item.get("is_bot") else "HUMAN",
                },
                "createTime": item.get("timestamp") or "",
                "text": item.get("text") or "",
                "quotedMessageMetadata": (
                    {"quotedMessageSnapshot": {"sender": item.get("quoted_sender", ""), "text": item["quoted_text"]}}
                    if item.get("quoted_text")
                    else {}
                ),
                "emojiReactionSummaries": [
                    {"emoji": {"unicode": r.get("emoji", "👍")}, "reactionCount": r.get("count", 1)}
                    for r in (item.get("reactions") or [])
                ],
            }
        )

        msg_media: list[str] = []
        for img_idx, img in enumerate(item.get("images") or [], start=1):
            data_url = img.get("data_url") or ""
            alt = img.get("alt") or f"image_{idx}_{img_idx}"
            if data_url.startswith("data:"):
                header, b64_part = data_url.split(",", 1)
                mime_match = re.match(r"data:([^;]+)", header)
                mime = mime_match.group(1) if mime_match else "image/png"
                raw_bytes = base64.b64decode(b64_part)
                rel_path, _, label = save_media_bytes(
                    raw_bytes,
                    images_dir=images_dir,
                    md_dir=output_md_path.parent,
                    msg_index=idx,
                    item_index=img_idx,
                    original_name=img.get("filename") or alt,
                    content_type=mime,
                )
                msg_media.append(f"![{label}]({rel_path})")
                saved_images += 1
            elif img.get("src"):
                msg_media.append(f"![{alt}]({img['src']})")
        media_per_message.append(msg_media)

    md_content = render_thread_markdown(
        source_label=f"[{url}]({url})" if url.startswith("http") else f"`{url}`",
        space_title=space_title,
        space_name=space_name,
        thread_name=thread_name,
        messages=normalized_msgs,
        media_per_message=media_per_message,
        user_map={},
        tz=tz,
    )
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.write_text(md_content, encoding="utf-8")
    return {
        "status": "ok",
        "mode": "browser_json",
        "output_markdown": str(output_md_path),
        "images_dir": str(images_dir),
        "message_count": len(normalized_msgs),
        "downloaded_files": saved_images,
    }


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


def resolve_timezone(tz_name: str | None) -> dt.tzinfo:
    if tz_name:
        from zoneinfo import ZoneInfo

        return ZoneInfo(tz_name)
    return dt.datetime.now().astimezone().tzinfo or dt.timezone.utc


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a Google Chat thread conversation (including images) to Markdown."
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="Google Chat thread URL (e.g. https://chat.google.com/u/0/app/chat/SPACE/topic/THREAD) or spaces/SPACE/threads/THREAD",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output Markdown file path (default: ./exports/gchat-<thread_id>/thread.md)",
    )
    parser.add_argument(
        "--images-dir",
        help="Directory to store downloaded images/files (default: <output_dir>/images)",
    )
    parser.add_argument(
        "--credentials",
        default=os.environ.get("GCHAT_CREDENTIALS_PATH", str(DEFAULT_CREDENTIALS_PATH)),
        help=f"Path to Google OAuth Desktop credentials.json (default: {DEFAULT_CREDENTIALS_PATH})",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GCHAT_TOKEN_PATH", str(DEFAULT_TOKEN_PATH)),
        help=f"Path to cached OAuth token.json (default: {DEFAULT_TOKEN_PATH})",
    )
    parser.add_argument(
        "--with-drive",
        action="store_true",
        help="Include drive.readonly OAuth scope to download Drive-hosted image attachments directly.",
    )
    parser.add_argument(
        "--timezone",
        help="IANA timezone name for message timestamps (e.g. Asia/Ho_Chi_Minh). Defaults to local timezone.",
    )
    parser.add_argument(
        "--save-raw-json",
        action="store_true",
        help="Also save the raw Google Chat API messages payload as thread.raw.json next to the Markdown file.",
    )

    # Utility & Auth modes
    parser.add_argument(
        "--parse-only",
        action="store_true",
        help="Parse and validate the Google Chat URL/ID without calling the API.",
    )
    parser.add_argument(
        "--check-auth",
        action="store_true",
        help="Check whether credentials.json and token.json are configured and usable.",
    )
    parser.add_argument(
        "--auth",
        action="store_true",
        help="Run interactive OAuth 2.0 browser login and save token.json.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="With --auth, print the authorization URL without auto-opening a browser.",
    )
    parser.add_argument(
        "--print-auth-url",
        action="store_true",
        help="Generate an OAuth PKCE URL for manual/remote login (pair with --complete-auth).",
    )
    parser.add_argument(
        "--complete-auth",
        metavar="REDIRECT_URL_OR_CODE",
        help="Complete manual OAuth flow using the http://127.0.0.1:.../?code=... redirect URL.",
    )
    parser.add_argument(
        "--listen-pending",
        action="store_true",
        help="Listen on the redirect_uri port of an existing pending_oauth.json session and auto-complete.",
    )
    parser.add_argument(
        "--from-browser-json",
        metavar="DUMP_JSON_PATH",
        help="Convert a JSON file exported by scripts/browser_extract.js into Markdown + local images.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    credentials_path = Path(args.credentials).expanduser().resolve()
    token_path = Path(args.token).expanduser().resolve()
    pending_path = token_path.parent / DEFAULT_PENDING_OAUTH_PATH.name
    scopes = build_scopes(with_drive=args.with_drive)
    tz = resolve_timezone(args.timezone)

    try:
        if args.check_auth:
            status = check_auth_status(credentials_path, token_path)
            print(json.dumps(status, indent=2, ensure_ascii=False))
            return 0 if status["ready"] else 2

        if args.parse_only:
            if not args.target:
                parser.error("`--parse-only` requires a target Google Chat URL or resource ID.")
            parsed = parse_gchat_target(args.target)
            print(json.dumps(parsed, indent=2, ensure_ascii=False))
            return 0

        if args.print_auth_url:
            info = create_manual_auth_url(credentials_path, pending_path, scopes=scopes)
            print(json.dumps(info, indent=2, ensure_ascii=False))
            return 0

        if args.complete_auth:
            tok = complete_manual_auth(
                args.complete_auth,
                pending_path=pending_path,
                token_path=token_path,
                credentials_path=credentials_path,
            )
            print(
                json.dumps(
                    {"status": "authenticated", "token_path": str(token_path), "scopes": tok.get("scopes", [])},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

        if args.listen_pending:
            pending = json.loads(pending_path.read_text(encoding="utf-8"))
            port = urllib.parse.urlparse(pending["redirect_uri"]).port or 8765
            captured_url: dict[str, str] = {}

            class PendingHandler(http.server.BaseHTTPRequestHandler):
                def do_GET(self) -> None:  # noqa: N802
                    if self.path.startswith("/favicon.ico"):
                        self.send_response(204)
                        self.end_headers()
                        return
                    captured_url["full"] = f"http://127.0.0.1:{port}{self.path}"
                    body = (
                        "<html><head><meta charset='utf-8'></head>"
                        "<body style='font-family:sans-serif;padding:2rem;'>"
                        "<h2>Xác thực thành công! Bạn có thể đóng tab này và quay lại Antigravity.</h2>"
                        "</body></html>"
                    ).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

                def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                    return

            srv = http.server.HTTPServer(("127.0.0.1", port), PendingHandler)
            deadline = dt.datetime.now(dt.timezone.utc).timestamp() + 600
            try:
                while "full" not in captured_url:
                    rem = deadline - dt.datetime.now(dt.timezone.utc).timestamp()
                    if rem <= 0:
                        raise TimeoutError("Timed out waiting on pending OAuth port.")
                    srv.timeout = min(rem, 5.0)
                    srv.handle_request()
            finally:
                srv.server_close()

            tok = complete_manual_auth(
                captured_url["full"],
                pending_path=pending_path,
                token_path=token_path,
                credentials_path=credentials_path,
            )
            print(
                json.dumps(
                    {"status": "authenticated", "token_path": str(token_path), "scopes": tok.get("scopes", [])},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

        if args.auth:
            tok = run_interactive_loopback_auth(
                credentials_path=credentials_path,
                token_path=token_path,
                scopes=scopes,
                open_browser=not args.no_browser,
            )
            print(
                json.dumps(
                    {"status": "authenticated", "token_path": str(token_path), "scopes": tok.get("scopes", [])},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

        if args.from_browser_json:
            dump_file = Path(args.from_browser_json).expanduser().resolve()
            out_md = (
                Path(args.output).expanduser().resolve()
                if args.output
                else Path.cwd() / "exports" / dump_file.stem / "thread.md"
            )
            img_dir = (
                Path(args.images_dir).expanduser().resolve()
                if args.images_dir
                else out_md.parent / "images"
            )
            summary = convert_browser_dump_to_markdown(dump_file, out_md, img_dir, tz=tz)
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            return 0

        if not args.target:
            parser.error("Provide a Google Chat thread URL/ID, or use `--check-auth`, `--auth`, or `--from-browser-json`.")

        target = parse_gchat_target(args.target)
        out_md = (
            Path(args.output).expanduser().resolve()
            if args.output
            else Path.cwd() / "exports" / f"gchat-{target['thread_id']}" / "thread.md"
        )
        img_dir = (
            Path(args.images_dir).expanduser().resolve()
            if args.images_dir
            else out_md.parent / "images"
        )

        access_token = get_valid_access_token(
            credentials_path=credentials_path,
            token_path=token_path,
            scopes=scopes,
            auto_interactive_auth=False,
        )

        space_meta = fetch_space_metadata(target["space_name"], access_token)
        space_title = (
            space_meta.get("displayName")
            or space_meta.get("spaceDetails", {}).get("description")
            or target["space_name"]
        )

        messages, resolved_thread_name = fetch_thread_messages(target, access_token)
        if not messages:
            print(
                json.dumps(
                    {
                        "status": "empty",
                        "space_name": target["space_name"],
                        "thread_name": resolved_thread_name,
                        "message": "Không tìm thấy tin nhắn nào trong thread này (hoặc tài khoản không có quyền xem space).",
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 1

        user_map = resolve_user_names(messages, access_token)

        out_md.parent.mkdir(parents=True, exist_ok=True)
        media_per_message: list[list[str]] = []
        downloaded_count = 0
        for idx, msg in enumerate(messages, start=1):
            items = download_message_media(
                msg,
                msg_index=idx,
                access_token=access_token,
                images_dir=img_dir,
                md_dir=out_md.parent,
            )
            downloaded_count += sum(1 for line in items if "(images/" in line or f"({img_dir.name}/" in line)
            media_per_message.append(items)

        source_label = (
            f"[{target['input']}]({target['input']})"
            if target["input"].startswith("http")
            else f"`{target['input']}`"
        )
        md_text = render_thread_markdown(
            source_label=source_label,
            space_title=space_title,
            space_name=target["space_name"],
            thread_name=resolved_thread_name,
            messages=messages,
            media_per_message=media_per_message,
            user_map=user_map,
            tz=tz,
        )
        out_md.write_text(md_text, encoding="utf-8")

        if args.save_raw_json:
            raw_path = out_md.with_suffix(".raw.json")
            raw_path.write_text(
                json.dumps(
                    {
                        "target": target,
                        "space": space_meta,
                        "resolved_thread_name": resolved_thread_name,
                        "user_map": user_map,
                        "messages": messages,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

        print(
            json.dumps(
                {
                    "status": "ok",
                    "mode": "google_chat_api",
                    "space_name": target["space_name"],
                    "space_title": space_title,
                    "thread_name": resolved_thread_name,
                    "message_count": len(messages),
                    "downloaded_files": downloaded_count,
                    "output_markdown": str(out_md),
                    "images_dir": str(img_dir),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    except HttpError as exc:
        print(explain_google_api_error(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
