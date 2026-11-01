import unicodedata
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader, PdfWriter

BROKEN_CHARACTERS = {"�", "￿"}


@dataclass(frozen=True)
class PdfTitler:
    size_ratio: float = 0.95
    max_length: int = 150

    def title(self, pdf: bytes) -> str | None:
        reader = PdfReader(BytesIO(pdf))
        stored = reader.metadata.title if reader.metadata else None
        return self.clean(self.first_page_title(reader)) or self.clean(stored)

    def retitle(self, pdf: bytes, title: str) -> bytes:
        writer = PdfWriter(clone_from=PdfReader(BytesIO(pdf)))
        writer.add_metadata({"/Title": title})
        buffer = BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    def first_page_title(self, reader: PdfReader) -> str | None:
        fragments = []

        def collect(text, matrix, text_matrix, font, size):
            if text.strip():
                fragments.append((size * abs(text_matrix[0] or 1), text.strip()))

        reader.pages[0].extract_text(visitor_text=collect)
        if not fragments:
            return None
        biggest = max(size for size, _ in fragments)
        return " ".join(text for size, text in fragments if size >= biggest * self.size_ratio)

    def clean(self, title: str | None) -> str | None:
        if not title or BROKEN_CHARACTERS & set(title):
            return None
        printable = "".join(character for character in title if unicodedata.category(character)[0] != "C")
        cleaned = " ".join(printable.split())[: self.max_length]
        return cleaned if sum(character.isalpha() for character in cleaned) >= 3 else None
