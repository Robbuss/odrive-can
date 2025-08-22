from typing import Optional, Any, Dict
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db import get_session
from backend.models import Run

router = APIRouter(prefix="/runs", tags=["runs"])

class RunStartOut(BaseModel):
    run_id: int
    started_at: datetime

class RunStartIn(BaseModel):
    label: Optional[str] = None
    notes: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    config_snapshot: Optional[Dict[str, Any]] = None

class StartRunBody(BaseModel):
    label: str | None = None
    meta: dict | None = None

@router.post("/start", operation_id="startRun")
async def start_run(
    body: StartRunBody | None = None,
    session: AsyncSession = Depends(get_session),
):
    now = datetime.now(timezone.utc)
    run = Run(
        started_at=now,
        meta=(body.meta if body and body.meta is not None else {}),   # maps to DB "metadata"
        # if your model has a label/title, set it; otherwise drop this arg
        # label=(body.label if body else None),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return {"run_id": run.id, "started_at": run.started_at}

class RunStopOut(BaseModel):
    run_id: int
    ended_at: datetime

@router.post("/{run_id}/stop", response_model=RunStopOut, operation_id="stopRun")
async def stop_run(run_id: int, session: AsyncSession = Depends(get_session)):
    q = select(Run).where(Run.id == run_id)
    run = (await session.execute(q)).scalars().first()
    if not run:
        raise HTTPException(404, "Run not found")
    if run.ended_at is None:
        run.ended_at = datetime.now(timezone.utc)
        await session.commit()
    return RunStopOut(run_id=run.id, ended_at=run.ended_at)