"""FastMCP server setup."""

import os
import sys

from mcp.server.fastmcp import FastMCP

from .executor import CellExecutor
from .kernel_manager import KernelRegistry
from .notebook_manager import NotebookManager
from .tools.cells import register_cell_tools
from .tools.execution import register_execution_tools
from .tools.kernel import register_kernel_tools
from .tools.notebooks import register_notebook_tools


def _get_working_dir() -> str:
    """Get working directory from --working-dir arg, CLAUDE_CODE_CWD env, or cwd."""
    if "--working-dir" in sys.argv:
        idx = sys.argv.index("--working-dir")
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return os.environ.get("CLAUDE_CODE_CWD") or os.getcwd()


def create_server():
    """Create and configure the MCP server."""
    working_dir = _get_working_dir()

    mcp = FastMCP(
        name="jupyter-notebook",
        instructions=(
            "Manage Jupyter notebooks and execute Python code interactively. "
            "Notebooks are saved as .ipynb files. Kernel state (variables, imports) "
            "persists between cell executions within the same session."
        ),
    )

    # Mutable state: working directory can be changed at runtime
    _session_state = {"working_dir": working_dir}

    notebook_mgr = NotebookManager(working_dir=working_dir)
    kernel_reg = KernelRegistry()
    executor = CellExecutor(kernel_registry=kernel_reg)

    def _get_current_working_dir() -> str:
        """Get the current session working directory."""
        return _session_state["working_dir"]

    def _set_notebook_manager_dir(path: str) -> None:
        """Update the notebook manager's working directory."""
        _session_state["working_dir"] = path
        notebook_mgr.working_dir = path

    # Register tool groups
    register_notebook_tools(mcp, notebook_mgr, kernel_reg, _get_current_working_dir, _set_notebook_manager_dir)
    register_cell_tools(mcp, notebook_mgr)
    register_execution_tools(mcp, notebook_mgr, kernel_reg, executor)
    register_kernel_tools(mcp, notebook_mgr, kernel_reg)

    return mcp


def main():
    """Entry point for the MCP server."""
    mcp = create_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
