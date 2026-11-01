import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StateFile:
    path: Path

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        text = self.path.read_text()
        return json.loads(text)

    def save(self, state: dict) -> None:
        body = json.dumps(state, indent=2, sort_keys=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        staging = self.path.with_suffix(".tmp")
        staging.write_text(body)
        staging.replace(self.path)
