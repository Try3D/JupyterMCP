import time
from queue import Empty

from .kernel_manager import KernelRegistry

OUTPUT_MSG_TYPES = {"stream", "display_data", "execute_result", "error"}
MAX_TEXT_LENGTH = 10_000


class CellExecutor:
    def __init__(self, kernel_registry: KernelRegistry):
        self.registry = kernel_registry

    def execute_code(
        self,
        notebook_path: str,
        code: str,
        timeout: float = 30.0,
    ) -> dict:
        entry = self.registry.get_or_start(notebook_path)
        with entry.lock:
            msg_id = entry.client.execute(code, store_history=True)
            outputs, execution_count, status = self._collect_outputs(
                entry.client, msg_id, timeout
            )
        return {
            "status": status,
            "execution_count": execution_count,
            "outputs": self._format_outputs_for_response(outputs),
        }

    def _collect_outputs(
        self, kc, msg_id: str, timeout: float
    ) -> tuple[list[dict], int | None, str]:
        deadline = time.monotonic() + timeout
        outputs: list[dict] = []
        execution_count: int | None = None
        final_status = "ok"

        # Drain IOPub until the kernel goes idle for our request
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Cell execution timed out after {timeout}s")
            try:
                msg = kc.get_iopub_msg(timeout=remaining)
            except Empty:
                raise TimeoutError(f"Cell execution timed out after {timeout}s")

            if msg["parent_header"].get("msg_id") != msg_id:
                continue

            msg_type = msg["header"]["msg_type"]
            content = msg["content"]

            if msg_type == "status":
                if content.get("execution_state") == "idle":
                    break
            elif msg_type in OUTPUT_MSG_TYPES:
                output = self._format_output(msg_type, content)
                if output is not None:
                    outputs.append(output)
                if msg_type == "execute_result":
                    execution_count = content.get("execution_count")
                if msg_type == "error":
                    final_status = "error"

        # Always drain the execute_reply from the shell channel.
        # - For print-only cells there is no execute_result IOPub msg, so the shell
        #   reply is the only place to get execution_count.
        # - For cells that do emit execute_result we already have the count, but we
        #   must still consume the reply so it doesn't pollute the next execution's read.
        shell_deadline = time.monotonic() + 5
        while True:
            remaining = shell_deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                shell_reply = kc.get_shell_msg(timeout=remaining)
            except Empty:
                break
            if (
                shell_reply["parent_header"].get("msg_id") == msg_id
                and shell_reply["header"]["msg_type"] == "execute_reply"
            ):
                if execution_count is None:
                    execution_count = shell_reply["content"].get("execution_count")
                break  # found our reply, done

        return outputs, execution_count, final_status

    def _format_output(self, msg_type: str, content: dict) -> dict | None:
        if msg_type == "stream":
            return {
                "type": "stream",
                "name": content.get("name", "stdout"),
                "text": content.get("text", ""),
            }
        elif msg_type == "execute_result":
            data = content.get("data", {})
            return {
                "type": "execute_result",
                "execution_count": content.get("execution_count"),
                "text": data.get("text/plain", ""),
                "data": data,
            }
        elif msg_type == "display_data":
            data = content.get("data", {})
            return {
                "type": "display_data",
                "text": data.get("text/plain", ""),
                "data": data,
            }
        elif msg_type == "error":
            return {
                "type": "error",
                "ename": content.get("ename", ""),
                "evalue": content.get("evalue", ""),
                "traceback": content.get("traceback", []),
            }
        return None

    def _format_outputs_for_response(self, outputs: list[dict]) -> list[dict]:
        # Merge consecutive stream outputs with the same name
        merged: list[dict] = []
        for out in outputs:
            if (
                out["type"] == "stream"
                and merged
                and merged[-1]["type"] == "stream"
                and merged[-1]["name"] == out["name"]
            ):
                merged[-1]["text"] += out["text"]
            else:
                merged.append(dict(out))

        # Truncate very long text
        for out in merged:
            if out["type"] == "stream" and len(out["text"]) > MAX_TEXT_LENGTH:
                out["text"] = out["text"][:MAX_TEXT_LENGTH] + f"\n... [truncated, {len(out['text'])} chars total]"
            if "text" in out and out["type"] in ("execute_result", "display_data"):
                if len(out["text"]) > MAX_TEXT_LENGTH:
                    out["text"] = out["text"][:MAX_TEXT_LENGTH] + "\n... [truncated]"

        return merged
