import json
import os
import time
from pathlib import Path

import pytest

AN_HOUR_AGO = time.time() - 3600


class StopWatching(Exception):
    pass


class MemorySmtp:
    sent = []

    def __init__(self, host, port, timeout):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, message):
        MemorySmtp.sent.append(message)


class MemoryDiscord:
    messages = []

    def __init__(self, request, timeout):
        body = json.loads(request.data)
        MemoryDiscord.messages.append(body["content"])

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def write_book(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.utime(path, (AN_HOUR_AGO, AN_HOUR_AGO))


def test_sync_kindle_sends_each_new_book_once(monkeypatch, tmp_path) -> None:
    library = tmp_path / "library"
    state = tmp_path / "data" / "deliveries.json"
    write_book(library / "Frank Herbert" / "Dune Messiah.epub", b"epub")
    monkeypatch.setenv("LIBRARY", str(library))
    monkeypatch.setenv("STATE", str(state))
    monkeypatch.setenv("KINDLE_ADDRESS", "reader@kindle.test")
    monkeypatch.setenv("SMTP_USER", "sender@mail.test")
    monkeypatch.setenv("SMTP_PASSWORD", "test")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/webhook")
    from containers.sync_kindle import main

    monkeypatch.setattr(main.smtplib, "SMTP", MemorySmtp)
    monkeypatch.setattr(main.urllib.request, "urlopen", MemoryDiscord)

    scans = iter([None, None])

    def next_scan(seconds):
        try:
            next(scans)
        except StopIteration:
            raise StopWatching from None
        write_book(library / "Frank Herbert" / "Dune.epub", b"epub")
        write_book(library / "Frank Herbert" / "Dune.pdf", b"pdf")
        write_book(library / "Joe Reis" / "Fundamentals" / "Fundamentals.pdf", b"pdf")

    monkeypatch.setattr(main.time, "sleep", next_scan)

    with pytest.raises(StopWatching):
        main.main()

    attachments = [next(message.iter_attachments()).get_filename() for message in MemorySmtp.sent]
    recorded = json.loads(state.read_text())
    assert attachments == ["Dune.epub", "Fundamentals.pdf"]
    assert recorded == {
        "Frank Herbert/Dune Messiah.epub": "baseline",
        "Frank Herbert/Dune.epub": "sent",
        "Joe Reis/Fundamentals/Fundamentals.pdf": "sent",
    }
    assert len(MemoryDiscord.messages) == 3
