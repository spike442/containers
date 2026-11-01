import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PdfReflower:
    width: int = 1264
    height: int = 1680
    dpi: int = 300
    timeout_seconds: int = 300

    def reflow(self, pdf: bytes) -> bytes:
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.pdf"
            target = Path(folder) / "reflowed.pdf"
            source.write_bytes(pdf)
            screen = ["-w", str(self.width), "-h", str(self.height), "-dpi", str(self.dpi)]
            subprocess.run(
                ["k2pdfopt", "-ui-", "-x", "-a-", "-fc-", "-wrap+", *screen, "-o", str(target), str(source)],
                check=True,
                capture_output=True,
                timeout=self.timeout_seconds,
            )
            return target.read_bytes()
