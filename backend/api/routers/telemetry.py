from datetime import datetime, timedelta, timezone
from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, desc, text
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db import get_session
from backend.models import JointSample
from backend.api.routers.joints import joints
from backend.ingest.telemetry_queue import ingestor

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

# ---------- Schemas ----------

class SampleIn(BaseModel):
    ts: Optional[datetime] = Field(default=None)
    position: float
    velocity: Optional[float] = None
    accel: Optional[float] = None
    torque: Optional[float] = None
    supply_v: Optional[float] = None
    motor_temp: Optional[float] = None
    controller_temp: Optional[float] = None
    mode: Optional[str] = None             # store textual mode or int->str mapping
    fault_code: Optional[int] = None
    error_flags: Optional[int] = None
    target_position: Optional[float] = None
    target_velocity: Optional[float] = None
    target_accel: Optional[float] = None
    target_torque: Optional[float] = None

class SampleOut(SampleIn):
    ts: datetime
    joint_id: str
    run_id: Optional[int] = None

class TelemetryPayload(BaseModel):
    # Either a single sample or batch; optional run_id tag
    run_id: Optional[int] = None
    sample: Optional[SampleIn] = None
    samples: Optional[List[SampleIn]] = None

    @model_validator(mode="after")
    def _one_of(self) -> "TelemetryPayload":
        if bool(self.sample) == bool(self.samples):
            raise ValueError("Provide exactly one of 'sample' or 'samples'")
        return self

# ---------- Helpers ----------

def _row_from_sample(joint_name: str, s: SampleIn, run_id: Optional[int]) -> Dict[str, Any]:
    return {
        "ts": s.ts or datetime.now(timezone.utc),
        "joint_id": joint_name,
        "position": s.position,
        "velocity": s.velocity,
        "accel": s.accel,
        "torque": s.torque,
        "supply_v": s.supply_v,
        "motor_temp": s.motor_temp,
        "controller_temp": s.controller_temp,
        "mode": s.mode,
        "fault_code": s.fault_code,
        "error_flags": s.error_flags,
        "target_position": s.target_position,
        "target_velocity": s.target_velocity,
        "target_accel": s.target_accel,
        "target_torque": s.target_torque,
        "run_id": run_id,
    }

# ---------- Endpoints ----------

@router.post("/{joint_name}/samples", operation_id="postTelemetrySamples")
async def add_sample_or_batch(
    joint_name: str,
    payload: TelemetryPayload,
    session: AsyncSession = Depends(get_session),
):
    if joint_name not in joints:
        raise HTTPException(404, "Unknown joint")

    # Efficient path: push into background ingestor buffer.
    if payload.sample:
        row = _row_from_sample(joint_name, payload.sample, payload.run_id)
        await ingestor.enqueue(row)
        return {"ok": True, "count": 1}

    assert payload.samples is not None
    rows = [_row_from_sample(joint_name, s, payload.run_id) for s in payload.samples]
    # For large batches, enqueue = O(n) puts. We can shortcut by inserting directly:
    if len(rows) >= 1000:
        # Direct bulk insert for very large payloads.
        from sqlalchemy import insert
        await session.execute(insert(JointSample), rows)
        await session.commit()
    else:
        for r in rows:
            await ingestor.enqueue(r)
    return {"ok": True, "count": len(rows)}

@router.get("/{joint_name}/samples", response_model=List[SampleOut], operation_id="getTelemetrySamples")
async def get_samples(
    joint_name: str,
    limit: int = Query(1000, ge=1, le=100000),
    since_seconds: Optional[int] = Query(None, ge=1),
    run_id: Optional[int] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    if joint_name not in joints:
        raise HTTPException(404, "Unknown joint")
    q = select(JointSample).where(JointSample.joint_id == joint_name)
    if run_id is not None:
        q = q.where(JointSample.run_id == run_id)
    if since_seconds:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=since_seconds)
        q = q.where(JointSample.ts >= cutoff)
    q = q.order_by(desc(JointSample.ts)).limit(limit)
    res = (await session.execute(q)).scalars().all()
    return [
        SampleOut(
            joint_id=r.joint_id, ts=r.ts, run_id=r.run_id,
            position=r.position, velocity=r.velocity, accel=r.accel,
            torque=r.torque, supply_v=r.supply_v,
            motor_temp=r.motor_temp, controller_temp=r.controller_temp,
            mode=r.mode, fault_code=r.fault_code, error_flags=r.error_flags,
            target_position=r.target_position, target_velocity=r.target_velocity,
            target_accel=r.target_accel, target_torque=r.target_torque,
        )
        for r in res
    ]

class RollupPoint(BaseModel):
    ts: datetime = Field(alias="bucket")
    joint_id: str
    run_id: Optional[int] = None
    avg_position: Optional[float] = None
    min_position: Optional[float] = None
    max_position: Optional[float] = None
    avg_velocity: Optional[float] = None
    avg_torque: Optional[float] = None
    avg_supply_v: Optional[float] = None

@router.get("/{joint_name}/rollup", response_model=List[RollupPoint], operation_id="getTelemetryRollup")
async def rollup_1s(
    joint_name: str,
    minutes: int = Query(10, ge=1, le=720),
    run_id: Optional[int] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    if joint_name not in joints:
        raise HTTPException(404, "Unknown joint")

    params: Dict[str, Any] = {
        "joint_id": joint_name,
        "since": minutes,
    }
    where_run = ""
    if run_id is not None:
        where_run = "AND run_id = :run_id"
        params["run_id"] = run_id

    sql = text(f"""
        SELECT bucket, joint_id, run_id,
               avg_position, min_position, max_position,
               avg_velocity, avg_torque, avg_supply_v
        FROM joint_samples_1s
        WHERE joint_id = :joint_id
          AND bucket >= now() - (:since || ' minutes')::interval
          {where_run}
        ORDER BY bucket ASC
    """)
    rows = (await session.execute(sql, params)).mappings().all()
    return [RollupPoint(**row) for row in rows]
