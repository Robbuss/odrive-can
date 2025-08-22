import math
import logging
import moteus
from backend.joints.base import Joint
from backend.joints.moteus.calibrator import MoteusCalibrator
import asyncio
from typing import Optional
import time
import os

logger = logging.getLogger(__name__)

class MoteusJoint(Joint):
    """
    Async Joint implementation for a Moteus R4.11 controller over CAN.
    """
    def __init__(self, node_id: int = 0):
        super().__init__()
        qr = moteus.QueryResolution()
        # Fast path registers (all read in a single .query())
        qr.mode                 = moteus.INT8
        qr.position             = moteus.F32
        qr.velocity             = moteus.F32
        qr.voltage              = moteus.F32
        qr.trajectory_complete  = moteus.INT8
        qr.fault                = moteus.INT8

        # >>> NEW: extra fields to fill DB/WS cleanly
        qr.torque               = moteus.F32               # Nm
        qr.motor_temperature    = moteus.F32               # °C
        qr.temperature          = moteus.F32               # controller °C
        # (driver faults already available via registers if you want)
        # qr.driver_fault1      = moteus.INT16
        # qr.driver_fault2      = moteus.INT16

        self.node_id = node_id
        self._ctrl = moteus.Controller(id=node_id, query_resolution=qr)
        self._running = False
        self._last_status_warn = 0.0  # rate-limit log

        # serialize hardware access + track active command
        self._lock = asyncio.Lock()
        self._current_cmd: Optional[dict] = None  # {"cmd_id", "target", "run_id"}

    def initialize(self) -> None:
        """Open the underlying bus/controller if not already open."""

    def get_current_cmd(self) -> Optional[dict]:
        return self._current_cmd

    def clear_current_cmd(self) -> None:
        self._current_cmd = None

    async def move(
        self,
        position: float,
        velocity: float = None,
        accel: float = None,
        hold: bool = True,
        cmd_id: str | None = None,
        run_id: int | None = None,
    ) -> dict:
        """
        Non-blocking move to absolute `position` (turns). The sampler will stream telemetry.
        """
        print(f"Moving joint {self.node_id} to position {position}, velocity {velocity}, accel {accel}, hold {hold}")
        async with self._lock:
            # 1) Stop any prior motion briefly
            await self._ctrl.set_stop()
            await asyncio.sleep(0.02)

            # 2) Resynchronize capture
            await self._ctrl.set_recapture_position_velocity()

            # 3) Read current position (radians -> turns)
            status = await self._ctrl.query()
            start_turns = status.values[moteus.Register.POSITION] / (2 * math.pi)

            vlim = velocity if velocity is not None else 1.0
            alim = accel if accel is not None else 1.0
            max_torque = float(os.getenv("MOTEUS_MAX_TORQUE", "3.5"))  # tune if needed

            # 4) Fire-and-forget position command (NO wait_complete)
            await self._ctrl.set_position(
                position=position,
                velocity=0.0,                 # stop at target
                velocity_limit=vlim,
                accel_limit=alim,
                maximum_torque=max_torque,
                feedforward_torque=math.nan,
                watchdog_timeout=0.5,
                query=False,
            )
            self._running = True

            # >>> include velocity/accel/run_id so sampler can mirror target_* into rows
            self._current_cmd = {
                "cmd_id": cmd_id,
                "target": position,
                "velocity": velocity,
                "accel": accel,
                "run_id": run_id,
                "hold": hold,
            }

        return {
            "target_turns": position,
            "start_turns":  start_turns,
            "requested_vel": velocity,
            "requested_acc": accel,
            "cmd_id": cmd_id,
        }

    async def stop(self) -> None:
        """Stop movement (brake)."""
        try:
            async with self._lock:
                await self._ctrl.set_stop()
        finally:
            self._running = False
            self._current_cmd = None

    async def get_control_values(
        self,
        *,
        use_cache: bool = False,   # default OFF for correctness
        ttl_sec: float = 10.0,
    ):
        """
        Returns (position_min, position_max, kp, ki, kd) as floats or None.
        Robust against 'key = value', 'key value', or 'value' formats.
        Flushes the diagnostic stream before each command to avoid stale bytes.
        """

        now = time.monotonic()
        if use_cache and hasattr(self, "_control_cache_time"):
            if (now - getattr(self, "_control_cache_time", 0.0)) < ttl_sec:
                return getattr(self, "_control_cache")

        async with self._lock:
            if not hasattr(self, "_diag_stream") or self._diag_stream is None:
                self._diag_stream = moteus.Stream(self._ctrl)

            # optional debug: set MOTEUS_DIAG_DEBUG=1 to log raw replies
            debug = os.getenv("MOTEUS_DIAG_DEBUG") == "1"

            async def _flush():
                # flush any residual unread data
                try:
                    await self._diag_stream.flush_read()
                except Exception:
                    pass

            def _parse_first_float(b: bytes) -> float | None:
                # Take the LAST non-empty line (diagnostic often echoes prompts/blank lines)
                lines = [ln.strip() for ln in b.splitlines() if ln.strip()]
                if not lines:
                    return None
                s = lines[-1].decode("latin1", "ignore")
                # If there is an '=', keep the RHS; else keep whole line
                if "=" in s:
                    s = s.split("=", 1)[1].strip()
                # Extract the first numeric token (handles nan, inf, scientific)
                import re
                m = re.search(r'(?i)(nan|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|inf|-inf)', s)
                if not m:
                    return None
                token = m.group(1)
                try:
                    # float('nan') / 'inf' fine in Python
                    return float(token)
                except Exception:
                    return None

            async def _get_float(key: str) -> float | None:
                await _flush()
                cmd = ("conf get " + key).encode("ascii")
                b = await self._diag_stream.command(cmd, allow_any_response=True)
                if debug:
                    logger.debug("diag %s -> %r", key, b)
                # Some errors come as 'ERR ...' lines — return None in that case
                if b.startswith(b"ERR"):
                    return None
                return _parse_first_float(b)

            # Read each key individually and robustly (not in 100 Hz path anyway)
            pmin = await _get_float("servopos.position_min")
            pmax = await _get_float("servopos.position_max")
            kp   = await _get_float("servo.pid_position.kp")
            ki   = await _get_float("servo.pid_position.ki")
            kd   = await _get_float("servo.pid_position.kd")

            result = (pmin, pmax, kp, ki, kd)

            if use_cache:
                self._control_cache = result
                self._control_cache_time = now

            return result

    async def set_control_values(  
        self,  
        kp: float,  
        ki: float,  
        kd: float,  
        min_pos: float,  
        max_pos: float,  
        *,  
        persist: bool = False,  
    ):  
        """  
        Set servopos limits (turns) and PID gains on the controller efficiently.  
        """  
        # Reuse/create a diagnostic stream  
        if not hasattr(self, "_diag_stream") or self._diag_stream is None:  
            self._diag_stream = moteus.Stream(self._ctrl)  
    
        stream = self._diag_stream  
    
        def _fmt(x: float) -> str:  
            return f"{float(x):.9g}"  
    
        # Prepare all config commands as a batch  
        commands = [  
            f"conf set servopos.position_min {_fmt(min_pos)}",  
            f"conf set servopos.position_max {_fmt(max_pos)}",  
            f"conf set servo.pid_position.kp {_fmt(kp)}",  
            f"conf set servo.pid_position.ki {_fmt(ki)}",  
            f"conf set servo.pid_position.kd {_fmt(kd)}",
            f"conf write"  
        ]  
    
        # Send commands efficiently without individual flushing  
        errors = []  
        for cmd in commands:  
            try:  
                await stream.command(cmd.encode('ascii'))  
            except moteus.CommandError as e:  
                errors.append(f"{cmd}: {e}")  
    
        # Persist if requested  
        if persist:  
            try:  
                await stream.command(b"conf write")  
            except moteus.CommandError as e:  
                errors.append(f"conf write: {e}")  
    
        if errors:  
            raise RuntimeError(f"Configuration errors: {'; '.join(errors)}")  
    
        return {  
            "kp": float(kp),  
            "ki": float(ki),  
            "kd": float(kd),  
            "min_pos": float(min_pos),  
            "max_pos": float(max_pos),  
            "persisted": bool(persist),  
        }

    async def status(self, include_control: bool = False) -> dict:
        """Fast status for the hot path (WS/DB). No diagnostic reads by default."""
        try:
            async with self._lock:
                st = await self._ctrl.query()
                vals = getattr(st, "values", {})
        except Exception as e:
            now = time.monotonic()
            if now - self._last_status_warn > 5.0:
                logger.warning("Status query failed (likely offline): %s", e, exc_info=False)
                self._last_status_warn = now
            raise

        # Turns / rev/s
        pos_raw = vals.get(moteus.Register.POSITION)
        vel_raw = vals.get(moteus.Register.VELOCITY)
        position = (pos_raw / (2 * math.pi)) if pos_raw is not None else None
        velocity = (vel_raw / (2 * math.pi)) if vel_raw is not None else None

        # Core health
        voltage         = vals.get(moteus.Register.VOLTAGE)
        fault           = vals.get(moteus.Register.FAULT) or 0
        traj_done       = vals.get(moteus.Register.TRAJECTORY_COMPLETE) or 0
        mode_val        = vals.get(moteus.Register.MODE)
        torque          = vals.get(moteus.Register.TORQUE)              # Nm
        motor_temp      = vals.get(moteus.Register.MOTOR_TEMPERATURE)   # °C
        controller_temp = vals.get(moteus.Register.TEMPERATURE)         # °C

        # Optional driver faults (bitfields)
        drv1 = vals.get(moteus.Register.DRIVER_FAULT1) or 0
        drv2 = vals.get(moteus.Register.DRIVER_FAULT2) or 0

        # Map mode to text for DB TEXT column
        mode_text = None
        if mode_val is not None:
            try:
                mode_text = moteus.Mode(mode_val).name.lower()
            except Exception:
                mode_text = str(mode_val)

        out = {
            "position": position,                 # turns
            "velocity": velocity,                 # rev/s
            "supply_v": voltage,                  # V
            "running": self._running,
            "fault": int(fault),
            "trajectory_complete": int(traj_done),
            "mode": mode_text,                    # TEXT for DB
            "torque": torque,                     # Nm
            "motor_temp": motor_temp,             # °C
            "controller_temp": controller_temp,   # °C
            "driver_fault1": int(drv1),
            "driver_fault2": int(drv2),
        }

        if not include_control:
            return out

        # Slow path: limits, PID via diag stream (on-demand only)
        try:
            if not hasattr(self, "_diag_stream") or self._diag_stream is None:
                self._diag_stream = moteus.Stream(self._ctrl)

            pmin, pmax, kp, ki, kd = await self.get_control_values(use_cache=True)
            out["min_pos"] = pmin
            out["max_pos"] = pmax
            out["kp"] = kp
            out["ki"] = ki
            out["kd"] = kd
        except Exception:
            pass

        return out
    async def disarm(self) -> None:
        """Disarm the motor and shutdown bus."""
        await self.stop()
        self._ctrl.shutdown()
        self._running = False

    async def calibrate(self, *args, **kwargs) -> dict:
        self.initialize()
        calibrator = MoteusCalibrator(self._ctrl, node_id=self.node_id)
        result = await calibrator.run()
        self._running = False
        return result

    async def configure(self, kp: float, ki: float, kd: float, min_pos: float, max_pos: float) -> None:
        """ Set the control values for this joint, values that can be set are:
        - kp
        - ki
        - kd
        - min_pos
        - max_pos
        """
        print(f"Configuring joint {self.node_id} with kp {kp}, ki {ki}, kd {kd}, min_pos {min_pos}, max_pos {max_pos}")
        return await self.set_control_values(kp, ki, kd, min_pos, max_pos)
