import json
import os
from datetime import datetime, timezone
from typing import Any, Dict


LOG_DIR = os.getenv("LOG_DIR", "reports")
os.makedirs(LOG_DIR, exist_ok=True)


def log_event(event: Dict[str, Any], filename: str = "rag_events.jsonl") -> None:
    """
    Append structured JSON event to a .jsonl file.
    Safe for MVP analytics and export.
    """

    path = os.path.join(LOG_DIR, filename)

    # Add UTC timestamp (ISO 8601)
    event["_ts"] = datetime.now(
        timezone.utc).isoformat().replace("+00:00", "Z")

    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        # Never break app because of logging
        pass
