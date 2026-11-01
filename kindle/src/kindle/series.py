import re
import urllib.parse
from dataclasses import dataclass

from lxml import html as lxml_html

from kindle.downloader import Download, Downloader

POST_LINK_TEXTS = frozenset({"read more", "continue reading", "read article", "read post"})


@dataclass(frozen=True)
class BlogSeries:
    downloader: Downloader
    link_texts: frozenset[str] = POST_LINK_TEXTS
    min_posts: int = 3
    max_posts: int = 30

    def posts(self, index: Download) -> list[Download]:
        return [post for url in self.post_urls(index) if (post := self.download(url))]

    def post_urls(self, index: Download) -> list[str]:
        tree = lxml_html.fromstring(index.content)
        urls = []
        for link in tree.xpath("//a[@href]"):
            text = " ".join(re.sub(r"[^a-z]+", " ", link.text_content().lower()).split())
            url = urllib.parse.urldefrag(urllib.parse.urljoin(index.url, link.get("href")))[0]
            if text in self.link_texts and url not in urls:
                urls.append(url)
        return urls[: self.max_posts] if len(urls) >= self.min_posts else []

    def download(self, url: str) -> Download | None:
        try:
            return self.downloader.get(url)
        except (OSError, ValueError) as error:
            print(f"⚠️ {url} skipped from the series: {error}", flush=True)
            return None
