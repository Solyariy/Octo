# Driving the GPU PC over SSH (`ssh pc`) + llama-server: Handoff

*Date: 2026-11-17 · Purpose: everything needed to run GPU work on the user's Ubuntu PC from the Mac session; source material for future skills · Companion to `docs/recipe-model-benchmark-handoff.md`*

## 1. Where things stand

- From the Mac session, `ssh pc` works non-interactively, so the agent runs every PC command as `ssh pc '<cmd>'`.
- The Octo repo lives on the PC at `~/Work/Octo`, as an **rsync copy of the Mac working tree** (not a git clone). Uncommitted Mac changes reach the PC by re-syncing.
- CUDA torch, `uv`, the HF models, the GGUF models and a CUDA build of llama.cpp are all in place and verified.

## 2. Key facts

| Item | Value | Status |
|---|---|---|
| PC OS | Ubuntu 26.04.1 LTS, x86_64 | Measured |
| GPU | NVIDIA GeForce RTX 4060 Ti, 16380 MiB, driver 595.99.02 | Measured (`nvidia-smi`) |
| CPU / RAM / disk | 12 threads / 30 GB RAM / 457 GB NVMe (≈330 GB free after models) | Measured |
| LAN IP | 192.168.31.49 (interface `enp6s0`, DHCP, so it can change) | Given by the user |
| Mac IP | 192.168.31.81 (same /24) | Measured |
| PC user | `oleksandr-skoromnov` | Given |
| SSH key (Mac) | `~/.ssh/id_ed25519` (ed25519, **no passphrase**, comment `mac-octo->pc`) | Created by the agent |
| Mac SSH alias | `~/.ssh/config`: `Host pc` / `HostName 192.168.31.49` / `User oleksandr-skoromnov` / `IdentityFile ~/.ssh/id_ed25519` | Created by the agent |
| uv on PC | `~/.local/bin/uv` (0.13.8). Not on PATH in non-interactive SSH, so use the full path | Measured |
| Python env | `~/Work/Octo/.venv` (Python 3.13 via uv), torch `2.13.0+cu130`, `cuda.is_available()=True`, bf16 supported | Measured |
| PC system python | 3.14.4 (unused) | Measured |
| ffmpeg | No system ffmpeg; the project uses the `imageio-ffmpeg` binary | Measured |
| llama.cpp | `~/Work/llama.cpp`, commit `7d7f02875` (2026-11-08), `GGML_CUDA=ON`, binaries in `~/Work/llama.cpp/build/bin/` (`llama-server`, `llama-cli`, `llama-bench`, …) | Measured |
| llama-swap | Config at `~/Work/llama/config.yaml` (the user's own setup: models `qwen3-8b`, `gemma3-4b` via `-hf`, ports from 10001, `--flash-attn on --jinja -ngl 999`) | Read; not used by Octo |
| Models | `~/Work/Octo/models`: HF cache layout. Actual bytes are in the shared Xet store `models/blobs/` (65 GB+); the per-repo folders only hold symlinks, so `du` on them looks tiny | Measured |
| Remote Control | `claude rc` on the PC did **not** show up in the Mac session's agent list; SSH was used instead | Observed |

## 3. Decisions

- **SSH from the Mac session, not Claude Remote Control.** With SSH, one agent can rsync uncommitted code, start jobs and pull results back. With Remote Control, the PC-side Claude would need a git push plus a manual copy of `temp/`.
- **rsync instead of git clone.** No commit is needed to test, and code edits on the Mac sync in seconds.
- **Model weights and `.venv` are built on the PC**, never synced: the venv is platform-specific, and syncing tens of GB is slower than downloading from HF.
- **The PC's `temp/recipes/cache` holds CUDA timings.** The Mac-timed `hf-*` caches were moved to `temp/recipes/cache-mac/` on the PC. On the Mac, PC caches and logs are copied into `temp/recipes/pc/`, so they don't overwrite the Mac caches.
- **Never delete test data on either machine** (user rule): copy, don't move.
- **Rejected:** an NVIDIA eGPU on the Mac (Apple Silicon has no NVIDIA drivers); running from a network-mounted repo (venv and weights must be on local disk); a USB-C cable link (not a reliable Mac↔PC network).

## 4. Working commands

### One-time SSH setup (already done)

```bash
# Mac
ssh-keygen -t ed25519 -N "" -C "mac-octo->pc" -f ~/.ssh/id_ed25519
printf '\nHost pc\n  HostName 192.168.31.49\n  User oleksandr-skoromnov\n  IdentityFile ~/.ssh/id_ed25519\n' >> ~/.ssh/config
# PC (run there by the user; ssh-copy-id from the Mac's own terminal failed, see Gotchas)
sudo apt install openssh-server
mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '<contents of ~/.ssh/id_ed25519.pub>' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
# PC: uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Health check

```bash
nc -z -G 5 192.168.31.49 22 && ssh -o BatchMode=yes pc 'echo ok; nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total --format=csv,noheader'
```

### Sync code from the Mac (run from the repo root)

```bash
# code only (most common)
rsync -az --exclude='.venv/' --exclude='.venv-cosmos/' --exclude='/models/' --exclude='/qdrant_data/' \
  --exclude='.idea/' --exclude='.DS_Store' --exclude='__pycache__/' --exclude='/temp/' ./ pc:~/Work/Octo/
# first sync / data too: drop --exclude='/temp/' and add --exclude='/temp/*.tar.gz'
```

macOS ships openrsync: use `--stats`, because `--info=stats1` is not supported.

### PC environment

```bash
ssh pc 'cd ~/Work/Octo && ~/.local/bin/uv sync && .venv/bin/python -c "import torch;print(torch.cuda.is_available())"'
```

### Run a long job in the background (the pattern that works)

```bash
ssh pc 'cd ~/Work/Octo && PYTHONUNBUFFERED=1 LLAMA_SERVER_BIN=$HOME/Work/llama.cpp/build/bin/llama-server \
  setsid nohup .venv/bin/python -m cli.recipe_bench run --pipelines <a,b> > temp/logs/<name>.log 2>&1 < /dev/null & disown; echo started' </dev/null
```

- `setsid nohup … < /dev/null & disown` plus a local `</dev/null`: the job survives the SSH session ending, and SSH returns at once. Without these, the SSH call hangs until the tool times out.
- `PYTHONUNBUFFERED=1`: otherwise prints sit in a buffer and the log looks empty for minutes.

### Wait for a job to finish (from the Mac, as a background Bash task)

```bash
sleep 10; until ! ssh pc 'pgrep -f "^\.venv/bin/python -m cli\.recipe_bench run" >/dev/null'; do sleep 30; done
ssh pc 'cd ~/Work/Octo && grep -aE "Traceback|Error:" temp/logs/<name>.log | tail -3; grep -aE "reels=|Reports in" temp/logs/<name>.log'
```

The pattern **must be anchored** (`^\.venv/bin/python …`); see Gotchas.

### Progress, GPU and logs

```bash
ssh pc 'pgrep -af "^\.venv/bin/python -m cli"; nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader'
ssh pc 'tail -c 1500 ~/Work/Octo/temp/logs/<name>.log | tr "\r" "\n" | sed "s/\x1b\[[0-9;]*m//g" | grep -v "^$" | tail -8'
# follow live from the Mac prompt:  ! ssh pc tail -f Work/Octo/temp/logs/<name>.log
```

### Pull results back to the Mac (copy, never move)

```bash
rsync -az pc:~/Work/Octo/temp/recipes/runs/ temp/recipes/runs/
rsync -az pc:~/Work/Octo/temp/logs/ pc:~/Work/Octo/temp/recipes/logs temp/recipes/pc/logs/
rsync -az pc:~/Work/Octo/temp/recipes/cache temp/recipes/pc/
```

### Ad-hoc Python on the PC

Copy the script with `scp` to `/tmp/x.py`, then run `ssh pc 'cd ~/Work/Octo && PYTHONPATH=. .venv/bin/python /tmp/x.py'`. A script outside the repo needs `PYTHONPATH=.` to import `src`.

### Peak VRAM while something runs

```bash
ssh pc '(while sleep 5; do nvidia-smi --query-gpu=memory.used --format=csv,noheader; done > /tmp/vram.txt) & W=$!; <command>; kill $W; sort -n /tmp/vram.txt | tail -1'
```

## 5. llama-server (Octo `llamacpp` backend)

- Code: `src/recipe_parser/backends/llamacpp.py` → `LlamaCppTextGenerator`. Specs live in `src/recipe_parser/models.py` (`backend="llamacpp"`, `gguf_file=`, `server_args=`).
- Binary: the `LLAMA_SERVER_BIN` setting/env (default `llama-server` on PATH). On the PC, pass `LLAMA_SERVER_BIN=$HOME/Work/llama.cpp/build/bin/llama-server` on the command line. Don't put it in `.env`: the Mac's `.env` is rsynced over the PC's.
- `download()` uses `hf_hub_download(repo, gguf_file, cache_dir=MODELS_PATH)`, so only the one quant downloads (`cli.recipe_bench download-models` does this).
- Launch flags: `--model <gguf> --host 127.0.0.1 --port <free> --n-gpu-layers 999 --flash-attn on --jinja --ctx-size 16384 --parallel 1 [server_args]`.
- Readiness: poll `GET /health` until 200 (timeout 600 s). If the process exits, the error includes the tail of the log.
- Request: `POST /v1/chat/completions` with `{"messages", "max_tokens", "temperature": 0, "chat_template_kwargs": {"enable_thinking": false}}`, reading `choices[0].message.content`.
- Logs: `temp/recipes/logs/<slug>.log` on the PC. Useful lines: `grep -E "eval time" <log>` gives prompt and decode tokens/s.
- `unload()` terminates the server (kills it after 30 s), keeping the benchmark at one model in VRAM at a time.

### Measured fits on the RTX 4060 Ti 16 GB

| GGUF | File size | Flags | VRAM | Decode tok/s | Prefill tok/s |
|---|---|---|---|---|---|
| gemma-4-12b-it-qat-q4_0 | 6.5 GB | — | fits | 34 | 1243 |
| gemma-4-26B_q4_0-it (MoE A4B) | 13.45 GB | — | fits | 79 | 1607 |
| Qwen3.5-27B-UD-Q3_K_XL (dense) | 13.45 GB | — | fits | 17 | 617 |
| Qwen3.5-35B-A3B-UD-Q4_K_XL (MoE A3B) | 20.7 GB | `--n-cpu-moe 16` | 14.3 GB peak | 56 | 410 |
| Qwen3.5-9B-Q8_0 | 8.9 GB | — | fits | (not measured separately) | — |

Rule of thumb: about 13.5 GB of weights fully on the GPU, with a 16k context and flash attention (Gemma 4 sliding-window attention and Qwen3.5's hybrid linear attention keep the KV cache small). Anything larger has to be MoE with `--n-cpu-moe N` (30 GB of system RAM is available). Decode speed tracks active parameters × bits per weight against about 288 GB/s of memory bandwidth.

### Finding quant sizes before downloading

```bash
curl -s "https://huggingface.co/api/models/<org>/<repo>/tree/main" | python3 -c "import json,sys;[print(f\"{(f.get('lfs',{}).get('size') or f.get('size',0))/2**30:6.2f} GiB {f['path']}\") for f in json.load(sys.stdin) if f['path'].endswith('.gguf')]"
# list repos: https://huggingface.co/api/models?author=<org>&search=<name>&limit=60
```

## 6. Gotchas

- **`pgrep -f "<pattern>"` matches its own SSH command line.** `ssh pc 'pgrep -f "recipe_bench run"'` runs as `bash -c '… recipe_bench run …'`, which matches itself, so wait loops never exit. Anchor the pattern: `pgrep -f "^\.venv/bin/python -m cli\.recipe_bench run"`.
- **"No route to host" from the user's own Mac terminal while the agent's session connects fine:** macOS Local Network privacy blocks the terminal app. Fix it in System Settings → Privacy & Security → Local Network, or install the key from the PC side (section 4).
- **`ssh-copy-id` needs a typed password**, and the agent can't type passwords. Have the user append the public key on the PC instead.
- **The PC goes offline (sleeps or is switched off) between sessions**: "Operation timed out" or "Host is down". Check with `nc -z -G 5 192.168.31.49 22` and ask the user to wake it. The IP is from DHCP and may change.
- **The launching SSH call can hit the 120 s tool timeout** even with `setsid nohup`, unless a local `</dev/null` is added. The job still runs; the "completed" notification is only the SSH session closing.
- **Buffered output:** run Python with `PYTHONUNBUFFERED=1`, or progress lines won't appear in the log.
- **Model folders look empty under `du`:** the HF Xet cache keeps bytes in `models/blobs/`. Find files with `find models -path "*snapshots*" -name "*.gguf"`.
- **`.env` is shared:** it is rsynced from the Mac, so PC-only settings go on the command line as env vars.
- **Transformers on CUDA:** Gemma 4 E4B bf16 (15 GB) runs out of memory unless its per-layer embedding table stays on CPU (`cpu_modules`, already in the spec). Qwen3.5 warns about missing `flash-linear-attention` / `causal_conv1d` (slow fallback, still correct).

## 7. Next steps / skill ideas

- [ ] Turn sections 4 and 5 into skills, for example:
  - `pc-run`: health check, then sync, then start a background job, then wait with the anchored pgrep, then pull results;
  - `pc-llama`: choose a quant that fits 16 GB, download one GGUF, smoke-test speed and VRAM.
- [ ] Optional: give the PC a static DHCP lease or an mDNS name so `HostName` survives IP changes
- [ ] Optional: add a passphrase to the SSH key and use ssh-agent, if keeping a passphrase-less key is not acceptable to the user
- [ ] Optional: install `flash-linear-attention` and `causal_conv1d` in the PC venv

*Sources: commands run in this session (`nvidia-smi`, `lsb_release`, `free`, `df`, `uv`, torch checks, llama-server logs, HF API listings); user-provided IP, username and setup steps. The SSH key and alias were created by the agent. VRAM and speed numbers are single-run measurements.*
