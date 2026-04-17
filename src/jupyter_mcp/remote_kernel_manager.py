"""Remote Jupyter kernel management via Jupyter Server REST API and WebSocket."""

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from queue import Empty, Queue

import requests
import websocket

logger = logging.getLogger(__name__)


@dataclass
class RemoteKernelEntry:
    kernel_id: str
    client: "RemoteBlockingClient"
    python_path: str = "remote"
    lock: threading.Lock = field(default_factory=threading.Lock)

    def is_alive(self) -> bool:
        return self.client.is_connected()


class RemoteBlockingClient:
    """Synchronous kernel client that communicates with a remote Jupyter kernel over WebSocket.

    Provides the same interface as BlockingKernelClient (execute, get_iopub_msg,
    get_shell_msg) so CellExecutor works without modification.
    """

    def __init__(self, ws_url: str):
        self._ws_url = ws_url
        self._iopub_queue: Queue = Queue()
        self._shell_queue: Queue = Queue()
        self._ws: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._connected = threading.Event()
        self._session_id = str(uuid.uuid4())
        self._error: str | None = None

    def start_channels(self):
        self._ws = websocket.WebSocketApp(
            self._ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._thread = threading.Thread(
            target=self._ws.run_forever,
            kwargs={"ping_interval": 30},
            daemon=True,
        )
        self._thread.start()
        if not self._connected.wait(timeout=10):
            raise ConnectionError(f"Failed to connect to remote kernel at {self._ws_url}")

    def stop_channels(self):
        if self._ws:
            self._ws.close()
        self._connected.clear()

    def is_connected(self) -> bool:
        return self._connected.is_set()

    def wait_for_ready(self, timeout: float = 30.0) -> dict:
        """Wait for kernel to be ready. Returns language_info from kernel_info_reply."""
        msg_id = self._send("shell", "kernel_info_request", {})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                msg = self._shell_queue.get(timeout=min(remaining, 1.0))
                if (
                    msg["header"]["msg_type"] == "kernel_info_reply"
                    and msg.get("parent_header", {}).get("msg_id") == msg_id
                ):
                    return msg.get("content", {}).get("language_info", {})
            except Empty:
                continue
        raise TimeoutError(f"Remote kernel not ready within {timeout}s")

    def execute(self, code: str, store_history: bool = True) -> str:
        return self._send("shell", "execute_request", {
            "code": code,
            "silent": False,
            "store_history": store_history,
            "user_expressions": {},
            "allow_stdin": False,
            "stop_on_error": True,
        })

    def get_iopub_msg(self, timeout: float = -1) -> dict:
        if self._error is not None:
            raise ConnectionError(f"WebSocket connection lost: {self._error}")
        t = None if timeout == -1 else timeout
        try:
            return self._iopub_queue.get(timeout=t)
        except Empty:
            raise Empty()

    def get_shell_msg(self, timeout: float = -1) -> dict:
        if self._error is not None:
            raise ConnectionError(f"WebSocket connection lost: {self._error}")
        t = None if timeout == -1 else timeout
        try:
            return self._shell_queue.get(timeout=t)
        except Empty:
            raise Empty()

    def _send(self, channel: str, msg_type: str, content: dict) -> str:
        msg_id = str(uuid.uuid4())
        msg = {
            "header": {
                "msg_id": msg_id,
                "msg_type": msg_type,
                "version": "5.3",
                "username": "mcp",
                "session": self._session_id,
                "date": datetime.now(timezone.utc).isoformat(),
            },
            "parent_header": {},
            "metadata": {},
            "content": content,
            "channel": channel,
            "buffers": [],
        }
        self._ws.send(json.dumps(msg))
        return msg_id

    def _on_open(self, ws):
        self._connected.set()

    def _on_message(self, ws, data):
        try:
            msg = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return
        channel = msg.get("channel", "")
        if channel == "iopub":
            self._iopub_queue.put(msg)
        elif channel == "shell":
            self._shell_queue.put(msg)

    def _on_error(self, ws, error):
        self._error = str(error)
        logger.error("WebSocket error for %s: %s", self._ws_url, error)
        self._connected.clear()

    def _on_close(self, ws, close_status_code, close_msg):
        self._connected.clear()
        if close_status_code and close_status_code not in (1000, 1001):
            if self._error is None:
                self._error = f"WebSocket closed unexpectedly: code={close_status_code} msg={close_msg}"
            logger.warning("WebSocket closed: %s: code=%s msg=%s", self._ws_url, close_status_code, close_msg)


class RemoteKernelRegistry:
    """Manages kernels on a remote Jupyter Server.

    Mirrors the KernelRegistry interface so it can be used as a drop-in
    replacement (via DelegatingKernelRegistry) without modifying CellExecutor
    or any tool registration code.
    """

    def __init__(self, server_url: str, token: str):
        self._server_url = server_url.rstrip("/")
        self._token = token
        self._kernels: dict[str, RemoteKernelEntry] = {}
        self._global_lock = threading.Lock()
        self._session = requests.Session()
        if token:
            self._session.headers["Authorization"] = f"token {token}"

    def verify_connection(self) -> None:
        """Raise if the remote server is unreachable or auth fails."""
        resp = self._session.get(f"{self._server_url}/api", timeout=10)
        resp.raise_for_status()

    def get_or_start(self, notebook_path: str, python_path: str | None = None) -> RemoteKernelEntry:
        with self._global_lock:
            entry = self._kernels.get(notebook_path)
            if entry is not None and entry.is_alive():
                return entry
            if entry is not None:
                try:
                    entry.client.stop_channels()
                except Exception:
                    pass
            return self._start_locked(notebook_path)

    def _start_locked(self, notebook_path: str) -> "RemoteKernelEntry":
        resp = self._session.post(f"{self._server_url}/api/kernels", json={})
        resp.raise_for_status()
        kernel_data = resp.json()
        kernel_id = kernel_data["id"]

        client = RemoteBlockingClient(self._kernel_ws_url(kernel_id))
        client.start_channels()
        language_info = client.wait_for_ready(timeout=30)

        python_version = language_info.get("version", "")
        kernel_name = kernel_data.get("name", "")
        if python_version:
            python_path = f"remote:{kernel_name}:{python_version}" if kernel_name else f"remote:python:{python_version}"
        elif kernel_name:
            python_path = f"remote:{kernel_name}"
        else:
            python_path = "remote"

        entry = RemoteKernelEntry(kernel_id=kernel_id, client=client, python_path=python_path)
        self._kernels[notebook_path] = entry
        return entry

    def _kernel_ws_url(self, kernel_id: str) -> str:
        ws_base = self._server_url.replace("https://", "wss://").replace("http://", "ws://")
        # Pass token as query param for maximum server compatibility
        return f"{ws_base}/api/kernels/{kernel_id}/channels?token={self._token}"

    def shutdown(self, notebook_path: str) -> None:
        with self._global_lock:
            entry = self._kernels.pop(notebook_path, None)
        if entry is None:
            return
        try:
            entry.client.stop_channels()
        except Exception:
            pass
        try:
            self._session.delete(f"{self._server_url}/api/kernels/{entry.kernel_id}")
        except Exception:
            pass

    def restart(self, notebook_path: str, python_path: str | None = None) -> str:
        with self._global_lock:
            entry = self._kernels.get(notebook_path)
            if entry is None:
                return self._start_locked(notebook_path).python_path
            try:
                entry.client.stop_channels()
                self._session.post(
                    f"{self._server_url}/api/kernels/{entry.kernel_id}/restart",
                    json={},
                )
                new_client = RemoteBlockingClient(self._kernel_ws_url(entry.kernel_id))
                new_client.start_channels()
                language_info = new_client.wait_for_ready(timeout=30)
                entry.client = new_client
                python_version = language_info.get("version", "")
                if python_version:
                    entry.python_path = f"remote:python:{python_version}"
            except Exception:
                self._kernels.pop(notebook_path, None)
                return self._start_locked(notebook_path).python_path
        return entry.python_path

    def interrupt(self, notebook_path: str) -> None:
        entry = self._kernels.get(notebook_path)
        if entry is None:
            return
        try:
            self._session.post(
                f"{self._server_url}/api/kernels/{entry.kernel_id}/interrupt",
                json={},
            )
        except Exception:
            pass

    def is_alive(self, notebook_path: str) -> bool:
        entry = self._kernels.get(notebook_path)
        return entry is not None and entry.is_alive()

    def get_status(self, notebook_path: str) -> dict:
        entry = self._kernels.get(notebook_path)
        if entry is None:
            return {"status": "not_started", "python_path": None}
        if not entry.is_alive():
            return {"status": "dead", "python_path": entry.python_path}
        return {"status": "idle", "python_path": entry.python_path}

    def start(self, notebook_path: str, python_path: str | None = None) -> str:
        """Always tear down any existing remote kernel and start a fresh one.
        python_path is not supported for remote kernels and must be None."""
        if python_path is not None:
            raise ValueError("python_path is not supported for remote kernels; the remote server controls the interpreter")
        with self._global_lock:
            entry = self._kernels.pop(notebook_path, None)
            if entry is not None:
                try:
                    entry.client.stop_channels()
                    self._session.delete(f"{self._server_url}/api/kernels/{entry.kernel_id}")
                except Exception:
                    pass
            return self._start_locked(notebook_path).python_path

    def list_kernels(self) -> list[dict]:
        """Return all tracked remote kernels with their status and python path."""
        with self._global_lock:
            return [
                {
                    "notebook": p,
                    "status": "idle" if e.is_alive() else "dead",
                    "python_path": e.python_path,
                    "kernel_id": e.kernel_id,
                }
                for p, e in self._kernels.items()
            ]

    def get_entry(self, notebook_path: str) -> RemoteKernelEntry | None:
        return self._kernels.get(notebook_path)

    def cleanup_all(self) -> None:
        paths = list(self._kernels.keys())
        for path in paths:
            self.shutdown(path)
