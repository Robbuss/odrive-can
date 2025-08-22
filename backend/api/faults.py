FAULT_CODE_MAP: dict[int, str] = {
    32: "Calibration fault – encoder could not sense a magnet during calibration.",
    33: "Motor driver fault – often undervoltage or DRV8323 electrical fault (see driver_fault regs).",
    34: "Over voltage – bus exceeded servo.max_voltage (regen or misconfig).",
    35: "Encoder fault – readings inconsistent with a magnet present.",
    36: "Motor not configured – run moteus_tool --calibrate.",
    37: "PWM cycle overrun – internal timing error.",
    38: "Over temperature – above configured max temperature.",
    39: "Outside limit – tried to start position control outside servopos.position_min/max.",
    40: "Under voltage – supply too low.",
    41: "Config changed – config modified during operation; requires stop.",
    42: "Theta invalid – no valid commutation encoder available.",
    43: "Position invalid – no valid output encoder available.",
    44: "Driver enable fault – gate driver could not be enabled.",
    45: "Stop position deprecated – used with vel/accel limits; command position w/ vel=0 instead.",
    46: "Timing violation – internal timing constraint violated.",
    47: "BEMF feedforward configured but no accel limit specified.",
}

def explain_fault(code: int | None) -> str | None:
    if not code:
        return None
    return FAULT_CODE_MAP.get(int(code), f"Unknown fault code {code}.")