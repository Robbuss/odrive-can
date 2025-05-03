from abc import ABC, abstractmethod

class Joint(ABC):
    """
    Abstract interface for any robotic joint.
    """
    @abstractmethod
    def initialize(self):
        """Prepare the joint (e.g., arm motors, zero sensors)."""
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
        """Return current status (e.g., position, moving flag)."""
        pass