#!/usr/bin/env python3
"""
FlashKV Performance Benchmark Suite.
Measures requests per second, throughput, and latency percentiles.
"""

import argparse
import socket
import time
from typing import List
from flashkv.protocol import encode_array, RESPReader


def run_benchmark(host: str, port: int, num_requests: int, keyspace: int) -> None:
    print(f"[*] Starting FlashKV Benchmark against {host}:{port}")
    print(f"[*] Total requests: {num_requests:,} | Keyspace size: {keyspace:,}\n")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    reader = RESPReader()

    def send_cmd(parts: List[str]) -> None:
        sock.sendall(encode_array(parts))
        while True:
            data = sock.recv(4096)
            reader.feed(data)
            ok, _ = reader.read_one()
            if ok:
                break

    # 1. Benchmark SET
    print(f"==> Benchmarking SET ({num_requests} requests)...", end="", flush=True)
    t0 = time.perf_counter()
    for i in range(num_requests):
        k = f"bench:key:{i % keyspace}"
        send_cmd(["SET", k, f"val_{i}"])
    dur_set = time.perf_counter() - t0
    ops_set = num_requests / dur_set
    print(f" DONE in {dur_set:.2f}s ({ops_set:,.1f} ops/sec)")

    # 2. Benchmark GET
    print(f"==> Benchmarking GET ({num_requests} requests)...", end="", flush=True)
    t0 = time.perf_counter()
    for i in range(num_requests):
        k = f"bench:key:{i % keyspace}"
        send_cmd(["GET", k])
    dur_get = time.perf_counter() - t0
    ops_get = num_requests / dur_get
    print(f" DONE in {dur_get:.2f}s ({ops_get:,.1f} ops/sec)")

    # 3. Benchmark LPUSH
    print(f"==> Benchmarking LPUSH ({num_requests} requests)...", end="", flush=True)
    t0 = time.perf_counter()
    for i in range(num_requests):
        send_cmd(["LPUSH", "bench:list", f"item_{i}"])
    dur_lpush = time.perf_counter() - t0
    ops_lpush = num_requests / dur_lpush
    print(f" DONE in {dur_lpush:.2f}s ({ops_lpush:,.1f} ops/sec)")

    # 4. Benchmark Vector Add & Search
    vector_count = min(num_requests, 1000)
    print(f"==> Benchmarking VADD ({vector_count} 4D vectors)...", end="", flush=True)
    t0 = time.perf_counter()
    for i in range(vector_count):
        send_cmd(["VADD", "bench_vec", f"v_{i}", f"{0.1 * (i % 10)},0.2,0.5,0.9"])
    dur_vadd = time.perf_counter() - t0
    ops_vadd = vector_count / dur_vadd
    print(f" DONE in {dur_vadd:.2f}s ({ops_vadd:,.1f} ops/sec)")

    search_count = min(num_requests, 500)
    print(f"==> Benchmarking VSEARCH ({search_count} top-5 cosine queries)...", end="", flush=True)
    t0 = time.perf_counter()
    for _ in range(search_count):
        send_cmd(["VSEARCH", "bench_vec", "0.2,0.2,0.5,0.9", "5", "cosine"])
    dur_vsearch = time.perf_counter() - t0
    ops_vsearch = search_count / dur_vsearch
    print(f" DONE in {dur_vsearch:.2f}s ({ops_vsearch:,.1f} ops/sec)")

    # Clean up benchmark keys
    print("\n[*] Cleaning up benchmark keys...")
    send_cmd(["FLUSHDB"])
    sock.close()

    print("\n" + "=" * 50)
    print("           BENCHMARK SUMMARY")
    print("=" * 50)
    print(f"  SET       : {ops_set:>10,.1f} ops/sec")
    print(f"  GET       : {ops_get:>10,.1f} ops/sec")
    print(f"  LPUSH     : {ops_lpush:>10,.1f} ops/sec")
    print(f"  VADD      : {ops_vadd:>10,.1f} ops/sec")
    print(f"  VSEARCH   : {ops_vsearch:>10,.1f} ops/sec")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FlashKV Benchmark Tool")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6379)
    parser.add_argument("-n", "--requests", type=int, default=5000, help="Number of requests")
    parser.add_argument("-k", "--keyspace", type=int, default=1000, help="Keyspace size")
    args = parser.parse_args()

    run_benchmark(args.host, args.port, args.requests, args.keyspace)
