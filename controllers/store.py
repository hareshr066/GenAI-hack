# backend/controllers/store.py
from __future__ import annotations
from pathlib import Path
import json
import time
from typing import Any, Dict, List, Optional
from threading import RLock

class _Store:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.db_path = self.data_dir / "store.json"
        self.lock = RLock()
        self._data = {"files": {}}
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.db_path.exists():
            try:
                self._data = json.loads(self.db_path.read_text(encoding="utf-8"))
            except Exception:
                self._data = {"files": {}}
        else:
            self._flush()

    def _flush(self):
        with self.lock:
            self.db_path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def upsert_file(self, file_id: str, payload: Dict[str, Any]):
        with self.lock:
            payload["updated_at"] = time.time()
            self._data["files"][file_id] = payload
            self._flush()

    def get_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self._data["files"].get(file_id)

    def list_files(self) -> List[Dict[str, Any]]:
        with self.lock:
            files = list(self._data["files"].values())
            files.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
            return files

    def latest_file_id(self) -> Optional[str]:
        files = self.list_files()
        return files[0]["file_id"] if files else None

def _init_store() -> _Store:
    base = Path(__file__).resolve().parents[1]
    data_dir = base / "data"
    return _Store(data_dir=data_dir)

store = _init_store()
