import can
import struct
import time

node_id = 0  # Node ID for the ODrive, should match your ODrive config

bus = can.interface.Bus("can0", bustype="socketcan")

# Flush CAN RX buffer so there are no more old pending messages
while not (bus.recv(timeout=0) is None): pass

# Put axis into position control state (closed loop control mode)
bus.send(can.Message(
    arbitration_id=(node_id << 5 | 0x07),  # 0x07: Set_Axis_State
    data=struct.pack('<I', 8),  # 8: AxisState.CLOSED_LOOP_POSITION_CONTROL
    is_extended_id=False
))

# Wait for axis to enter position control state by scanning heartbeat messages
for msg in bus:
    if msg.arbitration_id == (node_id << 5 | 0x01):  # 0x01: Heartbeat
        error, state, result, traj_done = struct.unpack('<IBBB', bytes(msg.data[:7]))
        if state == 8:  # 8: AxisState.CLOSED_LOOP_POSITION_CONTROL
            break

# Set position to 3 turns (positive for clockwise rotation)
target_position = 3.0  # 3 turns

# Send the position setpoint (target_position in turns)
bus.send(can.Message(
    arbitration_id=(node_id << 5 | 0x0F),  # 0x0F: Set_Position_Input
    data=struct.pack('<f', target_position),  # target_position in turns
    is_extended_id=False
))

# Wait until motor reaches the target position
start_time = time.time()
timeout = 10  # Timeout in seconds
while time.time() - start_time < timeout:
    for msg in bus:
        if msg.arbitration_id == (node_id << 5 | 0x09):  # 0x09: Get_Encoder_Estimates
            pos, vel = struct.unpack('<ff', bytes(msg.data))
            print(f"Position: {pos:.3f} [turns], Velocity: {vel:.3f} [turns/s]")
            if abs(pos - target_position) < 0.01:  # Close enough to target position
                print("Target position reached!")
                break
    else:
        continue
    break
else:
    print("Timeout reached. Target position not achieved.")