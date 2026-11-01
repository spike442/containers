import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from kindle.mail import MAX_BYTES

BROWSER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
BLOCKED_CODES = {403, 503}


@dataclass(frozen=True)
class Download:
    content: bytes
    content_type: str
    url: str


@dataclass(frozen=True)
class Downloader:
    solver: str | None = None
    user_agent: str = BROWSER_AGENT
    max_bytes: int = MAX_BYTES
    timeout_seconds: int = 60

    @classmethod
    def from_env(cls) -> "Downloader":
        return cls(solver=os.environ.get("FLARESOLVERR_URL"))

    def get(self, url: str) -> Download:
        try:
            return self.fetch(url)
        except urllib.error.HTTPError as error:
            if not self.solver or error.code not in BLOCKED_CODES:
                raise
        return self.solve(url)

    def fetch(self, url: str) -> Download:
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            content = response.read(self.max_bytes + 1)
            content_type = response.headers.get_content_type()
            final_url = response.geturl()
        return self.checked(Download(content=content, content_type=content_type, url=final_url))

    def solve(self, url: str) -> Download:
        payload = {"cmd": "request.get", "url": url, "maxTimeout": self.timeout_seconds * 1000}
        request = urllib.request.Request(
            f"{self.solver}/v1", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds + 30) as response:
            result = json.load(response)
        if result["status"] != "ok":
            raise ValueError(f"FlareSolverr: {result['message']}")
        solution = result["solution"]
        return self.checked(
            Download(content=solution["response"].encode(), content_type="text/html", url=solution["url"])
        )

    def checked(self, download: Download) -> Download:
        if len(download.content) > self.max_bytes:
            raise ValueError(f"larger than {self.max_bytes // 1048576} MiB")
        return download
