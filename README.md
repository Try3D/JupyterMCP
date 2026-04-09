# JupyterMCP

[![PyPI](https://img.shields.io/pypi/v/mcp-jupyter-server)](https://pypi.org/project/mcp-jupyter-server/)
[![Python](https://img.shields.io/pypi/pyversions/mcp-jupyter-server)](https://pypi.org/project/mcp-jupyter-server/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An MCP server that gives AI agents full control over Jupyter notebooks — create, read, edit, and execute cells, manage kernels, and connect to remote Jupyter Servers.

Works with [Claude Code](https://claude.ai/code), [Claude Desktop](https://claude.ai/download), and any other MCP-compatible client.

---

## Installation

```bash
pip install mcp-jupyter-server
```

Or with uv:

```bash
uv add mcp-jupyter-server
```

---

## Adding to Claude Code

### Option 1 — CLI (recommended)

```bash
claude mcp add jupyter -- jupyter-mcp
```

Pin notebooks to a specific directory at startup:

```bash
claude mcp add jupyter -- jupyter-mcp --working-dir /path/to/your/notebooks
```

### Option 2 — Project config (`.mcp.json`)

```json
{
  "mcpServers": {
    "jupyter": {
      "command": "jupyter-mcp",
      "args": ["--working-dir", "/path/to/your/notebooks"]
    }
  }
}
```

### Option 3 — Global config (`~/.claude/settings.json`)

```json
{
  "mcpServers": {
    "jupyter": {
      "command": "jupyter-mcp"
    }
  }
}
```

After adding, verify the connection with `/mcp` in Claude Code.

---

## Adding to Claude Desktop

Edit your config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "jupyter": {
      "command": "jupyter-mcp",
      "args": ["--working-dir", "/path/to/your/notebooks"]
    }
  }
}
```

Restart Claude Desktop after saving.

---

## What You Can Do

JupyterMCP exposes 19 tools across five categories:

| Category | Tools |
|---|---|
| **Notebooks** | `notebook_create`, `notebook_get`, `notebook_list`, `notebook_delete`, `notebook_as_script`, `notebook_execute_all` |
| **Cells** | `cell_add`, `cell_update`, `cell_delete`, `cell_move`, `cell_execute` |
| **Kernels** | `kernel_status`, `kernel_restart`, `kernel_interrupt` |
| **Workspace** | `get_notebook_directory`, `set_notebook_directory` |
| **Remote** | `remote_connect`, `remote_disconnect`, `remote_status` |

Notebooks are always saved as `.ipynb` files. Kernel state (variables, imports) persists between cell executions within the same session.

### Example prompts

> *"Create a notebook called `analysis`, add a cell that loads `data.csv` with pandas, and execute it."*

> *"Show me `model_training.ipynb` as a single Python script so I can review the logic."*

> *"Something's wrong in cell 3 of `pipeline.ipynb` — read the notebook, fix it, and re-run."*

> *"Connect to my remote GPU server at `http://10.0.0.5:8888` and run the training notebook there."*

---

## Configuration

### Working directory

Controls where notebooks are read from and written to. Defaults to the current working directory.

| Method | Example |
|---|---|
| CLI arg | `--working-dir /home/user/notebooks` |
| Environment variable | `CLAUDE_CODE_CWD=/home/user/notebooks` |
| At runtime | `set_notebook_directory` tool |

### Remote Jupyter Server

Route kernel execution to a remote Jupyter Server while keeping notebooks saved locally. Useful for cloud GPUs, remote data, or shared compute.

| Method | Example |
|---|---|
| CLI args | `--remote-url http://host:8888 --remote-token mytoken` |
| Environment variables | `JUPYTER_SERVER_URL=http://host:8888` / `JUPYTER_SERVER_TOKEN=mytoken` |
| At runtime | `remote_connect` tool |

Find your Jupyter token in the server startup output:

```
http://localhost:8888/?token=abc123...
```

---

## Tool Reference

### Notebooks

#### `notebook_create`
Create a new empty notebook. The `.ipynb` extension is added automatically.
```
name: str
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
Return the entire notebook as a single Python string using `# %%` cell markers (compatible with VS Code, Spyder, and nbconvert). Useful for letting an agent read and reason about a notebook as a complete program.

Code cells are pasted verbatim; markdown cells have each line prefixed with `# `.

```
name:             str
include_markdown: bool = True
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
timeout:       int  = 30
stop_on_error: bool = True
python_path:   str  = ""
```

---

### Cells

#### `cell_add`
Add a new cell to a notebook.
```
name:      str
source:    str
cell_type: str = "code"   — "code", "markdown", or "raw"
position:  int = -1       — 0 = prepend, -1 = append
```
Returns the new cell's `cell_id` and position.

#### `cell_update`
Replace a cell's source. For code cells, clears existing outputs and execution count.
```
name:    str
cell_id: str   — from notebook_get
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
new_position: int   — 0-indexed
```

#### `cell_execute`
Execute a single code cell and return its outputs. Saves outputs back to the `.ipynb` file.
```
name:        str
cell_id:     str
timeout:     int = 30
python_path: str = ""   — only applies when starting a new kernel
```

---

### Kernels

#### `kernel_status`
Get the current status (`not_started`, `idle`, or `dead`) and Python interpreter of a notebook's kernel.
```
name: str
```

#### `kernel_restart`
Restart the kernel, clearing all in-memory state. Saved cell outputs are not affected.
```
name:        str
python_path: str = ""   — switch to a different interpreter on restart
```

#### `kernel_interrupt`
Send an interrupt signal to stop a long-running or stuck cell.
```
name: str
```

---

### Workspace

#### `get_notebook_directory`
Return the current working directory for notebook operations.

#### `set_notebook_directory`
Change the working directory. All subsequent notebook operations use the new path.
```
path: str   — must already exist
```

---

### Remote Execution

#### `remote_connect`
Connect to a remote Jupyter Server. All kernel operations are routed there; notebooks are still saved locally.
```
server_url: str   — e.g. "http://hostname:8888"
token:      str
```

#### `remote_disconnect`
Disconnect from the remote server, shut down remote kernels, and revert to local execution.

#### `remote_status`
Show whether a remote server is connected and which URL it is using.

---

## Architecture

```
src/jupyter_mcp/
├── server.py                — FastMCP server, CLI arg parsing
├── notebook_manager.py      — Read/write/serialize .ipynb files
├── kernel_manager.py        — Local kernel lifecycle
├── remote_kernel_manager.py — Remote kernel lifecycle (REST + WebSocket)
├── executor.py              — Cell execution and output collection
└── tools/
    ├── notebooks.py         — notebook_* tools
    ├── cells.py             — cell_* tools
    ├── execution.py         — cell_execute, notebook_execute_all
    ├── kernel.py            — kernel_* tools
    └── remote.py            — remote_* tools
```

Uses **stdio transport** — runs as a subprocess of the MCP client. Notebooks are standard `.ipynb` files and can be opened in JupyterLab, VS Code, or any Jupyter-compatible editor at any time.

---

## Contributing

```bash
git clone https://github.com/Try3D/JupyterMCP
cd JupyterMCP
uv sync
```

---

## License

MIT
