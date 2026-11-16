import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from . import api, metrics, monitor
from .config import Settings
from .db import Database
from .providers.base import ProviderError
from .providers.demo import DemoProvider
from .providers.live import LiveProvider
from .runtime import rt
from .topology import Topology


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = Settings.from_env()
    rt.settings = s
    rt.topo = Topology.load(s.topology_file)
    rt.db = Database(s.db_path)
    rt.provider = DemoProvider(rt.topo) if s.demo_mode else LiveProvider(s.ryu_url, s.lab_agent_url)
    rt.snapshot = None
    metrics.register()
    await asyncio.to_thread(monitor.refresh)  # snapshot ready before the first request
    task = asyncio.create_task(monitor.poll_forever())
    yield
    task.cancel()


app = FastAPI(title="FlowNet SDN API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=Settings.from_env().cors_origins, allow_methods=["*"], allow_headers=["*"])
app.include_router(api.router)


@app.exception_handler(ProviderError)
async def provider_error(_: Request, exc: ProviderError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
