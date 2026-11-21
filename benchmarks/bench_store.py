"""Benchmark in-memory key-value store operations."""
import time
from flashkv.store import KVStore


def benchmark_store(n: int = 10000):
    store = KVStore()
    print(f"Benchmarking {n} SET and GET operations...")

    start = time.perf_counter()
    for i in range(n):
        store.set(f"key:{i}", f"val:{i}")
    set_time = time.perf_counter() - start

    start = time.perf_counter()
    for i in range(n):
        val = store.get(f"key:{i}")
    get_time = time.perf_counter() - start

    print(f"SET ops/sec: {n / set_time:,.0f} | GET ops/sec: {n / get_time:,.0f}")


if __name__ == "__main__":
    benchmark_store()
