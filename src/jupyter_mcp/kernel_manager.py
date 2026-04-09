import atexit
import shutil
import sys
import threading
from dataclasses import dataclass, field

from jupyter_client import KernelManager
from jupyter_client.blocking.client import BlockingKernelClient


@dataclass
class KernelEntry:
    manager: KernelManager
    client: BlockingKernelClient
    python_path: str
    lock: threading.Lock = field(default_factory=threading.Lock)


def _resolve_python(python_path: str | None) -> str:
    """Resolve a python_path hint to an absolute executable path.

    Accepts:
    - None / "" → sys.executable (server's own Python, sensible default)
    - Absolute path  → used as-is
    - Name on PATH (e.g. "python3.11") → resolved via shutil.which
    """
    if not python_path:
        return sys.executable
    resolved = shutil.which(python_path)
    if resolved:
        return resolved
    raise ValueError(
        f"Python executable not found: '{python_path}'. "
        "Provide an absolute path or a name available on PATH."
    )


class KernelRegistry:
    def __init__(self):
        self._kernels: dict[str, KernelEntry] = {}
        self._global_lock = threading.Lock()
        atexit.register(self.cleanup_all)

    def get_or_start(self, notebook_path: str, python_path: str | None = None) -> KernelEntry:
        """Return a live kernel for the notebook, starting one if needed.

        python_path is only used when a new kernel must be started.
        If a kernel is already running, it is returned as-is (use restart
        to switch to a different Python).
        """
        with self._global_lock:
            entry = self._kernels.get(notebook_path)
            if entry is not None and entry.manager.is_alive():
                return entry
            if entry is not None:
                try:
                    entry.client.stop_channels()
                    entry.manager.shutdown_kernel(now=True)
                except Exception:
                    pass
            return self._start_locked(notebook_path, python_path)

    def _start_locked(self, notebook_path: str, python_path: str | None = None) -> KernelEntry:
        resolved = _resolve_python(python_path)
        km = KernelManager()
        # In jupyter_client 8+, format_kernel_cmd uses kernel_spec.argv directly
        # and ignores the deprecated kernel_cmd attribute. We must override argv.
        km.kernel_spec.argv = [resolved, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
        km.start_kernel()
        kc: BlockingKernelClient = km.blocking_client()
        kc.start_channels()
        kc.wait_for_ready(timeout=30)
        entry = KernelEntry(manager=km, client=kc, python_path=resolved)
        self._kernels[notebook_path] = entry
        return entry

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
            entry.manager.shutdown_kernel(now=False)
        except Exception:
            pass

    def restart(self, notebook_path: str, python_path: str | None = None) -> str:
        """Restart the kernel. If python_path changes, tears down and starts fresh.
        Returns the resolved python path in use after restart."""
        with self._global_lock:
            entry = self._kernels.get(notebook_path)
            if entry is None:
                return self._start_locked(notebook_path, python_path).python_path

            resolved = _resolve_python(python_path)
            if resolved != entry.python_path:
                # Different Python requested — full teardown and fresh start
                try:
                    entry.client.stop_channels()
                    entry.manager.shutdown_kernel(now=True)
                except Exception:
                    pass
                return self._start_locked(notebook_path, python_path).python_path
            else:
                # Same Python — in-place restart (faster, keeps connection)
                entry.manager.restart_kernel()
                entry.client.wait_for_ready(timeout=30)
                return entry.python_path

    def interrupt(self, notebook_path: str) -> None:
        entry = self._kernels.get(notebook_path)
        if entry is not None:
            entry.manager.interrupt_kernel()

    def is_alive(self, notebook_path: str) -> bool:
        entry = self._kernels.get(notebook_path)
        if entry is None:
            return False
        return entry.manager.is_alive()

    def get_status(self, notebook_path: str) -> dict:
        entry = self._kernels.get(notebook_path)
        if entry is None:
            return {"status": "not_started", "python_path": None}
        if not entry.manager.is_alive():
            return {"status": "dead", "python_path": entry.python_path}
        return {"status": "idle", "python_path": entry.python_path}

    def get_entry(self, notebook_path: str) -> KernelEntry | None:
        return self._kernels.get(notebook_path)

    def cleanup_all(self) -> None:
        paths = list(self._kernels.keys())
        for path in paths:
            self.shutdown(path)


class DelegatingKernelRegistry:
    """Proxies kernel operations to either the local or a remote registry.

    Swap registries at runtime via set_remote / clear_remote without touching
    CellExecutor or any tool registration code.
    """

    def __init__(self, local: KernelRegistry):
        self._local = local
        self._remote = None

    def set_remote(self, remote) -> None:
        self._remote = remote

    def clear_remote(self) -> None:
        if self._remote is not None:
            self._remote.cleanup_all()
        self._remote = None

    def has_remote(self) -> bool:
        return self._remote is not None

    def remote_url(self) -> str | None:
        if self._remote is not None:
            return self._remote._server_url
        return None

    @property
    def _active(self):
        return self._remote if self._remote is not None else self._local

    def get_or_start(self, notebook_path: str, python_path: str | None = None):
        return self._active.get_or_start(notebook_path, python_path)

    def shutdown(self, notebook_path: str) -> None:
        return self._active.shutdown(notebook_path)

    def restart(self, notebook_path: str, python_path: str | None = None) -> str:
        return self._active.restart(notebook_path, python_path)

    def interrupt(self, notebook_path: str) -> None:
        return self._active.interrupt(notebook_path)

    def is_alive(self, notebook_path: str) -> bool:
        return self._active.is_alive(notebook_path)

    def get_status(self, notebook_path: str) -> dict:
        return self._active.get_status(notebook_path)

    def get_entry(self, notebook_path: str):
        return self._active.get_entry(notebook_path)

    def cleanup_all(self) -> None:
        return self._active.cleanup_all()
