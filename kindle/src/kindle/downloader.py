import urllib.request
from dataclasses import dataclass

from kindle.mail import MAX_BYTES

BROWSER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


@dataclass(frozen=True)
class Download:
    content: bytes
    content_type: str
    url: str


@dataclass(frozen=True)
class Downloader:
    user_agent: str = BROWSER_AGENT
    max_bytes: int = MAX_BYTES
    timeout_seconds: int = 60

    def get(self, url: str) -> Download:
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            content = response.read(self.max_bytes + 1)
            content_type = response.headers.get_content_type()
            final_url = response.geturl()
        if len(content) > self.max_bytes:
            raise ValueError(f"larger than {self.max_bytes // 1048576} MiB")
        return Download(content=content, content_type=content_type, url=final_url)
