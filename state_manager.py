"""
Persist migration progress to a JSON file so the run can be resumed.
"""

import json
import logging
import pathlib

log = logging.getLogger(__name__)

_DEFAULTS = {
    "last_completed_offset": 0,
    "processed_count": 0,
    "skipped_count": 0,
    "error_count": 0,
    "completed": False,
}


class StateManager:
    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.state = self._load()

    def _load(self):
        if self.path.exists():
            with open(self.path) as f:
                saved = json.load(f)
            return {**_DEFAULTS, **saved}
        return dict(_DEFAULTS)

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.state, f, indent=2)

    @property
    def resume_offset(self):
        return self.state["last_completed_offset"]

    @property
    def is_complete(self):
        return self.state["completed"]

    def record_batch(self, new_offset, processed, skipped, errors):
        self.state["last_completed_offset"] = new_offset
        self.state["processed_count"] += processed
        self.state["skipped_count"] += skipped
        self.state["error_count"] += errors
        self.save()
        log.info(
            "Batch done. offset=%d processed=%d skipped=%d errors=%d | "
            "totals: processed=%d skipped=%d errors=%d",
            new_offset, processed, skipped, errors,
            self.state["processed_count"],
            self.state["skipped_count"],
            self.state["error_count"],
        )

    def mark_complete(self):
        self.state["completed"] = True
        self.save()
        log.info(
            "Migration complete. processed=%d skipped=%d errors=%d",
            self.state["processed_count"],
            self.state["skipped_count"],
            self.state["error_count"],
        )
