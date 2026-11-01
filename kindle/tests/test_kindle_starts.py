import json
import os
import time
import urllib.error
import zipfile
from email.message import Message
from io import BytesIO
from pathlib import Path

import pytest

AN_HOUR_AGO = time.time() - 3600
WEBHOOK = "https://discord.test/webhook"
ARTICLE = "https://blog.test/posts/streaming"
PAPER = "https://papers.test/files/dynamo.pdf"
GUARDED = "https://guarded.test/posts/batch"
SOLVER = "http://flaresolverr.test"
PARAGRAPH = "Streaming systems process unbounded data with low latency and exactly-once guarantees. " * 12
PAGE = f"""<html><head><title>Streaming 101</title><meta name="author" content="Tyler Akidau"></head>
<body><nav>Home Blog About</nav><article><h1>Streaming 101</h1><p>{PARAGRAPH}</p>
<img src="/images/watermark.png" alt="watermark"><p>{PARAGRAPH}</p></article><footer>Footer</footer></body></html>"""
GUIDE = "https://docs.test/guide/intro.html"
GUIDE_PRINT = "https://docs.test/print.html"
GUIDE_PAGE = """<html lang="en"><head><title>Operator Guide</title></head><body><!-- Book generated using mdBook -->
<nav><a href="../print.html">Print this book</a></nav><main><h1>Introduction</h1></main></body></html>"""
GUIDE_PRINT_PAGE = f"""<html lang="en"><head><title>Operator Guide</title></head><body><!-- Book generated using mdBook -->
<nav><a href="print.html">Print this book</a></nav><main>
<h1 id="introduction">Introduction</h1><p><svg viewBox="0 0 16 16"><path d="M0 0"/></svg>{PARAGRAPH}</p><p>Read <a href="#reconcile">the loop</a>.</p>
<img src="images/demo.gif" alt="demo">
<h1 id="reconcile">Reconcile</h1><p>{PARAGRAPH}</p><img src="images/watermark.png" alt="diagram">
</main></body></html>"""
MESSAGES = [
    {
        "id": "1300000000000000002",
        "content": f"read later {ARTICLE} and <{PAPER}> and {GUARDED} and {GUIDE}",
        "author": {"id": "7"},
    },
    {"id": "1300000000000000003", "content": f"📚 {ARTICLE} sent", "author": {"id": "8", "bot": True}},
]


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


class MemoryResponse:
    def __init__(self, body: bytes, content_type: str, url: str):
        self.body = body
        self.url = url
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size=-1):
        return self.body

    def geturl(self):
        return self.url


class MemoryWeb:
    def __init__(self):
        self.discord = []
        self.webhook = []

    def urlopen(self, request, timeout):
        url = request.full_url
        if url == WEBHOOK:
            self.webhook.append(json.loads(request.data)["content"])
            return MemoryResponse(b"", "application/json", url)
        if url.startswith("https://discord.com/api/v10/channels/42/"):
            self.discord.append((request.get_method(), url, request.data))
            body = json.dumps(MESSAGES).encode() if request.get_method() == "GET" else b"{}"
            return MemoryResponse(body, "application/json", url)
        if url == ARTICLE:
            return MemoryResponse(PAGE.encode(), "text/html", url)
        if url.endswith("/images/watermark.png"):
            return MemoryResponse(b"\x89PNG\r\n\x1a\n", "image/png", url)
        if url == PAPER:
            return MemoryResponse(b"%PDF-1.7", "application/pdf", url)
        if url == GUIDE:
            return MemoryResponse(GUIDE_PAGE.encode(), "text/html", url)
        if url == GUIDE_PRINT:
            return MemoryResponse(GUIDE_PRINT_PAGE.encode(), "text/html", url)
        if url == "https://docs.test/images/demo.gif":
            return MemoryResponse(b"GIF89a", "image/gif", url)
        if url == GUARDED:
            raise urllib.error.HTTPError(url, 403, "Forbidden", Message(), None)
        if url == f"{SOLVER}/v1":
            page = PAGE.replace("Streaming 101", "Batch 201")
            solution = {"status": "ok", "solution": {"url": GUARDED, "response": page}}
            return MemoryResponse(json.dumps(solution).encode(), "application/json", url)
        raise AssertionError(f"unexpected request {url}")


def stop_after(scans: int, between=None):
    remaining = iter(range(scans - 1))

    def sleep(seconds):
        try:
            next(remaining)
        except StopIteration:
            raise StopWatching from None
        if between:
            between()

    return sleep


