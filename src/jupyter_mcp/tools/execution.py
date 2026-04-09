"""Cell execution tools."""

from mcp.server.fastmcp import FastMCP

from ..executor import CellExecutor
from ..kernel_manager import KernelRegistry
from ..notebook_manager import NotebookManager


def register_execution_tools(
    mcp: FastMCP,
    notebook_mgr: NotebookManager,
    kernel_reg: KernelRegistry,
    executor: CellExecutor,
):
    """Register cell execution tools with the MCP server."""

    @mcp.tool(
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}
    )
    def cell_execute(
        name: str,
        cell_id: str,
        timeout: int = 30,
        python_path: str = "",
    ) -> dict:
        """
        Execute a specific code cell and return its output. The kernel state
        persists between executions (variables, imports, etc. remain in memory).
        Only code cells can be executed. Outputs are saved back to the .ipynb file.

        python_path controls which Python interpreter runs the kernel:
        - "" or omitted: uses the server's own Python (sys.executable) the first
          time; subsequent calls reuse the already-running kernel regardless.
        - Absolute path: e.g. "/home/user/myproject/.venv/bin/python"
        - Name on PATH: e.g. "python3.11"
        Only takes effect when a new kernel is being started (no kernel running yet).
        Use kernel_restart to switch an already-running kernel to a different Python.
        """
        try:
            nb = notebook_mgr.read(name)
            _, cell = notebook_mgr.get_cell_by_id(nb, cell_id)
            if cell.cell_type != "code":
                return {"success": False, "error": f"Cannot execute a '{cell.cell_type}' cell. Only code cells can be executed."}

            path = notebook_mgr._path(name)
            kernel_reg.get_or_start(path, python_path=python_path or None)
            result = executor.execute_code(path, cell.source, timeout=float(timeout))

            notebook_mgr.update_cell_outputs(
                name, cell_id,
                outputs=result["outputs"],
                execution_count=result["execution_count"],
            )

            return {"success": True, "cell_id": cell_id, **result}
        except TimeoutError as e:
            return {"success": False, "error": str(e), "timeout": True}
        except (FileNotFoundError, ValueError) as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Execution failed: {e}"}

    @mcp.tool(
        annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}
    )
    def notebook_execute_all(
        name: str,
        timeout: int = 30,
        stop_on_error: bool = True,
        python_path: str = "",
    ) -> dict:
        """
        Execute all code cells in the notebook in order. Markdown and raw cells
        are skipped. If stop_on_error is True (default), execution stops at the
        first cell that raises an exception.
        Returns a summary of results for each code cell executed.

        python_path: which Python to use if no kernel is running yet (see cell_execute).
        """
        try:
            nb = notebook_mgr.read(name)
            path = notebook_mgr._path(name)
            kernel_reg.get_or_start(path, python_path=python_path or None)

            results = []
            for cell in nb.cells:
                if cell.cell_type != "code":
                    continue
                result = executor.execute_code(path, cell.source, timeout=float(timeout))
                notebook_mgr.update_cell_outputs(
                    name, cell.id,
                    outputs=result["outputs"],
                    execution_count=result["execution_count"],
                )
                results.append({"cell_id": cell.id, **result})
                if stop_on_error and result["status"] == "error":
                    return {"success": True, "stopped_early": True, "results": results}

            return {"success": True, "stopped_early": False, "results": results}
        except TimeoutError as e:
            return {"success": False, "error": str(e), "timeout": True}
        except FileNotFoundError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Execution failed: {e}"}
