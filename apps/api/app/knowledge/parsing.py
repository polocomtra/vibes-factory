"""Safe, provenance-preserving PDF and text parsing/chunking."""

import re
import unicodedata
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader


class DocumentParseError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ParsedSegment:
    text: str
    page: int | None
    section: str | None


@dataclass(frozen=True)
class Chunk:
    text: str
    token_count: int
    page: int | None
    section: str | None


def normalize_text(value: str) -> str:
    value = (
        unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    )
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def parse_document(filename: str, mime_type: str, data: bytes) -> list[ParsedSegment]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" or mime_type == "application/pdf":
        if not data.startswith(b"%PDF-"):
            raise DocumentParseError(
                "DOCUMENT_TYPE_UNSUPPORTED", "The PDF signature is invalid."
            )
        try:
            reader = PdfReader(BytesIO(data))
            if len(reader.pages) > 500:
                raise DocumentParseError(
                    "DOCUMENT_TOO_LARGE", "PDF exceeds the 500 page limit."
                )
            segments = [
                ParsedSegment(
                    normalize_text(page.extract_text() or ""), index + 1, None
                )
                for index, page in enumerate(reader.pages)
            ]
        except DocumentParseError:
            raise
        except Exception as exc:
            raise DocumentParseError(
                "DOCUMENT_PARSE_FAILED", "The PDF could not be parsed."
            ) from exc
        if not any(segment.text for segment in segments):
            raise DocumentParseError(
                "DOCUMENT_NO_EXTRACTABLE_TEXT",
                "This PDF has no extractable text. OCR is not enabled.",
            )
        return [segment for segment in segments if segment.text]
    if suffix not in {".txt", ".md", ".markdown"} or mime_type not in {
        "text/plain",
        "text/markdown",
        "application/octet-stream",
    }:
        raise DocumentParseError(
            "DOCUMENT_TYPE_UNSUPPORTED",
            "Only PDF, UTF-8 TXT and Markdown files are supported.",
        )
    try:
        text = normalize_text(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise DocumentParseError(
            "DOCUMENT_ENCODING_UNSUPPORTED", "Text documents must be UTF-8."
        ) from exc
    if not text:
        raise DocumentParseError(
            "DOCUMENT_NO_EXTRACTABLE_TEXT", "The document has no extractable text."
        )
    sections: list[ParsedSegment] = []
    heading: str | None = None
    current: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            if current:
                sections.append(ParsedSegment("\n".join(current), None, heading))
                current = []
            heading = line.lstrip("# ").strip() or heading
        else:
            current.append(line)
    if current:
        sections.append(ParsedSegment("\n".join(current), None, heading))
    return [segment for segment in sections if segment.text.strip()]


def chunk_segments(
    segments: list[ParsedSegment], target_tokens: int = 400, overlap: int = 64
) -> list[Chunk]:
    """Token-light deterministic chunker; worker can swap in pinned E5 tokenizer."""
    chunks: list[Chunk] = []
    for segment in segments:
        words = segment.text.split()
        if not words:
            continue
        start = 0
        while start < len(words):
            end = min(len(words), start + target_tokens)
            text = " ".join(words[start:end]).strip()
            chunks.append(Chunk(text, end - start, segment.page, segment.section))
            if end == len(words):
                break
            start = max(start + 1, end - overlap)
    return chunks
