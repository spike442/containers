import os
import re
import subprocess
import time
import urllib.parse
from pathlib import Path

from lxml import html as lxml_html

from kindle.channel import Channel
from kindle.converter import EpubConverter
from kindle.downloader import Download, Downloader
from kindle.mail import MAX_BYTES, Kindle
from kindle.reflower import PdfReflower
from kindle.state import StateFile
from kindle.webhook import Webhook

STATE = Path(os.environ.get("STATE", "/data/fetch-articles.json"))
POLL_SECONDS = 30
URL_PATTERN = re.compile(r"https?://[^\s<>|]+")
DOCUMENT_TYPES = {".pdf": "application/pdf", ".epub": "application/epub+zip"}
PAGE_TYPES = {"text/html", "application/xhtml+xml"}
MDBOOK_MARKER = b"Book generated using mdBook"


def document_suffix(url: str, content_type: str) -> str | None:
    for suffix, document_type in DOCUMENT_TYPES.items():
        if content_type == document_type:
            return suffix
    path = urllib.parse.urlparse(url).path
    suffix = Path(path).suffix.lower()
    return suffix if suffix in DOCUMENT_TYPES else None


def safe_name(title: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', " ", title).strip()
    return cleaned[:100] or "article"


def print_version(download: Download, downloader: Downloader) -> Download:
    tree = lxml_html.fromstring(download.content)
    links = [href for href in tree.xpath("//a/@href") if href.endswith("print.html")]
    if not links:
        return download
    url = urllib.parse.urljoin(download.url, links[0])
    return download if url == download.url else downloader.get(url)


def reflowed(pdf: bytes, reflower: PdfReflower) -> bytes:
    try:
        content = reflower.reflow(pdf)
    except (OSError, subprocess.SubprocessError) as error:
        print(f"⚠️ PDF sent unchanged, reflow failed: {error}", flush=True)
        return pdf
    if len(content) > MAX_BYTES:
        print("⚠️ PDF sent unchanged, reflowed file is larger than 18 MiB", flush=True)
        return pdf
    return content


def fetch(url: str, converter: EpubConverter, reflower: PdfReflower) -> tuple[str, bytes, str]:
    download = converter.downloader.get(url)
    suffix = document_suffix(download.url, download.content_type)
    if suffix:
        path = urllib.parse.urlparse(download.url).path
        name = urllib.parse.unquote(Path(path).name)
        filename = name if name.lower().endswith(suffix) else f"document{suffix}"
        content = reflowed(download.content, reflower) if suffix == ".pdf" else download.content
        return filename, content, DOCUMENT_TYPES[suffix]
    if download.content_type not in PAGE_TYPES:
        raise ValueError(f"unsupported content type {download.content_type}")
    if MDBOOK_MARKER in download.content:
        book = print_version(download, converter.downloader)
        article = converter.convert_book(book.url, book.content)
    else:
        article = converter.convert(download.url, download.content)
    if len(article.epub) > MAX_BYTES:
        raise ValueError("the EPUB is larger than 18 MiB")
    return f"{safe_name(article.title)}.epub", article.epub, DOCUMENT_TYPES[".epub"]


def handle(message: dict, channel: Channel, kindle: Kindle, converter: EpubConverter, reflower: PdfReflower) -> None:
    channel.react(message["id"], "👀")
    urls = URL_PATTERN.findall(message.get("content", ""))
    for url in urls:
        try:
            filename, content, content_type = fetch(url, converter, reflower)
            kindle.send(filename, content, content_type)
        except Exception as error:
            channel.answer(message["id"], "❌", f"❌ {url} could not be sent: {error}")
            continue
        channel.answer(message["id"], "💯", f"📰 {filename} sent to Kindle")


def is_from_a_person(message: dict) -> bool:
    return "webhook_id" not in message and not message["author"].get("bot")


def poll(
    state: dict,
    channel: Channel,
    kindle: Kindle,
    state_file: StateFile,
    *,
    converter: EpubConverter,
    reflower: PdfReflower,
) -> None:
    if "last_message_id" not in state:
        state["last_message_id"] = Channel.now_id()
        state_file.save(state)
    messages = channel.messages(state["last_message_id"])
    for message in messages:
        if is_from_a_person(message):
            handle(message, channel, kindle, converter, reflower)
        state["last_message_id"] = message["id"]
        state_file.save(state)


def main() -> None:
    channel = Channel.from_env()
    kindle = Kindle.from_env()
    webhook = Webhook.from_env()
    state_file = StateFile(STATE)
    converter = EpubConverter(Downloader.from_env())
    reflower = PdfReflower()
    state = state_file.load()
    last_error = ""
    while True:
        try:
            poll(state, channel, kindle, state_file, converter=converter, reflower=reflower)
            last_error = ""
        except Exception as error:
            if repr(error) != last_error:
                webhook.notify(f"🔥 fetch-articles poll failed, retrying every poll: {error!r}")
            last_error = repr(error)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
