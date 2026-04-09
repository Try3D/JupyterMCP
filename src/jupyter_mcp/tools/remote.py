"""Remote Jupyter server connection tools."""

from mcp.server.fastmcp import FastMCP

from ..kernel_manager import DelegatingKernelRegistry
from ..remote_kernel_manager import RemoteKernelRegistry


def register_remote_tools(mcp: FastMCP, kernel_reg: DelegatingKernelRegistry):
    """Register remote server connection tools with the MCP server."""

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False})
    def remote_connect(server_url: str, token: str) -> dict:
        """
        Connect to a remote Jupyter Server and route all kernel operations to it.
        Notebooks continue to be saved locally; only code execution runs on the
        remote kernel. Useful for accessing remote compute, GPUs, or data.

        server_url: Base URL of the remote Jupyter Server, e.g. "http://hostname:8888"
        token: API token (the value printed by Jupyter on startup, or set via
               --NotebookApp.token / --ServerApp.token)

        Any currently running remote kernels are shut down before switching.
        """
        try:
            remote = RemoteKernelRegistry(server_url=server_url, token=token)
            remote.verify_connection()
            kernel_reg.set_remote(remote)
            return {
                "success": True,
                "server_url": server_url,
                "message": "Connected to remote Jupyter server. Kernel operations now run remotely.",
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to connect to remote server: {e}"}

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True})
    def remote_disconnect() -> dict:
        """
        Disconnect from the remote Jupyter Server and switch back to local kernels.
        All running remote kernels are shut down.
        """
        if not kernel_reg.has_remote():
            return {"success": True, "message": "No remote connection active; already using local kernels."}
        kernel_reg.clear_remote()
        return {"success": True, "message": "Disconnected. Kernel operations now run locally."}

    @mcp.tool(annotations={"readOnlyHint": True})
    def remote_status() -> dict:
        """
        Show whether a remote Jupyter Server is connected and which URL it is using.
        """
        if not kernel_reg.has_remote():
            return {"success": True, "connected": False, "message": "Using local kernels."}
        return {
            "success": True,
            "connected": True,
            "server_url": kernel_reg.remote_url(),
            "message": "Kernel operations are running on the remote server. Notebooks are saved locally.",
        }
