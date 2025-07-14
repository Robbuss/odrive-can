import asyncio
import sys
import math
import moteus

async def move_to_position():
    if len(sys.argv) != 5:
        print(f"Usage: {sys.argv[0]} <position> <velocity> <accel_limit> <hold_position>")
        return

    position = float(sys.argv[1])
    velocity = float(sys.argv[2])
    accel_limit = float(sys.argv[3])
    hold_position = sys.argv[4] == "1"

    # Only ask for the fields we need (mode & velocity)
    qr = moteus.QueryResolution()
    qr.mode     = moteus.INT8
    qr.position = moteus.F32

    controller = moteus.Controller(
        id=1,
        query_resolution=qr,
    )

    # 1) Clear any prior motion or fault state
    await controller.set_stop()
    await asyncio.sleep(0.05)

    print(f"Spinning at {velocity:.3f} turns/s. Ctrl+C to stop.")
    print(f"Position: {position:.3f} turns")
    print(f"Velocity: {velocity:.3f} turns/s")
    print(f"Accel limit: {accel_limit:.3f} turns/s^2")

    await controller.set_recapture_position_velocity()

    result = await controller.set_position(  
        position=position,  
        velocity=math.nan,  
        velocity_limit=velocity,  
        accel_limit=accel_limit,  
        query=True,  
    )  

    try:
        actual = result.values.get(moteus.Register.POSITION, float('nan')) if result else 0.0  
        while hold_position or abs(actual - position) > 0.004:  
            state = await controller.query()  
            if state and state.values:  
                actual = state.values.get(moteus.Register.POSITION, float('nan'))  
                print(f"  → actual pos = {actual:7.3f} turns")  # Fixed: was showing "vel" but displaying position  
            await asyncio.sleep(0.1)  # Reduced from 0.5s for more responsive monitoring

    except KeyboardInterrupt:
        print("\nStopping motor…")

    finally:
        # 4) Cleanly stop and clear torque
        await controller.set_stop()

if __name__ == "__main__":
    asyncio.run(move_to_position())