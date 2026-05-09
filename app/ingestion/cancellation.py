"""
In-memory cancellation registry for ingestion runs.

The admin API writes to this set; the ingestion service reads from it
between page iterations. Single-process only (fine for Render free tier).
"""
from __future__ import annotations

_pending: set[str] = set()


def request_cancel(run_id: str) -> None:
    _pending.add(run_id)


def is_cancel_requested(run_id: str) -> bool:
    return run_id in _pending


def consume(run_id: str) -> None:
    """Mark as handled so the flag doesn't linger."""
    _pending.discard(run_id)
