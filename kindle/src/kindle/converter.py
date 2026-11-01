import mimetypes
import urllib.parse
from dataclasses import dataclass
from html import escape
from io import BytesIO

import trafilatura
from ebooklib import epub
from lxml import html as lxml_html

from kindle.downloader import Downloader

MAX_IMAGE_BYTES = 1024 * 1024
SKIPPED_IMAGE_TYPES = {"image/gif"}
CHAPTER_FILE = "chapter{}.xhtml"
UNSUPPORTED_ELEMENTS = ".//svg | .//script | .//style | .//input | .//button | .//form | .//iframe"


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
        byline = " · ".join(part for part in (metadata.author, metadata.sitename, metadata.date) if part)
        content = f"<p><em>{escape(byline)}</em></p>{body}<p><a href='{escape(url)}'>{escape(url)}</a></p>"
        return self.build(url, title, metadata.language or "en", metadata.author, [(title, content)])

    def convert_book(self, url: str, page: bytes) -> Article:
        tree = lxml_html.fromstring(page)
        main = tree.find(".//main")
        if main is None:
            raise ValueError("no book content found on the page")
        title = (tree.findtext(".//title") or url).strip()
        for element in main.xpath(UNSUPPORTED_ELEMENTS):
            element.drop_tree()
        chapters = []
        for element in main:
            if element.tag == "h1" or not chapters:
                chapters.append((element.text_content().strip() or title, []))
            chapters[-1][1].append(element)
        files = {
            anchor: CHAPTER_FILE.format(index)
            for index, (_, elements) in enumerate(chapters)
            for element in elements
            for anchor in element.xpath("descendant-or-self::*/@id")
        }
        for index, (_, elements) in enumerate(chapters):
            for element in elements:
                for link in element.xpath("descendant-or-self::a[starts-with(@href, '#')]"):
                    target = files.get(link.get("href")[1:])
                    if target and target != CHAPTER_FILE.format(index):
                        link.set("href", f"{target}{link.get('href')}")
        contents = [
            (name, "".join(lxml_html.tostring(element, encoding="unicode") for element in elements))
            for name, elements in chapters
        ]
        return self.build(url, title, tree.get("lang") or "en", None, contents)

    def build(self, url: str, title: str, language: str, author: str | None, chapters: list) -> Article:
        book = epub.EpubBook()
        book.set_identifier(url)
        book.set_title(title)
        book.set_language(language)
        if author:
            book.add_author(author)
        items = []
        for index, (name, content) in enumerate(chapters):
            item = epub.EpubHtml(title=name, file_name=CHAPTER_FILE.format(index), lang=language)
            item.content = self.embed_images(book, content, url)
            book.add_item(item)
            items.append(item)
        book.toc = items
        book.spine = items
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        buffer = BytesIO()
        epub.write_epub(buffer, book)
        return Article(title=title, epub=buffer.getvalue())

    def embed_images(self, book: epub.EpubBook, content: str, url: str) -> str:
        tree = lxml_html.fragment_fromstring(content, create_parent="div")
        for image in list(tree.iter("img")):
            source = urllib.parse.urljoin(url, image.get("src", ""))
            try:
                download = self.downloader.get(source)
            except (OSError, ValueError):
                image.drop_tree()
                continue
            if (
                not download.content_type.startswith("image/")
                or download.content_type in SKIPPED_IMAGE_TYPES
                or len(download.content) > MAX_IMAGE_BYTES
            ):
                image.drop_tree()
                continue
            index = len(book.items)
            extension = mimetypes.guess_extension(download.content_type) or ".img"
            name = f"images/{index}{extension}"
            item = epub.EpubItem(
                uid=f"image{index}", file_name=name, media_type=download.content_type, content=download.content
            )
            book.add_item(item)
            image.set("src", name)
        return escape(tree.text or "") + "".join(lxml_html.tostring(child, encoding="unicode") for child in tree)
