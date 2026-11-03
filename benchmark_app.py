"""Optional standalone entry point; main.py also mounts the same isolated router."""
from fastapi import FastAPI
from services.benchmark import BenchmarkBodyLimit, router

app = FastAPI(title="Drone Audio Benchmark API", version="1")
app.include_router(router)
app.add_middleware(BenchmarkBodyLimit)
