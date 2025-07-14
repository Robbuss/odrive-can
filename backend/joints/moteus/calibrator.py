import sys
import asyncio
import logging
from backend.joints.moteus.transport import MoteusBus

logger = logging.getLogger(__name__)

class MoteusCalibrator:
    """
    Encapsulates rotor-alignment calibration by invoking the CLI tool.

    Calibration of a bare moteus board must use the diagnostic protocol
    provided by the `moteus_tool` CLI; it is not supported in the Python
    register protocol. This class shells out to that tool.
    """
    def __init__(self, bus: MoteusBus, node_id: int = 0):
        self.bus = bus
        self.node_id = node_id

    def initialize(self) -> None:
        """Ensure the underlying MoteusBus/controller is initialized."""
        try:
            self.bus.open()
        except Exception as e:
            logger.error("Failed to initialize bus for calibration: %s", e)
            raise RuntimeError("Calibration bus initialization failed") from e

    async def run(self) -> dict:
        """
        Perform the calibration sequence by invoking:
          `python3 -m moteus.moteus_tool --target <node_id> --transport <transport_spec> --calibrate`

        Returns:
          { 'status': 'calibrated', 'output': <CLI stdout> }
        Raises on non-zero return code or timeout.
        """
        self.initialize()

        # Derive transport spec from bus configuration
        transport_spec = getattr(self.bus, 'transport_spec', None)
        if not transport_spec:
            transport_spec = f"socketcan:{self.bus.iface},fd={'yes' if self.bus.fd else 'no'}"

        # Build CLI arguments
        cli_args = [
            sys.executable, "-m", "moteus.moteus_tool",
            "--target", str(self.node_id),
            "--transport", transport_spec,
            "--calibrate"
        ]

        # Launch the CLI with a timeout
        try:
            proc = await asyncio.create_subprocess_exec(
                *cli_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as e:
            logger.error("Failed to start calibration subprocess: %s", e)
            raise RuntimeError("Calibration subprocess failed to start") from e

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=60
            )
        except asyncio.TimeoutError:
            proc.kill()
            logger.error("Calibration timed out after 60 seconds")
            raise RuntimeError("Calibration timed out after 60 seconds")

        if proc.returncode != 0:
            err_text = stderr.decode(errors='ignore').strip()
            logger.error("Calibration CLI failed (code %d): %s", proc.returncode, err_text)
            raise RuntimeError(f"Calibration failed (code {proc.returncode}): {err_text}")

        output = stdout.decode(errors='ignore').strip()
        if stderr:
            warn_text = stderr.decode(errors='ignore').strip()
            logger.debug("Calibration warnings: %s", warn_text)

        logger.info("Calibration successful: %s", output)
        return {'status': 'calibrated', 'output': output}
    """
    Encapsulates rotor-alignment calibration by invoking the CLI tool.

    Calibration of a bare moteus board must use the diagnostic protocol
    provided by the `moteus_tool` CLI; it is not supported in the Python
    register protocol. This class shells out to that tool.
    """
    def __init__(self, bus: MoteusBus, node_id: int = 0):
        self.bus = bus
        self.node_id = node_id

    def initialize(self) -> None:
        """Ensure the underlying MoteusBus/controller is initialized."""
        try:
            self.bus.open()
        except Exception as e:
            logger.error("Failed to initialize bus for calibration: %s", e)
            raise RuntimeError("Calibration bus initialization failed") from e

    async def run(self) -> dict:
        """
        Perform the calibration sequence by invoking:
          `python3 -m moteus.moteus_tool --target <node_id> --calibrate`

        Returns:
          { 'status': 'calibrated', 'output': <CLI stdout> }
        Raises on non-zero return code or timeout.
        """
        self.initialize()

        # Launch the CLI with a timeout
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "moteus.moteus_tool",
                "--target", str(self.node_id),
                "--calibrate",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as e:
            logger.error("Failed to start calibration subprocess: %s", e)
            raise RuntimeError("Calibration subprocess failed to start") from e

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=60
            )
        except asyncio.TimeoutError:
            proc.kill()
            logger.error("Calibration timed out after 60 seconds")
            raise RuntimeError("Calibration timed out after 60 seconds")

        if proc.returncode != 0:
            err_text = stderr.decode(errors='ignore').strip()
            logger.error("Calibration CLI failed (code %d): %s", proc.returncode, err_text)
            raise RuntimeError(f"Calibration failed (code {proc.returncode}): {err_text}")

        output = stdout.decode(errors='ignore').strip()
        if stderr:
            warn_text = stderr.decode(errors='ignore').strip()
            logger.debug("Calibration warnings: %s", warn_text)

        logger.info("Calibration successful: %s", output)
        return {'status': 'calibrated', 'output': output}
