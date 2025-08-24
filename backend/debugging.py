import os

def enable_debugpy():
    if os.getenv("DEBUGPY", "0") != "1":
        return
    import debugpy
    host = os.getenv("DEBUGPY_HOST", "0.0.0.0")  # bind inside container
    port = int(os.getenv("DEBUGPY_PORT", "5678"))
    debugpy.listen((host, port))
    print(f"🔎 debugpy listening on {host}:{port}")
    if os.getenv("DEBUGPY_WAIT_FOR_CLIENT", "0") == "1":
        print("⏸️  Waiting for debugger attach...")
        debugpy.wait_for_client()
    # Optional: break right after startup if you want to land at the first line
    if os.getenv("DEBUGPY_BREAK_STARTUP", "0") == "1":
        debugpy.breakpoint()