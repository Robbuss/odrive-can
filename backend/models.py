from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, DateTime, Integer, BigInteger, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Index
from sqlalchemy.dialects.postgresql import JSONB
from .db import Base

class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    label: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # ⚠️ rename attribute to avoid reserved name; keep column name "metadata"
    meta: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)

    config_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB)

    events: Mapped[list["RunEvent"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    samples: Mapped[list["JointSample"]] = relationship(back_populates="run")

class RunEvent(Base):
    __tablename__ = "run_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    joint_id: Mapped[Optional[str]] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB)

    run: Mapped["Run"] = relationship(back_populates="events")

class JointSample(Base):
    __tablename__ = "joint_samples"

    # part of composite PK; still auto-incremented by DB
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, nullable=False)
    joint_id: Mapped[str] = mapped_column(String(32), primary_key=True, nullable=False)

    # Kinematics
    position: Mapped[float] = mapped_column(Float, nullable=False)
    velocity: Mapped[Optional[float]] = mapped_column(Float)
    accel:    Mapped[Optional[float]] = mapped_column(Float)

    # Actuation
    torque:   Mapped[Optional[float]] = mapped_column(Float)
    supply_v: Mapped[Optional[float]] = mapped_column(Float)
    motor_temp: Mapped[Optional[float]] = mapped_column(Float)
    controller_temp: Mapped[Optional[float]] = mapped_column(Float)

    # Controller state
    mode: Mapped[Optional[str]] = mapped_column(Text)
    fault_code: Mapped[Optional[int]] = mapped_column(Integer)
    error_flags: Mapped[Optional[int]] = mapped_column(BigInteger)

    # Targets
    target_position: Mapped[Optional[float]] = mapped_column(Float)
    target_velocity: Mapped[Optional[float]] = mapped_column(Float)
    target_accel:    Mapped[Optional[float]] = mapped_column(Float)
    target_torque:   Mapped[Optional[float]] = mapped_column(Float)

    # Run link
    run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"), index=True)
    run: Mapped[Optional["Run"]] = relationship(back_populates="samples")

# Helpful composite index (also created in migration)
Index("ix_joint_samples_joint_ts_desc", JointSample.joint_id, JointSample.ts.desc())
