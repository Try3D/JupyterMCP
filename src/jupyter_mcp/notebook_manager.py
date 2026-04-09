import glob
import os
from typing import Literal

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook, new_raw_cell

NBFORMAT_VERSION = 4


class NotebookManager:
    def __init__(self, working_dir: str):
        self.working_dir = working_dir

    def _path(self, name: str) -> str:
        if not name.endswith(".ipynb"):
            name = name + ".ipynb"
        if os.path.dirname(name):
            raise ValueError(f"Invalid notebook name '{name}': must be a plain filename with no path separators")
        return os.path.join(self.working_dir, name)

    def _name(self, name: str) -> str:
        if not name.endswith(".ipynb"):
            return name + ".ipynb"
        return name

    def create(self, name: str) -> dict:
        path = self._path(name)
        if os.path.exists(path):
            raise FileExistsError(f"Notebook '{self._name(name)}' already exists")
        nb = new_notebook()
        with open(path, "w", encoding="utf-8") as f:
            nbformat.write(nb, f, version=NBFORMAT_VERSION)
        return {"name": self._name(name), "path": path}

    def delete(self, name: str) -> None:
        path = self._path(name)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Notebook '{self._name(name)}' not found")
        os.remove(path)

    def list_notebooks(self) -> list[str]:
        pattern = os.path.join(self.working_dir, "*.ipynb")
        paths = glob.glob(pattern)
        return sorted(os.path.basename(p) for p in paths)

    def read(self, name: str) -> nbformat.NotebookNode:
        path = self._path(name)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Notebook '{self._name(name)}' not found")
        with open(path, "r", encoding="utf-8") as f:
            return nbformat.read(f, as_version=NBFORMAT_VERSION)

    def write(self, name: str, nb: nbformat.NotebookNode) -> None:
        path = self._path(name)
        nbformat.validate(nb)
        with open(path, "w", encoding="utf-8") as f:
            nbformat.write(nb, f, version=NBFORMAT_VERSION)

    def get_cell_by_id(
        self, nb: nbformat.NotebookNode, cell_id: str
    ) -> tuple[int, nbformat.NotebookNode]:
        for idx, cell in enumerate(nb.cells):
            if cell.id == cell_id:
                return idx, cell
        raise ValueError(f"Cell '{cell_id}' not found in notebook")

    def add_cell(
        self,
        name: str,
        cell_type: Literal["code", "markdown", "raw"],
        source: str,
        position: int = -1,
    ) -> dict:
        nb = self.read(name)
        if cell_type == "code":
            cell = new_code_cell(source=source)
        elif cell_type == "markdown":
            cell = new_markdown_cell(source=source)
        elif cell_type == "raw":
            cell = new_raw_cell(source=source)
        else:
            raise ValueError(f"Invalid cell_type '{cell_type}'. Must be code, markdown, or raw")

        if position == -1:
            nb.cells.append(cell)
            actual_position = len(nb.cells) - 1
        else:
            actual_position = max(0, min(position, len(nb.cells)))
            nb.cells.insert(actual_position, cell)

        self.write(name, nb)
        return {"cell_id": cell.id, "position": actual_position, "cell_type": cell_type}

    def delete_cell(self, name: str, cell_id: str) -> None:
        nb = self.read(name)
        idx, _ = self.get_cell_by_id(nb, cell_id)
        nb.cells.pop(idx)
        self.write(name, nb)

    def update_cell(self, name: str, cell_id: str, source: str) -> dict:
        nb = self.read(name)
        _, cell = self.get_cell_by_id(nb, cell_id)
        cell.source = source
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
        self.write(name, nb)
        return {"cell_id": cell_id, "cell_type": cell.cell_type}

    def move_cell(self, name: str, cell_id: str, new_position: int) -> None:
        nb = self.read(name)
        idx, cell = self.get_cell_by_id(nb, cell_id)
        nb.cells.pop(idx)
        clamped = max(0, min(new_position, len(nb.cells)))
        nb.cells.insert(clamped, cell)
        self.write(name, nb)

    def update_cell_outputs(
        self,
        name: str,
        cell_id: str,
        outputs: list,
        execution_count: int | None,
    ) -> None:
        nb = self.read(name)
        _, cell = self.get_cell_by_id(nb, cell_id)
        if cell.cell_type != "code":
            return
        # Convert our output dicts to nbformat output nodes
        nbformat_outputs = []
        for out in outputs:
            out_type = out.get("type")
            if out_type == "stream":
                nbformat_outputs.append(
                    nbformat.v4.new_output(
                        output_type="stream",
                        name=out.get("name", "stdout"),
                        text=out.get("text", ""),
                    )
                )
            elif out_type == "execute_result":
                nbformat_outputs.append(
                    nbformat.v4.new_output(
                        output_type="execute_result",
                        data=out.get("data", {"text/plain": out.get("text", "")}),
                        metadata={},
                        execution_count=out.get("execution_count") or execution_count,
                    )
                )
            elif out_type == "display_data":
                nbformat_outputs.append(
                    nbformat.v4.new_output(
                        output_type="display_data",
                        data=out.get("data", {"text/plain": out.get("text", "")}),
                        metadata={},
                    )
                )
            elif out_type == "error":
                nbformat_outputs.append(
                    nbformat.v4.new_output(
                        output_type="error",
                        ename=out.get("ename", ""),
                        evalue=out.get("evalue", ""),
                        traceback=out.get("traceback", []),
                    )
                )
        cell.outputs = nbformat_outputs
        cell.execution_count = execution_count
        self.write(name, nb)

    def serialize_notebook(self, nb: nbformat.NotebookNode, name: str = "") -> dict:
        return {
            "name": name,
            "nbformat": nb.nbformat,
            "nbformat_minor": nb.nbformat_minor,
            "metadata": dict(nb.metadata),
            "cell_count": len(nb.cells),
            "cells": [self.serialize_cell(c) for c in nb.cells],
        }

    def serialize_cell(self, cell: nbformat.NotebookNode) -> dict:
        result = {
            "id": cell.id,
            "cell_type": cell.cell_type,
            "source": cell.source,
            "metadata": dict(cell.metadata),
        }
        if cell.cell_type == "code":
            result["execution_count"] = cell.get("execution_count")
            result["outputs"] = [dict(o) for o in cell.get("outputs", [])]
        return result
