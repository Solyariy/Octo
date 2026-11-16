"""llama.cpp backend: GGUF text generators served by a `llama-server` child process.

Quantised GGUFs let models larger than VRAM-sized bf16 checkpoints run on one 16 GB GPU (MoE
experts can stay in system RAM via `--n-cpu-moe`). One server per loaded model, bound to
localhost on a free port; `unload` stops it, so the benchmark's one-model-at-a-time rule holds.
"""

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from huggingface_hub import hf_hub_download

from src.recipe_parser.backends.base import TextGenerator
from src.recipe_parser.models import ParserModelsEnum
from src.recipe_parser.prompts import Message
from src.settings import main_settings

CTX_SIZE = 16384
READY_TIMEOUT_S = 600
REQUEST_TIMEOUT_S = 900
LOG_TAIL_CHARS = 2000


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class LlamaCppTextGenerator(TextGenerator):
    def __init__(self, model: ParserModelsEnum):
        super().__init__(model)
        if not self.spec.gguf_file:
            raise ValueError(f"{model.value}: llamacpp specs need `gguf_file`")
        self.process: subprocess.Popen | None = None
        self.port = 0
        self.log_path = main_settings.RECIPES_TEMP_DIR_PATH / "logs" / f"{model.value}.log"

    def download(self) -> Path:
        """Fetch (or reuse) only the one GGUF file, not the whole multi-quant repo."""
        return Path(
            hf_hub_download(
                self.repo,
                self.spec.gguf_file,
                cache_dir=main_settings.MODELS_PATH,
                token=main_settings.HF_AUTH_TOKEN.get_secret_value(),
            )
        )

    @property
    def _url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _load(self) -> None:
        weights = self.download()
        self.port = _free_port()
        command = [
            main_settings.LLAMA_SERVER_BIN,
            "--model",
            str(weights),
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--n-gpu-layers",
            "999",
            "--flash-attn",
            "on",
            "--jinja",
            "--ctx-size",
            str(CTX_SIZE),
            "--parallel",
            "1",
            *self.spec.server_args,
        ]
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("w") as log:
            self.process = subprocess.Popen(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        self._wait_ready()

    def _wait_ready(self) -> None:
        deadline = time.monotonic() + READY_TIMEOUT_S
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self._fail(f"llama-server exited with code {self.process.returncode}")
            try:
                with urllib.request.urlopen(f"{self._url}/health", timeout=5) as response:
                    if response.status == 200:
                        return
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                pass
            time.sleep(1)
        self._fail(f"llama-server not ready after {READY_TIMEOUT_S} s")

    def _fail(self, reason: str) -> None:
        self._unload()
        tail = self.log_path.read_text(errors="replace")[-LOG_TAIL_CHARS:]
        raise RuntimeError(f"{self.info.value}: {reason}; log {self.log_path}:\n{tail}")

    def _unload(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process = None

    def generate(self, messages: list[Message], max_new_tokens: int) -> str:
        self.load()
        body = {
            "messages": messages,
            "max_tokens": max_new_tokens,
            "temperature": 0,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        request = urllib.request.Request(
            f"{self._url}/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:
            payload = json.load(response)
        return (payload["choices"][0]["message"].get("content") or "").strip()
