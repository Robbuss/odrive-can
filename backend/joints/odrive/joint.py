import asyncio  
from typing import Optional  
import time  
import concurrent.futures
import odrive  
from odrive.enums import *  
  
from backend.joints.base import Joint  
  
class ODriveJoint:    
    def __init__(self, serial_number: str = None, axis_num: int = 0):    
        self.serial_number = serial_number  
        self.axis_num = axis_num  
          
        # Run ODrive discovery in a separate thread to avoid event loop conflict  
        with concurrent.futures.ThreadPoolExecutor() as executor:  
            future = executor.submit(self._find_odrive_sync)  
            self.odrive = future.result(timeout=30)  # 30 second timeout  
          
        self.axis = getattr(self.odrive, f'axis{self.axis_num}')  
        self.arm()  
      
    def _find_odrive_sync(self):  
        import odrive  
        return odrive.find_any(serial_number=self.serial_number)
        
    def move(self, position: float, velocity: float = None, accel: float = None):    
        # Check if motor is armed, arm if needed    
        if self.axis.current_state != AXIS_STATE_CLOSED_LOOP_CONTROL:    
            self.arm()    
            
        # Configure trajectory if velocity/accel specified    
        if velocity is not None or accel is not None:    
            self._setup_trajectory_mode(velocity, accel)    
            self.axis.controller.config.input_mode = INPUT_MODE_TRAP_TRAJ    
        else:    
            self.axis.controller.config.input_mode = INPUT_MODE_PASSTHROUGH    
            
        # Execute move    
        self.axis.controller.input_pos = position    
  
    def _setup_trajectory_mode(self, velocity: float = None, accel: float = None):  
        """Configure trajectory parameters for smooth motion."""  
        if velocity is not None:  
            self.axis.trap_traj.config.vel_limit = velocity  
        if accel is not None:  
            self.axis.trap_traj.config.accel_limit = accel  
            self.axis.trap_traj.config.decel_limit = accel  
  
    def _is_calibrated(self) -> bool:  
        """Check if the axis is calibrated."""  
        # This is a simplified check - you may want to add more comprehensive validation  
        return (self.axis.motor.is_calibrated and   
                self.axis.encoder.is_ready)  
        
    def arm(self):    
        # Run calibration if needed    
        if not self._is_calibrated():    
            self.axis.requested_state = AXIS_STATE_FULL_CALIBRATION_SEQUENCE    
            while self.axis.current_state != AXIS_STATE_IDLE:    
                time.sleep(0.1)    
            
        # Enter closed loop control    
        self.axis.requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL  
  
    def disarm(self):  
        """Disarm the axis."""  
        self.axis.requested_state = AXIS_STATE_IDLE  
  
    def calibrate(self) -> None:  
        """Calibrate the axis."""  
        self.axis.requested_state = AXIS_STATE_FULL_CALIBRATION_SEQUENCE  
        while self.axis.current_state != AXIS_STATE_IDLE:  
            time.sleep(0.1)  
  
    async def status(self) -> dict:  
        """Get the status of the axis."""  
        return {  
            "position": self.axis.encoder.pos_estimate,  
            "velocity": self.axis.encoder.vel_estimate,  
            "current": self.axis.motor.current_control.Iq_measured,  
            "temperature": self.axis.motor.temperature,  
            "state": self.axis.current_state,  
            "errors": self.axis.error  
        }