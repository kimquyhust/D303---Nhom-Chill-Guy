"""JSONL trace logger.

Records a real run of the multi-agent pipeline: every dispatch, tool call,
LLM call, handoff and verification decision is appended as one JSON line.
Per the lab, only the latest run is kept (the file is truncated on open()).
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any


class Tracer:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._fh = open(path, "w", encoding="utf-8")   # truncate: latest run only
        self._lock = threading.Lock()
        self._seq = 0

    def log(self, case_id: str, agent: str, event: str, **payload: Any) -> None:
        self._seq += 1
        rec = {
            "seq": self._seq,
            "ts": round(time.time(), 6),
            "case_id": case_id,
            "agent": agent,
            "event": event,
        }
        rec.update(payload)
        line = json.dumps(rec, ensure_ascii=False)
        with self._lock:
            self._fh.write(line + "\n")
            self._fh.flush()

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass
