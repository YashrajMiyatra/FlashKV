#!/usr/bin/env python3
"""
FlashKV Main Entrypoint.
Starts both the Redis-compatible TCP Server (Port 6379)
and the Embedded Real-time Web Dashboard (Port 6380).
"""

import argparse
import asyncio
import signal
import sys
from flashkv.server import FlashKVServer
from flashkv.web.app import WebDashboard

BANNER = r"""
  ______ _           _     _  ____     __
 |  ____| |         | |   | |/ /\ \   / /
 | |__  | | __ _ ___| |__ | ' /  \ \_/ / 
 |  __| | |/ _` / __| '_ \|  <    \   /  
 | |    | | (_| \__ \ | | | . \    | |   
 |_|    |_|\__,_|___/_| |_|_|\_\   |_|   
                                         
 High-Performance In-Memory Store & Vector Engine
"""


async def main() -> None:
    parser = argparse.ArgumentParser(description="FlashKV: Redis-compatible In-Memory Store & Vector Engine")
    parser.add_argument("--host", default="0.0.0.0", help="Host address to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=6379, help="Redis protocol TCP port (default: 6379)")
    parser.add_argument("--web-port", type=int, default=6380, help="Web dashboard HTTP port (default: 6380)")
    parser.add_argument("--aof-file", default="flashkv.aof", help="Path to Append-Only File (default: flashkv.aof)")
    parser.add_argument("--no-aof", action="store_true", help="Disable AOF persistence")
    parser.add_argument("--no-web", action="store_true", help="Disable embedded Web Dashboard")

    args = parser.parse_args()

    print(BANNER)
    server = FlashKVServer(
        host=args.host,
        port=args.port,
        aof_path=args.aof_file,
        enable_aof=not args.no_aof,
    )

    dashboard = None
    if not args.no_web:
        dashboard = WebDashboard(server, host=args.host, port=args.web_port)

    # Start servers
    await server.start()
    if dashboard:
        await dashboard.start()

    print("=" * 60)
    print(f"  Redis RESP Server  : tcp://{args.host}:{args.port}")
    if dashboard:
        print(f"  Web Dashboard      : http://localhost:{args.web_port}")
    print(f"  AOF Persistence    : {'ENABLED (' + args.aof_file + ')' if not args.no_aof else 'DISABLED'}")
    print("=" * 60)
    print("Ready to accept connections. Press Ctrl+C to exit.\n")

    stop_event = asyncio.Event()

    def handle_signal():
        print("\n[!] Shutdown signal received...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            # Signal handling on Windows
            pass

    try:
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        print("[*] Flushing buffers and shutting down...")
        if dashboard:
            await dashboard.stop()
        await server.stop()
        print("[+] Goodbye!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
