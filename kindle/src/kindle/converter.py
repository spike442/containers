import mimetypes
import urllib.parse
from dataclasses import dataclass
from html import escape
from io import BytesIO

import trafilatura
from ebooklib import epub
from lxml import html as lxml_html

from kindle.downloader import Downloader


@dataclass(frozen=True)
class Article:
    title: str
    epub: bytes


@dataclass(frozen=True)
class EpubConverter:
    downloader: Downloader

    def convert(self, url: str, page: bytes) -> Article:
        tree = trafilatura.load_html(page)
        body = trafilatura.extract(tree, url=url, output_format="html", include_images=True, include_comments=False)
        if not body:
            raise ValueError("no article text found on the page")
        metadata = trafilatura.extract_metadata(tree, default_url=url)
        title = metadata.title or url
        language = metadata.language or "en"
        byline = " · ".join(part for part in (metadata.author, metadata.sitename, metadata.date) if part)
        book = epub.EpubBook()
        book.set_identifier(url)
        book.set_title(title)
        book.set_language(language)
        if metadata.author:
            book.add_author(metadata.author)
        content = self.embed_images(book, body, url)
        chapter = epub.EpubHtml(title=title, file_name="article.xhtml", lang=language)
        chapter.content = f"<p><em>{escape(byline)}</em></p>{content}<p><a href='{escape(url)}'>{escape(url)}</a></p>"
        book.add_item(chapter)
        book.toc = [chapter]
        book.spine = [chapter]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        buffer = BytesIO()
        epub.write_epub(buffer, book)
        return Article(title=title, epub=buffer.getvalue())

    def embed_images(self, book: epub.EpubBook, body: str, url: str) -> str:
        tree = lxml_html.fromstring(body)
        for index, image in enumerate(tree.iter("img")):
            source = urllib.parse.urljoin(url, image.get("src", ""))
            try:
                download = self.downloader.get(source)
            except (OSError, ValueError):
                image.drop_tree()
                continue
            if not download.content_type.startswith("image/"):
                image.drop_tree()
                continue
            extension = mimetypes.guess_extension(download.content_type) or ".img"
            name = f"images/{index}{extension}"
            item = epub.EpubItem(
                uid=f"image{index}", file_name=name, media_type=download.content_type, content=download.content
            )
            book.add_item(item)
            image.set("src", name)
        content = tree.find("body") if tree.find("body") is not None else tree
        return "".join(lxml_html.tostring(child, encoding="unicode") for child in content)
