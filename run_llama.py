"""Terminal-only chat client for local GGUF models via llama-server.

Reusable GUI-free entry point: picks a model, starts llama-server, waits for
health, then streams a chat in the console.
"""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.config import LOG_PATH, MODEL_DIR
from core.http_utils import port_open
from core.llama import (kill_all_servers, start_server_process, stop_process,
                        wait_for_server)


def pick_model():
    models = sorted(MODEL_DIR.glob("*.gguf"))
    if not models:
        print(f"No .gguf files in {MODEL_DIR}")
        sys.exit(1)

    print("Available models:")
    for i, model in enumerate(models, 1):
        size_mb = model.stat().st_size / (1024 * 1024)
        print(f"  [{i}] {model.name} ({size_mb:.0f} MB)")

    while True:
        choice = input("\nSelect model number (or 'q' to quit): ").strip()
        if choice.lower() == "q":
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                return models[idx]
            print("Invalid selection.")
        except ValueError:
            print("Enter a valid number.")


def chat_loop(port):
    from core.http_utils import http_open

    url = f"http://127.0.0.1:{port}/v1/chat/completions"
    messages = []
    print("\n=== Chat started (type 'quit' to exit, 'clear' to reset history) ===\n", flush=True)

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input.lower() == "quit":
            break
        if user_input.lower() == "clear":
            messages.clear()
            print("History cleared.\n")
            continue

        messages.append({"role": "user", "content": user_input})

        payload = json.dumps({"messages": messages, "stream": True}).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"})

        try:
            resp = http_open(req, timeout=300)
            print("Assistant: ", end="", flush=True)
            assistant_content = ""
            in_thinking = False

            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk["choices"][0].get("delta", {})
                    reasoning = delta.get("reasoning_content", "")
                    if reasoning:
                        if not in_thinking:
                            print("[thinking...] ", end="", flush=True)
                            in_thinking = True
                    content = delta.get("content", "")
                    if content:
                        if in_thinking:
                            print("\n", end="", flush=True)
                            in_thinking = False
                        print(content, end="", flush=True)
                        assistant_content += content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

            print(flush=True)
            messages.append({"role": "assistant", "content": assistant_content})

        except KeyboardInterrupt:
            print("\nInterrupted.")
            messages.pop()
            break
        except Exception as e:
            print(f"\n[Request failed: {type(e).__name__}: {e}]")
            print("Try again.")
            messages.pop()
            continue


def main():
    if not pick_model_path_check():
        return
    model = pick_model()
    if model is None:
        return

    port = input("Port [8081]: ").strip() or "8081"
    ctx_size = input("Context size [4096]: ").strip() or "4096"
    n_gpu_layers = input("GPU layers [0]: ").strip() or "0"

    if port_open(port):
        print(f"WARNING: port {port} is already in use. Stop the other server or pick another port.")

    print(f"\nStarting server with {model.name}")
    print("Server logs -> llama_server.log (terminal kept clean for chat)")

    try:
        process, log_file = start_server_process(
            model, port, ctx=ctx_size, n_gpu_layers=n_gpu_layers, log_path=LOG_PATH)
    except OSError as e:
        print(f"Failed to start server: {e}")
        sys.exit(1)

    try:
        if not wait_for_server(process, port, LOG_PATH):
            print("Server failed to start. See llama_server.log")
            sys.exit(1)

        print(f"Server is ready on http://127.0.0.1:{port}")
        chat_loop(port)
    finally:
        print("Stopping server...")
        stop_process(process, log_file)
        print("Server stopped.")


def pick_model_path_check():
    from core.config import LLAMA_SERVER
    if not LLAMA_SERVER.exists():
        print(f"Not found: {LLAMA_SERVER}")
        return False
    return True


if __name__ == "__main__":
    import atexit

    # Kill leftovers from a previous crash first
    kill_all_servers()
    atexit.register(kill_all_servers)
    try:
        main()
    finally:
        kill_all_servers()
