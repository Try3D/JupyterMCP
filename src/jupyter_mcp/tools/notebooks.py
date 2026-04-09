"""Notebook management tools."""

import os

from mcp.server.fastmcp import FastMCP

from ..kernel_manager import KernelRegistry
from ..notebook_manager import NotebookManager


def register_notebook_tools(
    mcp: FastMCP,
    notebook_mgr: NotebookManager,
    kernel_reg: KernelRegistry,
    get_current_dir,
    set_notebook_dir,
):
    """Register notebook management tools with the MCP server."""

    @mcp.tool(
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}
    )
    def notebook_create(name: str) -> dict:
        """
        Create a new Jupyter notebook (.ipynb) in the working directory.
        The .ipynb extension is added automatically if not included.
        Returns the notebook name and path on success.
        """
        try:
            result = notebook_mgr.create(name)
            return {"success": True, **result}
        except FileExistsError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Failed to create notebook: {e}"}

    @mcp.tool(
        annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True}
    )
    def notebook_delete(name: str) -> dict:
        """
        Delete a notebook file and shut down its kernel if running.
        The .ipynb extension is optional.
        """
        try:
            path = notebook_mgr._path(name)
            kernel_reg.shutdown(path)
            notebook_mgr.delete(name)
            nb_name = name if name.endswith(".ipynb") else name + ".ipynb"
            return {"success": True, "message": f"Deleted {nb_name}"}
        except FileNotFoundError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Failed to delete notebook: {e}"}

    @mcp.tool(
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}
    )
    def set_notebook_directory(path: str) -> dict:
        """
        Set the working directory for notebook operations.
        All subsequent notebook operations will use this directory.
        Useful for specifying where notebooks should be saved and loaded from.
        """
        try:
            if not os.path.isdir(path):
                return {"success": False, "error": f"Directory does not exist: {path}"}
            set_notebook_dir(os.path.abspath(path))
            return {"success": True, "working_dir": get_current_dir()}
        except Exception as e:
            return {"success": False, "error": f"Failed to set working directory: {e}"}

    @mcp.tool(annotations={"readOnlyHint": True})
    def get_notebook_directory() -> dict:
        """Get the current working directory for notebook operations."""
        return {"success": True, "working_dir": get_current_dir()}

    @mcp.tool(annotations={"readOnlyHint": True})
    def notebook_list() -> dict:
        """List all .ipynb notebooks in the working directory."""
        notebooks = notebook_mgr.list_notebooks()
        return {"success": True, "notebooks": notebooks, "count": len(notebooks)}