def write_book(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.utime(path, (AN_HOUR_AGO, AN_HOUR_AGO))


@pytest.fixture
def kindle(monkeypatch):
    MemorySmtp.sent.clear()
    web = MemoryWeb()
    monkeypatch.setenv("KINDLE_ADDRESS", "reader@kindle.test")
    monkeypatch.setenv("SMTP_USER", "sender@mail.test")
    monkeypatch.setenv("SMTP_PASSWORD", "test")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", WEBHOOK)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "bot-token")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "42")
    monkeypatch.setenv("FLARESOLVERR_URL", SOLVER)
    from kindle import mail, webhook

    monkeypatch.setattr(mail.smtplib, "SMTP", MemorySmtp)
    monkeypatch.setattr(webhook.urllib.request, "urlopen", web.urlopen)
    return web


def test_sync_kindle_sends_each_new_book_once(kindle, monkeypatch, tmp_path) -> None:
    library = tmp_path / "library"
    state = tmp_path / "data" / "deliveries.json"
    write_book(library / "Frank Herbert" / "Dune Messiah.epub", b"epub")
    from kindle import sync_kindle

    monkeypatch.setattr(sync_kindle, "LIBRARY", library)
    monkeypatch.setattr(sync_kindle, "STATE", state)

    def import_books():
        write_book(library / "Frank Herbert" / "Dune.epub", b"epub")
        write_book(library / "Frank Herbert" / "Dune.pdf", b"pdf")
        write_book(library / "Joe Reis" / "Fundamentals" / "Fundamentals.pdf", b"pdf")

    monkeypatch.setattr(sync_kindle.time, "sleep", stop_after(3, import_books))
    with pytest.raises(StopWatching):
        sync_kindle.main()

    attachments = [next(message.iter_attachments()).get_filename() for message in MemorySmtp.sent]
    assert attachments == ["Dune Messiah.epub", "Dune.epub", "Fundamentals.pdf"]
    assert json.loads(state.read_text()) == {
        "Frank Herbert/Dune Messiah.epub": "sent",
        "Frank Herbert/Dune.epub": "sent",
        "Joe Reis/Fundamentals/Fundamentals.pdf": "sent",
    }
    assert len(kindle.webhook) == 3


def test_fetch_articles_sends_each_linked_page_document_guarded_page_and_book(kindle, monkeypatch, tmp_path) -> None:
    state = tmp_path / "data" / "fetch-articles.json"
    from kindle import fetch_articles

    monkeypatch.setattr(fetch_articles, "STATE", state)
    monkeypatch.setattr(fetch_articles.time, "sleep", stop_after(1))
    with pytest.raises(StopWatching):
        fetch_articles.main()

    attachments = [next(message.iter_attachments()) for message in MemorySmtp.sent]
    names = [attachment.get_filename() for attachment in attachments]
    article = zipfile.ZipFile(BytesIO(attachments[0].get_payload(decode=True)))
    chapter = article.read("EPUB/chapter0.xhtml").decode()
    guide = zipfile.ZipFile(BytesIO(attachments[3].get_payload(decode=True)))
    navigation = guide.read("EPUB/nav.xhtml").decode()
    introduction = guide.read("EPUB/chapter0.xhtml").decode()
    reactions = [url for method, url, _ in kindle.discord if method == "PUT"]
    replies = [json.loads(data)["content"] for method, _, data in kindle.discord if method == "POST"]
    assert names == ["Streaming 101.epub", "dynamo.pdf", "Batch 201.epub", "Operator Guide.epub"]
    assert "EPUB/images/0.png" in article.namelist()
    assert "Streaming systems process unbounded data" in chapter
    assert "Home Blog About" not in chapter
    assert "Introduction" in navigation and "Reconcile" in navigation
    assert 'href="chapter1.xhtml#reconcile"' in introduction
    assert "<svg" not in introduction and "Streaming systems" in introduction
    assert [name for name in guide.namelist() if "images/" in name] == ["EPUB/images/1.png"]
    assert len(reactions) == 4 and all(url.endswith("/reactions/%E2%9C%85/@me") for url in reactions)
    assert replies == [
        "📰 Streaming 101.epub sent to Kindle",
        "📰 dynamo.pdf sent to Kindle",
        "📰 Batch 201.epub sent to Kindle",
        "📰 Operator Guide.epub sent to Kindle",
    ]
    assert json.loads(state.read_text()) == {"last_message_id": "1300000000000000003"}
