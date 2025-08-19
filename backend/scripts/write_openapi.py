import json, sys, tempfile
from pathlib import Path

try:
    # import your app
    from backend.main import app
except Exception as e:
    print(f"[openapi] Failed to import backend.main: {e}", file=sys.stderr)
    sys.exit(1)

try:
    schema = app.openapi()
except Exception as e:
    print(f"[openapi] Failed to build schema: {e}", file=sys.stderr)
    sys.exit(1)

OUT = Path(__file__).resolve().parents[2] / "openapi.json"  # repo root/openapi.json
# atomic write: write temp, then rename
try:
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(OUT.parent), suffix=".tmp") as tf:
        json.dump(schema, tf, indent=2)
        temp_name = tf.name
    Path(temp_name).replace(OUT)
    print(f"[openapi] Wrote {OUT}")
except Exception as e:
    print(f"[openapi] Failed to write schema: {e}", file=sys.stderr)
    sys.exit(1)