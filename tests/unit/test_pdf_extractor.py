"""Unit tests for app.ingestion.discovery.pdf_extractor."""
from __future__ import annotations

import io
from decimal import Decimal

import pytest

from app.ingestion.discovery.pdf_extractor import (
    PDFExtractResult,
    _extract_budgets,
    _extract_fallback,
    extract_pdf,
)


class TestExtractBudgets:
    def test_italian_format_with_thousands(self):
        result = _extract_budgets("Importo totale: € 1.250.000,00")
        assert Decimal("1250000.00") in result

    def test_plain_number(self):
        result = _extract_budgets("Costo stimato EUR 500.000")
        assert any(v == Decimal("500000") for v in result)

    def test_multiple_amounts(self):
        text = "Prima tranche: €100.000,00. Totale: €450.000,50"
        result = _extract_budgets(text)
        assert len(result) == 2

    def test_no_amounts(self):
        assert _extract_budgets("Nessun importo qui.") == []

    def test_skips_zero(self):
        result = _extract_budgets("Valore: € 0,00")
        assert all(v > 0 for v in result)


class TestFallbackExtractor:
    def test_extracts_ascii_text(self):
        content = b"Questo e' un documento pubblico con informazioni."
        result = _extract_fallback(content)
        assert result.ok
        assert "documento" in result.text

    def test_handles_empty_bytes(self):
        result = _extract_fallback(b"")
        assert result.error is None  # no error, just empty text


class TestExtractPdf:
    def test_returns_result_on_invalid_path(self):
        result = extract_pdf("/nonexistent/path/file.pdf")
        assert not result.ok
        assert result.error is not None

    def test_accepts_bytes(self):
        # Minimal valid-ish PDF bytes (won't parse with pdfplumber, triggers fallback)
        fake_pdf = b"%PDF-1.4 some public content here with useful text fragments"
        result = extract_pdf(fake_pdf)
        # Fallback should still return a result
        assert isinstance(result, PDFExtractResult)
        assert result.error is None or isinstance(result.error, str)


class TestPDFExtractResult:
    def test_ok_true_when_text_present(self):
        r = PDFExtractResult(text="hello world")
        assert r.ok is True

    def test_ok_false_when_empty(self):
        r = PDFExtractResult(text="")
        assert r.ok is False

    def test_ok_false_when_error(self):
        r = PDFExtractResult(text="some text", error="something went wrong")
        assert r.ok is False
