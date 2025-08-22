import asyncio, os
from fastapi import FastAPI

from backend.api.routers import joints as joints_router
from backend.api.routers import telemetry as telemetry_router
from backend.api.routers import runs as runs_router
from backend.api.routers import ws as ws_router

from backend.api.routers.joints import joints
from backend.api.ws_manager import manager
from backend.ingest.telemetry_queue import TelemetryIngestor
from backend.joints.sampler import run_joint_sampler

app = FastAPI()

app.include_router(joints_router.router)
app.include_router(telemetry_router.router)
app.include_router(runs_router.router)
app.include_router(ws_router.router)

@app.on_event("startup")
async def on_startup():
    app.state.ingestor = TelemetryIngestor(flush_max=200, flush_ms=200)
    await app.state.ingestor.start()

    hz = int(os.getenv("SAMPLER_HZ", "100"))
    app.state.sampler_tasks = []
    for name, joint_obj in joints.items():
        task = asyncio.create_task(run_joint_sampler(name, joint_obj, app.state.ingestor, hz=hz))
        app.state.sampler_tasks.append(task)

@app.on_event("shutdown")
async def on_shutdown():
    # 1) Instantly wake WS handlers and stop broadcasts
    try:
        await manager.shutdown()
    except Exception:
        pass

    # 2) Cancel samplers fast
    tasks = getattr(app.state, "sampler_tasks", [])
    for t in tasks:
        t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    # 3) Stop ingestor
    ing = getattr(app.state, "ingestor", None)
    if ing:
        try:
            await ing.stop()
        except Exception:
            pass