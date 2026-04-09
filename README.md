# JupyterMCP

A [Model Context Protocol](https://modelcontextprotocol.io) server that gives AI agents full control over Jupyter notebooks — create, read, edit, and execute cells, manage kernels, and optionally route execution to a remote Jupyter Server.

---

## What It Does

JupyterMCP exposes **19 tools** that cover everything an agent needs to work with Jupyter notebooks end-to-end:

| Category | Tools |
|---|---|
| **Notebooks** | `notebook_create`, `notebook_get`, `notebook_list`, `notebook_delete`, `notebook_as_script`, `notebook_execute_all` |
| **Cells** | `cell_add`, `cell_update`, `cell_delete`, `cell_move`, `cell_execute` |
| **Kernels** | `kernel_status`, `kernel_restart`, `kernel_interrupt` |
| **Workspace** | `get_notebook_directory`, `set_notebook_directory` |
| **Remote** | `remote_connect`, `remote_disconnect`, `remote_status` |

Notebooks are always saved as `.ipynb` files on disk. Kernel state (variables, imports) persists between cell executions within the same session.

---

## Installation

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/yourname/JupyterMCP
cd JupyterMCP
uv sync
```

---

## Adding to Claude Code

### Option 1 — CLI (recommended)

```bash
claude mcp add jupyter -- uv run --directory /path/to/JupyterMCP jupyter-mcp
```

To pin notebooks to a specific directory at startup:

```bash
claude mcp add jupyter -- uv run --directory /path/to/JupyterMCP jupyter-mcp --working-dir /path/to/your/notebooks
```

### Option 2 — Project config (`.mcp.json`)

Create or edit `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "jupyter": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "/path/to/JupyterMCP",
        "jupyter-mcp",
        "--working-dir", "/path/to/your/notebooks"
      ]
    }
  }
}
```

### Option 3 — Global config (`~/.claude/settings.json`)

```json
{
  "mcpServers": {
    "jupyter": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/JupyterMCP", "jupyter-mcp"]
    }
  }
}
```

After adding, verify the server is connected:

```
/mcp
```

---

## Configuration

### Working directory

Controls where notebooks are read and written. Defaults to the current working directory when the server starts.

| Method | Example |
|---|---|
| CLI arg | `--working-dir /home/user/notebooks` |
| Environment variable | `CLAUDE_CODE_CWD=/home/user/notebooks` |
| At runtime | Call the `set_notebook_directory` tool |

### Remote Jupyter Server

Route kernel execution to a remote Jupyter Server (e.g., a cloud GPU machine) while keeping notebooks saved locally.

| Method | Example |
|---|---|
| CLI args | `--remote-url http://host:8888 --remote-token mytoken` |
| Environment variables | `JUPYTER_SERVER_URL=http://host:8888 JUPYTER_SERVER_TOKEN=mytoken` |
| At runtime | Call the `remote_connect` tool |

To find your Jupyter token, look at the startup output of your remote Jupyter instance:

```
http://localhost:8888/?token=abc123...
```

---

## Tool Reference

### Notebooks

#### `notebook_create`
Create a new empty `.ipynb` notebook. The `.ipynb` extension is added automatically.
```
name: str  — notebook name, e.g. "analysis" or "analysis.ipynb"
```

#### `notebook_get`
Return the full notebook structure: all cells with their IDs, types, source, execution counts, and outputs. Use the returned cell IDs with `cell_update`, `cell_delete`, `cell_move`, and `cell_execute`.
```
name: str
```

#### `notebook_list`
List all `.ipynb` files in the current working directory.

#### `notebook_delete`
Delete a notebook file and shut down its kernel if running.
```
name: str
```

#### `notebook_as_script`
Return the entire notebook as a single Python string using `# %%` cell markers (compatible with VSCode, Spyder, and nbconvert). Useful for reviewing the notebook as a complete program or asking an agent to analyse its logic.

Code cells are pasted verbatim; markdown cells have each line prefixed with `# `.
```
name:             str
include_markdown: bool = True  — set False to emit only code cells
```

Example output:
```python
# %% [cell 0 · code · id:abc123]
import pandas as pd
df = pd.read_csv("data.csv")

# %% [cell 1 · markdown · id:def456]
# ## Data Cleaning
# Drop rows with missing values.

# %% [cell 2 · code · id:ghi789]
df = df.dropna()
df.head()
```

#### `notebook_execute_all`
Execute all code cells in order. Markdown and raw cells are skipped.
```
name:          str
timeout:       int  = 30    — seconds per cell
stop_on_error: bool = True  — halt at first exception
python_path:   str  = ""    — interpreter to use if no kernel is running yet
```

---

### Cells

#### `cell_add`
Add a new cell to a notebook.
```
name:      str
source:    str
cell_type: str = "code"  — "code", "markdown", or "raw"
position:  int = -1      — 0 = prepend, -1 = append
```
Returns the new cell's `cell_id` and position.

#### `cell_update`
Replace a cell's source. For code cells, clears existing outputs and execution count.
```
name:    str
cell_id: str  — from notebook_get
source:  str
```

#### `cell_delete`
Delete a cell by ID.
```
name:    str
cell_id: str
```

#### `cell_move`
Reorder a cell within the notebook.
```
name:         str
cell_id:      str
new_position: int  — 0-indexed
```

#### `cell_execute`
Execute a single code cell and return its outputs. Saves outputs back to the `.ipynb` file.
```
name:        str
cell_id:     str
timeout:     int = 30   — seconds
python_path: str = ""   — interpreter; only applies when starting a new kernel
```

---

### Kernels

#### `kernel_status`
Get the status (`not_started`, `idle`, or `dead`) and Python interpreter of the kernel for a notebook.
```
name: str
```

#### `kernel_restart`
Restart the kernel, clearing all in-memory state. Saved cell outputs are not affected.
```
name:        str
python_path: str = ""  — switch to a different interpreter on restart
```

#### `kernel_interrupt`
Send an interrupt signal to stop a long-running or infinite-loop cell.
```
name: str
```

---

### Workspace

#### `get_notebook_directory`
Return the current working directory for notebook operations.

#### `set_notebook_directory`
Switch the working directory. All subsequent notebook operations use the new path.
```
path: str  — must already exist
```

---

### Remote Execution

#### `remote_connect`
Connect to a remote Jupyter Server. All kernel operations (start, execute, restart, interrupt) are routed to the remote server. Notebook files are still saved locally.
```
server_url: str  — e.g. "http://hostname:8888"
token:      str  — API token from the Jupyter startup output
```

#### `remote_disconnect`
Disconnect from the remote server, shut down remote kernels, and revert to local execution.

#### `remote_status`
Show whether a remote server is connected and which URL it is using.

---

## Quick Start (with Claude)

Once the server is connected, you can ask Claude things like:

> "Create a notebook called `analysis`, add a cell that loads a CSV from `data.csv` using pandas, and execute it."

> "Show me all the cells in `model_training.ipynb` as a Python script so I can review the logic."

> "Connect to my remote GPU server at `http://10.0.0.5:8888` with token `abc123` and run the training notebook there."

> "Restart the kernel for `analysis.ipynb` and re-execute all cells."
