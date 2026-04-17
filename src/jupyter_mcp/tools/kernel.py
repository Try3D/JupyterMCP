"""Kernel management tools."""

from mcp.server.fastmcp import FastMCP

from ..kernel_manager import DelegatingKernelRegistry
from ..notebook_manager import NotebookManager


def register_kernel_tools(
    mcp: FastMCP,
    notebook_mgr: NotebookManager,
    kernel_reg: DelegatingKernelRegistry,
):
    """Register kernel management tools with the MCP server."""

    @mcp.tool(
        annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False}
    )
    def kernel_restart(name: str, python_path: str = "") -> dict:
        """
        Restart the kernel for a notebook. Clears all in-memory state (variables,
        imports, etc.). Cell outputs saved to the .ipynb file are not affected.

        python_path: optionally switch to a different Python interpreter on restart.
        - "" or omitted: keep using the same Python the kernel was started with.
        - Absolute path: e.g. "/home/user/project/.venv/bin/python"
        - Name on PATH: e.g. "python3.11"
        If python_path differs from the current kernel's Python, the kernel is
        fully replaced rather than just restarted in-place.
        """
        try:
            path = notebook_mgr._path(name)
            resolved = kernel_reg.restart(path, python_path=python_path or None)
            return {"success": True, "message": f"Kernel for '{name}' restarted", "python_path": resolved}
        except (ValueError, Exception) as e:
            return {"success": False, "error": f"Failed to restart kernel: {e}"}

    @mcp.tool(
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True}
    )
    def kernel_interrupt(name: str) -> dict:
        """
        Send an interrupt signal to the running kernel. Use this to stop a
        long-running or infinite-loop cell execution.
        """
        try:
            path = notebook_mgr._path(name)
            kernel_reg.interrupt(path)
            return {"success": True, "message": f"Interrupt sent to kernel for '{name}'"}
        except Exception as e:
            return {"success": False, "error": f"Failed to interrupt kernel: {e}"}

    @mcp.tool(annotations={"readOnlyHint": True})
    def kernel_status(name: str) -> dict:
        """
        Get the current status and Python interpreter of the kernel for a notebook.
        Status is one of: 'not_started', 'idle', or 'dead'.
        python_path shows which Python executable the kernel is using (null if not started).
        """
        path = notebook_mgr._path(name)
        info = kernel_reg.get_status(path)
        return {"success": True, "notebook": name, **info}

    @mcp.tool(
        annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False}
    )
    def kernel_start(name: str, python_path: str = "") -> dict:
        """
        Shut down any existing kernel for this notebook and start a completely
        fresh one. Unlike kernel_restart, this always creates a new kernel
        process from scratch — even if the Python interpreter is unchanged.
        Use this at session start to enforce a specific Python environment,
        or to guarantee a clean slate.

        python_path: which Python to use for the new kernel.
        - "" or omitted: uses the server's own Python (sys.executable)
        - Absolute path: e.g. "/home/user/project/.venv/bin/python"
        - Name on PATH: e.g. "python3.11"
        Not supported when connected to a remote server (use remote_connect to
        select the server; the remote server controls the interpreter).
        """
        try:
            path = notebook_mgr._path(name)
            resolved = kernel_reg.start(path, python_path=python_path or None)
            return {"success": True, "message": f"Kernel for '{name}' started fresh", "python_path": resolved}
        except Exception as e:
            return {"success": False, "error": f"Failed to start kernel: {e}"}

    @mcp.tool(annotations={"readOnlyHint": True})
    def kernel_list() -> dict:
        """
        List all kernels currently tracked in this session, with their status
        (idle/dead) and Python interpreter path. Only kernels started during
        this MCP session are listed.
        """
        kernels = kernel_reg.list_kernels()
        return {"success": True, "kernels": kernels, "count": len(kernels)}
