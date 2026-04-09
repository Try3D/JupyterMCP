"""Cell management tools."""

from mcp.server.fastmcp import FastMCP

from ..notebook_manager import NotebookManager


def register_cell_tools(mcp: FastMCP, notebook_mgr: NotebookManager):
    """Register cell management tools with the MCP server."""

    @mcp.tool(
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}
    )
    def cell_add(
        name: str,
        source: str,
        cell_type: str = "code",
        position: int = -1,
    ) -> dict:
        """
        Add a new cell to a notebook.
        - name: notebook name (with or without .ipynb)
        - source: the cell content / code
        - cell_type: 'code', 'markdown', or 'raw' (default: 'code')
        - position: index to insert at (0 = first cell, -1 = append at end)
        Returns the new cell's ID and position.
        """
        try:
            result = notebook_mgr.add_cell(name, cell_type, source, position)
            return {"success": True, **result}
        except (FileNotFoundError, ValueError) as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Failed to add cell: {e}"}

    @mcp.tool(
        annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True}
    )
    def cell_delete(name: str, cell_id: str) -> dict:
        """
        Delete a cell from a notebook by its cell ID.
        Use notebook_get to find cell IDs.
        """
        try:
            notebook_mgr.delete_cell(name, cell_id)
            return {"success": True, "message": f"Cell {cell_id} deleted"}
        except (FileNotFoundError, ValueError) as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Failed to delete cell: {e}"}

    @mcp.tool(
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}
    )
    def cell_update(name: str, cell_id: str, source: str) -> dict:
        """
        Update the source content of a cell. For code cells, this clears
        existing outputs and execution count since the code has changed.
        Use notebook_get to find cell IDs.
        """
        try:
            result = notebook_mgr.update_cell(name, cell_id, source)
            return {"success": True, **result}
        except (FileNotFoundError, ValueError) as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Failed to update cell: {e}"}

    @mcp.tool(
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}
    )
    def cell_move(name: str, cell_id: str, new_position: int) -> dict:
        """
        Move a cell to a new position in the notebook.
        new_position is 0-indexed. Use notebook_get to see current positions.
        """
        try:
            notebook_mgr.move_cell(name, cell_id, new_position)
            return {"success": True, "message": f"Cell {cell_id} moved to position {new_position}"}
        except (FileNotFoundError, ValueError) as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Failed to move cell: {e}"}
