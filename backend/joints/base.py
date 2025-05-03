from abc import ABC, abstractmethod

class Joint(ABC):
    """
    Abstract interface for any robotic joint.
    """
    @abstractmethod
    def initialize(self):
        """Prepare/arm the joint (e.g., open bus, engage motors)."""
        pass

    @abstractmethod
    def move(self, delta: float, freq: float = 100.0):
        """Command the joint to move by `delta` units at `freq`Hz."""
        pass

    @abstractmethod
    def stop(self):
        """Stop any ongoing motion."""
        pass

    @abstractmethod
    def status(self) -> dict:
        """Return current status (e.g., position, running)."""
        pass

    @abstractmethod
    def disarm(self):
        """Disarm or shutdown the joint (e.g., send IDLE, close bus)."""
        pass

    @abstractmethod
    async def calibrate(self, state: int = 3, save_config: bool = False) -> dict:
        """
        Run calibration sequence (async). Uses CANSimple protocol.
        Returns result dict.
        """
        pass