try:
    import orjson
    def fast_dumps(obj) -> str:
        return orjson.dumps(obj).decode("utf-8")
except Exception:
    import json
    def fast_dumps(obj) -> str:
        return json.dumps(obj, separators=(",", ":"))