import json
import os
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class Webhook:
    url: str

    @classmethod
    def from_env(cls) -> "Webhook":
        return cls(url=os.environ["DISCORD_WEBHOOK_URL"])

    def notify(self, message: str) -> None:
        print(message, flush=True)
        payload = json.dumps({"content": message}).encode()
        headers = {"Content-Type": "application/json", "User-Agent": "kindle"}
        request = urllib.request.Request(self.url, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=10):
                pass
        except OSError as error:
            print(f"discord notification failed: {error}", flush=True)
