"""Temporary debug NDJSON logger for session ec2dc9."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

# #region agent log
# Prefer the HA config mount. Never mkdir invent a host Mac path inside Docker.
_LOG_PATHS = (
    Path("/config/.cursor/debug-ec2dc9.log"),
    Path("/home/ntableman/docker/ha/config/.cursor/debug-ec2dc9.log"),
    Path("/Users/ntableman/Documents/GitHub/ac-infinity-hacs/.cursor/debug-ec2dc9.log"),
)
_SESSION_ID = "ec2dc9"
# #endregion


def agent_log(
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict[str, Any] | None = None,
    *,
    run_id: str = "pre-fix",
) -> None:
    """Append one NDJSON debug line to the first existing-or-creatable log path."""
    # #region agent log
    payload = {
        "sessionId": _SESSION_ID,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
    }
    line = json.dumps(payload, default=str) + "\n"
    for path in _LOG_PATHS:
        try:
            # Only create .cursor under known HA/config roots, not phantom trees.
            if path.parent.name == ".cursor":
                path.parent.mkdir(parents=True, exist_ok=True)
            elif not path.parent.exists():
                continue
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)
            return
        except OSError:
            continue
    # #endregion
