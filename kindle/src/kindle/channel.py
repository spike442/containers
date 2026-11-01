import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

DISCORD_API = "https://discord.com/api/v10"
DISCORD_EPOCH_MS = 1420070400000


@dataclass(frozen=True)
class Channel:
    token: str
    channel_id: str

    @classmethod
    def from_env(cls) -> "Channel":
        return cls(token=os.environ["DISCORD_BOT_TOKEN"], channel_id=os.environ["DISCORD_CHANNEL_ID"])

    def request(self, method: str, path: str, payload: dict | None = None) -> bytes:
        body = json.dumps(payload).encode() if payload is not None else (None if method == "GET" else b"")
        headers = {
            "Authorization": f"Bot {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://github.com/spike442/containers, 1)",
        }
        url = f"{DISCORD_API}/channels/{self.channel_id}{path}"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()

    def messages(self, after: str) -> list[dict]:
        text = self.request("GET", f"/messages?after={after}&limit=100")
        messages = json.loads(text)
        return sorted(messages, key=lambda message: int(message["id"]))

    def react(self, message_id: str, emoji: str) -> None:
        reaction = urllib.parse.quote(emoji)
        try:
            self.request("PUT", f"/messages/{message_id}/reactions/{reaction}/@me")
        except OSError as error:
            print(f"discord reaction failed: {error}", flush=True)

    def answer(self, message_id: str, emoji: str, text: str) -> None:
        print(text, flush=True)
        self.react(message_id, emoji)
        reply = {"content": text, "message_reference": {"message_id": message_id}, "allowed_mentions": {"parse": []}}
        try:
            self.request("POST", "/messages", reply)
        except OSError as error:
            print(f"discord answer failed: {error}", flush=True)

    @staticmethod
    def now_id() -> str:
        now_ms = int(time.time() * 1000)
        return str((now_ms - DISCORD_EPOCH_MS) << 22)
