import json
import os
import smtplib
import time
import urllib.request
from collections import defaultdict
from email.message import EmailMessage
from pathlib import Path

LIBRARY = Path(os.environ.get("LIBRARY", "/media/Books"))
STATE = Path(os.environ.get("STATE", "/data/deliveries.json"))
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
MAX_BYTES = 18 * 1024 * 1024
SETTLE_SECONDS = 120
SCAN_SECONDS = 300
CONTENT_TYPES = {".epub": "application/epub+zip", ".pdf": "application/pdf"}


def notify(message: str) -> None:
    print(message, flush=True)
    payload = json.dumps({"content": message}).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "sync-kindle"}
    request = urllib.request.Request(os.environ["DISCORD_WEBHOOK_URL"], data=payload, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10):
            pass
    except OSError as error:
        print(f"discord notification failed: {error}", flush=True)


def load_state() -> dict[str, str]:
    text = STATE.read_text()
    return json.loads(text)


def save_state(state: dict[str, str]) -> None:
    body = json.dumps(state, indent=2, sort_keys=True)
    staging = STATE.with_suffix(".tmp")
    staging.write_text(body)
    staging.replace(STATE)


def relative(path: Path) -> str:
    return path.relative_to(LIBRARY).as_posix()


def find_books() -> dict[Path, list[Path]]:
    if not LIBRARY.is_dir():
        raise FileNotFoundError(f"library {LIBRARY} is not mounted")
    books: defaultdict[Path, list[Path]] = defaultdict(list)
    for path in sorted(LIBRARY.rglob("*")):
        if path.suffix.lower() in CONTENT_TYPES and path.is_file():
            books[path.parent].append(path)
    return books


def preferred(files: list[Path]) -> Path:
    order = list(CONTENT_TYPES)
    return min(files, key=lambda path: order.index(path.suffix.lower()))


def send_to_kindle(path: Path) -> None:
    sender = os.environ["SMTP_USER"]
    maintype, subtype = CONTENT_TYPES[path.suffix.lower()].split("/")
    content = path.read_bytes()
    message = EmailMessage()
    message["From"] = sender
    message["To"] = os.environ["KINDLE_ADDRESS"]
    message["Subject"] = path.stem
    message.set_content(path.name)
    message.add_attachment(content, maintype=maintype, subtype=subtype, filename=path.name)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=60) as client:
        client.starttls()
        client.login(sender, os.environ["SMTP_PASSWORD"])
        client.send_message(message)


def deliver(path: Path, state: dict[str, str], failing: set[Path]) -> None:
    size = path.stat().st_size
    if size > MAX_BYTES:
        state[relative(path)] = "too_large"
        notify(f"⚠️ {path.name} is too large for Kindle ({size // 1048576} MB), not sent")
        return
    try:
        send_to_kindle(path)
    except (smtplib.SMTPException, OSError) as error:
        if path not in failing:
            notify(f"❌ {path.name} could not be sent, retrying every scan: {error}")
        failing.add(path)
        return
    failing.discard(path)
    state[relative(path)] = "sent"
    notify(f"📚 {path.name} sent to Kindle")


def record_library(books: dict[Path, list[Path]]) -> None:
    state = {relative(path): "baseline" for files in books.values() for path in files}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    save_state(state)
    notify(f"📖 sync-kindle started: {len(state)} files already in the library, none sent")


def sync(failing: set[Path]) -> None:
    books = find_books()
    if not STATE.exists():
        record_library(books)
        return
    state = load_state()
    for files in books.values():
        if any(relative(path) in state for path in files):
            continue
        path = preferred(files)
        if time.time() - path.stat().st_mtime < SETTLE_SECONDS:
            continue
        deliver(path, state, failing)
        save_state(state)


def main() -> None:
    failing: set[Path] = set()
    last_error = ""
    while True:
        try:
            sync(failing)
            last_error = ""
        except Exception as error:
            if repr(error) != last_error:
                notify(f"🔥 sync-kindle scan failed, retrying every scan: {error!r}")
            last_error = repr(error)
        time.sleep(SCAN_SECONDS)


if __name__ == "__main__":
    main()
