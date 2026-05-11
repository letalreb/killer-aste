"""
PDF text and structured data extraction.

Uses pdfplumber as the primary engine (best results on Italian public documents
with tables, e.g. perizie, piani urbanistici, bandi di alienazione).
Falls back to raw text concatenation when pdfplumber is unavailable or fails.

Public entry-point: extract_pdf(source) → PDFExtractResult
  source may be:
    - bytes   — PDF content already in memory
    - str     — local file path or HTTP/HTTPS URL
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Optional

import structlog

log = structlog.get_logger(__name__)

_BUDGET_RE = re.compile(
    r"(?:€\s*|EUR\s*|euro\s*)?([\d]{1,3}(?:[.\s][\d]{3})*(?:,\d{1,2})?)",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\b")


@dataclass
class PDFExtractResult:
    text: str                                    # full extracted text
    tables: list[list[list[str]]] = field(default_factory=list)  # nested rows/cols
    metadata: dict = field(default_factory=dict) # title, author, pages, etc.
    budget_hints: list[Decimal] = field(default_factory=list)    # money amounts found
    date_hints: list[str] = field(default_factory=list)          # date strings found
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.text.strip())


def extract_pdf(source: bytes | str) -> PDFExtractResult:
    """
    Extract text and structured data from a PDF.

    Accepts raw bytes or a file path string.
    Never raises — returns a PDFExtractResult with error set on failure.
    """
    try:
        raw = _load_bytes(source)
    except Exception as exc:
        return PDFExtractResult(text="", error=f"load_failed: {exc}")

    try:
        import pdfplumber
        return _extract_with_pdfplumber(raw)
    except ImportError:
        log.warning("pdf_extractor.pdfplumber_unavailable")
        return _extract_fallback(raw)
    except Exception as exc:
        log.warning("pdf_extractor.pdfplumber_error", error=str(exc))
        return _extract_fallback(raw)


# ── Loaders ───────────────────────────────────────────────────────────────────

def _load_bytes(source: bytes | str) -> bytes:
    if isinstance(source, bytes):
        return source
    path = str(source)
    with open(path, "rb") as f:
        return f.read()


# ── pdfplumber extractor ──────────────────────────────────────────────────────

def _extract_with_pdfplumber(raw: bytes) -> PDFExtractResult:
    import pdfplumber

    text_parts: list[str] = []
    tables: list[list[list[str]]] = []
    metadata: dict = {}

    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        metadata["pages"] = len(pdf.pages)
        if pdf.metadata:
            metadata.update({
                k: v for k, v in pdf.metadata.items()
                if isinstance(v, (str, int, float))
            })

        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)

            for table in page.extract_tables():
                cleaned = [
                    [cell or "" for cell in row]
                    for row in table
                    if any(cell for cell in row)
                ]
                if cleaned:
                    tables.append(cleaned)

    full_text = "\n".join(text_parts)
    return PDFExtractResult(
        text=full_text,
        tables=tables,
        metadata=metadata,
        budget_hints=_extract_budgets(full_text),
        date_hints=_DATE_RE.findall(full_text),
    )


# ── Fallback extractor (no pdfplumber) ───────────────────────────────────────

def _extract_fallback(raw: bytes) -> PDFExtractResult:
    """Minimal fallback: scan PDF byte stream for printable ASCII runs."""
    try:
        text = raw.decode("latin-1", errors="replace")
        # Extract contiguous printable text fragments (crude but functional)
        fragments = re.findall(r"[\x20-\x7e\n\r]{4,}", text)
        full_text = " ".join(fragments)
        return PDFExtractResult(
            text=full_text,
            metadata={"method": "fallback_ascii"},
            budget_hints=_extract_budgets(full_text),
            date_hints=_DATE_RE.findall(full_text),
        )
    except Exception as exc:
        return PDFExtractResult(text="", error=f"fallback_failed: {exc}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_budgets(text: str) -> list[Decimal]:
    """Find all money amounts in Italian format (1.234.567,89) within the text."""
    results: list[Decimal] = []
    for m in _BUDGET_RE.finditer(text):
        raw = m.group(1).replace(" ", "").replace(".", "").replace(",", ".")
        try:
            val = Decimal(raw)
            if val > 0:
                results.append(val)
        except InvalidOperation:
            continue
    return results
