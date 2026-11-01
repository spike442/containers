import os
import smtplib
import time
from collections import defaultdict
from pathlib import Path

from kindle.mail import MAX_BYTES, Kindle
from kindle.state import StateFile
from kindle.webhook import Webhook

LIBRARY = Path(os.environ.get("LIBRARY", "/media/Books"))
STATE = Path(os.environ.get("STATE", "/data/deliveries.json"))
SETTLE_SECONDS = 120
SCAN_SECONDS = 300
CONTENT_TYPES = {".epub": "application/epub+zip", ".pdf": "application/pdf"}


def relative(path: Path) -> str:
    return path.relative_to(LIBRARY).as_posix()


def find_books() -> dict[Path, list[Path]]:
    if not LIBRARY.is_dir():
        raise FileNotFoundError(f"library {LIBRARY} is not mounted")
    books: defaultdict[Path, list[Path]] = defaultdict(list)
    for path in sorted(LIBRARY.rglob("*")):
        if path.suffix.lower() in CONTENT_TYPES and path.is_file():
            books[path.with_suffix("")].append(path)
    return books


def preferred(files: list[Path]) -> Path:
    order = list(CONTENT_TYPES)
    return min(files, key=lambda path: order.index(path.suffix.lower()))


def deliver(path: Path, state: dict[str, str], failing: set[Path], kindle: Kindle, webhook: Webhook) -> None:
    size = path.stat().st_size
    if size > MAX_BYTES:
        state[relative(path)] = "too_large"
        webhook.notify(f"⚠️ {path.name} is too large for Kindle ({size // 1048576} MB), not sent")
        return
    content_type = CONTENT_TYPES[path.suffix.lower()]
    try:
        content = path.read_bytes()
        kindle.send(path.name, content, content_type)
    except (smtplib.SMTPException, OSError) as error:
        if path not in failing:
            webhook.notify(f"❌ {path.name} could not be sent, retrying every scan: {error}")
        failing.add(path)
        return
    failing.discard(path)
    state[relative(path)] = "sent"
    webhook.notify(f"📚 {path.name} sent to Kindle")


def sync(failing: set[Path], kindle: Kindle, webhook: Webhook, state_file: StateFile) -> None:
    books = find_books()
    state = state_file.load()
    for files in books.values():
        if any(relative(path) in state for path in files):
            continue
        path = preferred(files)
        if time.time() - path.stat().st_mtime < SETTLE_SECONDS:
            continue
        deliver(path, state, failing, kindle, webhook)
        state_file.save(state)


def main() -> None:
    kindle = Kindle.from_env()
    webhook = Webhook.from_env()
    state_file = StateFile(STATE)
    failing: set[Path] = set()
    last_error = ""
    while True:
        try:
            sync(failing, kindle, webhook, state_file)
            last_error = ""
        except Exception as error:
            if repr(error) != last_error:
                webhook.notify(f"🔥 sync-kindle scan failed, retrying every scan: {error!r}")
            last_error = repr(error)
        time.sleep(SCAN_SECONDS)


if __name__ == "__main__":
    main()
