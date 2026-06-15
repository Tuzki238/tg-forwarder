from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import threading
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def load_env_file(path: Path = BASE_DIR / ".env") -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_env_file()

import main as forwarder  # noqa: E402
import web_admin  # noqa: E402
from db import get_int_setting, get_setting  # noqa: E402
from init_db import init_db  # noqa: E402


async def run_app(web_host: str | None = None, web_port: int | None = None) -> None:
    forwarder.setup_logging()
    logging.info("Initializing database")
    init_db()
    forwarder.load_env_file()

    host = web_host or get_setting("web_host", "127.0.0.1") or "127.0.0.1"
    port = web_port if web_port is not None else get_int_setting("web_port", 8080)

    server = web_admin.create_server(host, port, initialize=False)
    started = threading.Event()

    def serve_web() -> None:
        started.set()
        web_admin.serve_server(server)

    web_thread = threading.Thread(target=serve_web, name="web-admin", daemon=True)
    web_thread.start()
    started.wait(timeout=2)
    logging.info("Web admin available at http://%s:%s", host, port)

    try:
        await forwarder.main(initialize=False)
    finally:
        logging.info("Stopping Web admin")
        if web_thread.is_alive():
            await asyncio.to_thread(server.shutdown)
            web_thread.join(timeout=5)
        else:
            server.server_close()
        logging.info("Web admin stopped")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start Telegram forwarder and Web admin together.")
    parser.add_argument("--web-host", help="Override settings.web_host for this run")
    parser.add_argument("--web-port", type=int, help="Override settings.web_port for this run")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        with forwarder.SingleInstance(forwarder.LOCK_FILE):
            asyncio.run(run_app(args.web_host, args.web_port))
    except KeyboardInterrupt:
        print("已停止 Telegram 转发系统")
    except OSError as exc:
        print(f"启动失败: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except RuntimeError as exc:
        print(f"启动失败: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
