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

    @mcp.tool(annotations={"readOnlyHint": True})
    def notebook_get(name: str) -> dict:
        """
        Read a notebook and return its full structure: all cells with their IDs,
        types, source, execution counts, and outputs.

        Use the returned cell IDs with cell_update, cell_delete, cell_move, and
        cell_execute to modify or run specific cells.
        """
        try:
            nb = notebook_mgr.read(name)
            return {"success": True, **notebook_mgr.serialize_notebook(nb, notebook_mgr._name(name))}
        except FileNotFoundError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Failed to read notebook: {e}"}

    @mcp.tool(annotations={"readOnlyHint": True})
    def notebook_as_script(name: str, include_markdown: bool = True) -> dict:
        """
        Return the entire notebook as a single Python script string.

        Each cell is preceded by a # %% marker (the convention used by VSCode,
        Spyder, and nbconvert) so the script can be analysed, diffed, or reasoned
        about as a complete program.

        - Code cells: source pasted verbatim under their marker.
        - Markdown cells: each line prefixed with "# " under their marker.
          Omitted entirely when include_markdown=False.
        - Raw cells: always skipped.

        The script is returned in the response; no file is written to disk.
        """
        try:
            nb = notebook_mgr.read(name)
            parts: list[str] = []
            code_count = 0

            for idx, cell in enumerate(nb.cells):
                if cell.cell_type == "raw":
                    continue
                if cell.cell_type == "markdown" and not include_markdown:
                    continue

                marker = f"# %% [cell {idx} · {cell.cell_type} · id:{cell.id}]"

                if cell.cell_type == "code":
                    code_count += 1
                    parts.append(marker + "\n" + cell.source)
                else:  # markdown
                    commented = "\n".join(
                        ("# " + line).rstrip() for line in cell.source.splitlines()
                    )
                    parts.append(marker + "\n" + commented)

            script = "\n\n".join(parts)
            nb_name = notebook_mgr._name(name)
            return {
                "success": True,
                "name": nb_name,
                "script": script,
                "cell_count": len(nb.cells),
                "code_cell_count": code_count,
            }
        except FileNotFoundError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Failed to export notebook as script: {e}"}
