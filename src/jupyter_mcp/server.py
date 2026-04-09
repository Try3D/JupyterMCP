"""FastMCP server setup."""

import os
import sys

from mcp.server.fastmcp import FastMCP

from .executor import CellExecutor
from .kernel_manager import DelegatingKernelRegistry, KernelRegistry
from .notebook_manager import NotebookManager
from .tools.cells import register_cell_tools
from .tools.execution import register_execution_tools
from .tools.kernel import register_kernel_tools
from .tools.notebooks import register_notebook_tools
from .tools.remote import register_remote_tools


def _get_working_dir() -> str:
    """Get working directory from --working-dir arg, CLAUDE_CODE_CWD env, or cwd."""
    if "--working-dir" in sys.argv:
        idx = sys.argv.index("--working-dir")
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return os.environ.get("CLAUDE_CODE_CWD") or os.getcwd()


def _get_remote_config() -> tuple[str | None, str | None]:
    """Get remote server URL and token from --remote-url/--remote-token args or env vars."""
    url = None
    token = None
    if "--remote-url" in sys.argv:
        idx = sys.argv.index("--remote-url")
        if idx + 1 < len(sys.argv):
            url = sys.argv[idx + 1]
    if "--remote-token" in sys.argv:
        idx = sys.argv.index("--remote-token")
        if idx + 1 < len(sys.argv):
            token = sys.argv[idx + 1]
    url = url or os.environ.get("JUPYTER_SERVER_URL")
    token = token or os.environ.get("JUPYTER_SERVER_TOKEN", "")
    return url, token


def create_server():
    """Create and configure the MCP server."""
    working_dir = _get_working_dir()

    mcp = FastMCP(
        name="jupyter-notebook",
        instructions=(
            "Manage Jupyter notebooks and execute Python code interactively. "
            "Notebooks are saved as .ipynb files. Kernel state (variables, imports) "
            "persists between cell executions within the same session. "
            "Use remote_connect to route kernel execution to a remote Jupyter Server."
        ),
    )

    # Mutable state: working directory can be changed at runtime
    _session_state = {"working_dir": working_dir}

    notebook_mgr = NotebookManager(working_dir=working_dir)
    kernel_reg = DelegatingKernelRegistry(local=KernelRegistry())
    executor = CellExecutor(kernel_registry=kernel_reg)

    # Connect to remote server at startup if configured
    remote_url, remote_token = _get_remote_config()
    if remote_url:
        from .remote_kernel_manager import RemoteKernelRegistry
        kernel_reg.set_remote(RemoteKernelRegistry(server_url=remote_url, token=remote_token or ""))

    def _get_current_working_dir() -> str:
        return _session_state["working_dir"]

    def _set_notebook_manager_dir(path: str) -> None:
        _session_state["working_dir"] = path
        notebook_mgr.working_dir = path

    # Register tool groups
    register_notebook_tools(mcp, notebook_mgr, kernel_reg, _get_current_working_dir, _set_notebook_manager_dir)
    register_cell_tools(mcp, notebook_mgr)
    register_execution_tools(mcp, notebook_mgr, kernel_reg, executor)
    register_kernel_tools(mcp, notebook_mgr, kernel_reg)
    register_remote_tools(mcp, kernel_reg)

    return mcp


def main():
    """Entry point for the MCP server."""
    mcp = create_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
