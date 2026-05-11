"""Adaptive sponsor-evidence layer.

ClinicalTrials.gov can show protocol intent, but it often does not contain
posted efficacy values for ongoing trials. This module takes the sponsors
surfaced from the clinical-trials pull, checks available market/news handles,
and classifies whether recent sponsor communications mention readouts, future
data timing, or clinically meaningful endpoint language.

The output is intentionally structured as evidence states, not curated prose.
The executive summary then decides what deserves surface area.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import time
from typing import Any, Iterable

try:  # optional in tests/fallbacks
    import yfinance as yf
except Exception:  # pragma: no cover - environment-specific
    yf = None  # type: ignore[assignment]

from config.sponsor_evidence_sources import (
    MAX_NEWS_ITEMS_PER_TICKER,
    MAX_SPONSORS_PER_RUN,
    SPONSOR_EVIDENCE_LOOKUP,
    SponsorEvidenceSource,
)


RESULT_TERMS = (
    "orr", "objective response", "overall response", "response rate",
    "pfs", "progression-free", "duration of response", "dor",
    "overall survival", "os", "complete response", "partial response",
)
SAFETY_TERMS = (
    "safety", "tolerability", "adverse event", "toxicity", "grade 3",
    "discontinuation", "dose limiting", "recommended phase 2", "rp2d",
)
DATA_TIMING_TERMS = (
    "asco", "aacr", "esmo", "sitc", "present", "presentation", "abstract",
    "data", "readout", "topline", "updated results", "oral presentation",
)
CLINICAL_CONTEXT_TERMS = (
    "ovarian", "cdh6", "b7-h4", "antibody-drug conjugate", "adc",
    "platinum-resistant", "gynecologic", "solid tumor", "phase 1", "phase 2", "phase 3",
)


@dataclass(frozen=True)
class SponsorEvidenceItem:
    sponsor: str
    ticker: str
    title: str
    publisher: str
    published_at: str
    url: str
    evidence_state: str
    matched_terms: tuple[str, ...]
    relevance_score: int


@dataclass(frozen=True)
class SponsorEvidenceSummary:
    source_status: str
    fetched_at_utc: str
    sponsors_checked: tuple[str, ...]
    items: tuple[SponsorEvidenceItem, ...]
    source_errors: tuple[str, ...]

    @property
    def result_items(self) -> list[SponsorEvidenceItem]:
        return [i for i in self.items if i.evidence_state == "reported_data_signal"]

    @property
    def timing_items(self) -> list[SponsorEvidenceItem]:
        return [i for i in self.items if i.evidence_state == "future_data_timing_signal"]

    @property
    def clinical_items(self) -> list[SponsorEvidenceItem]:
        return [i for i in self.items if i.evidence_state in {"reported_data_signal", "future_data_timing_signal", "clinical_context_signal"}]


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("–", "-").split())


def _matches_any(text: str, terms: Iterable[str]) -> list[str]:
    haystack = _norm(text)
    return [term for term in terms if term in haystack]


def _source_for_sponsor(sponsor: str) -> SponsorEvidenceSource | None:
    sponsor_l = _norm(sponsor)
    candidates: list[tuple[int, SponsorEvidenceSource]] = []
    for source in SPONSOR_EVIDENCE_LOOKUP:
        names = (source.sponsor, *source.aliases)
        if any(_norm(name) in sponsor_l or sponsor_l in _norm(name) for name in names):
            candidates.append((source.priority, source))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0])[0][1]


def _select_sponsor_sources(sponsors: Iterable[str]) -> list[SponsorEvidenceSource]:
    selected: dict[str, SponsorEvidenceSource] = {}
    for sponsor in sponsors:
        source = _source_for_sponsor(sponsor)
        if source is not None:
            selected[source.sponsor] = source
    return sorted(selected.values(), key=lambda s: s.priority)[:MAX_SPONSORS_PER_RUN]


def _news_items_for_ticker(ticker: str) -> list[dict[str, Any]]:
    if yf is None:
        raise RuntimeError("yfinance is not available")
    raw = yf.Ticker(ticker).news or []  # type: ignore[union-attr]
    return raw[:MAX_NEWS_ITEMS_PER_TICKER]


def _extract_title(item: dict[str, Any]) -> str:
    return str(item.get("title") or item.get("content", {}).get("title") or "").strip()


def _extract_publisher(item: dict[str, Any]) -> str:
    return str(item.get("publisher") or item.get("content", {}).get("provider", {}).get("displayName") or "").strip()


def _extract_url(item: dict[str, Any]) -> str:
    return str(item.get("link") or item.get("content", {}).get("canonicalUrl", {}).get("url") or "").strip()


def _extract_published_at(item: dict[str, Any]) -> str:
    ts = item.get("providerPublishTime") or item.get("content", {}).get("pubDate")
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts, UTC).date().isoformat()
        except Exception:
            return ""
    return str(ts or "").strip()[:10]


def _classify_item(sponsor: str, ticker: str, item: dict[str, Any]) -> SponsorEvidenceItem | None:
    title = _extract_title(item)
    if not title:
        return None
    publisher = _extract_publisher(item)
    url = _extract_url(item)
    published_at = _extract_published_at(item)
    text = " ".join([title, publisher, url])
    result_terms = _matches_any(text, RESULT_TERMS)
    safety_terms = _matches_any(text, SAFETY_TERMS)
    timing_terms = _matches_any(text, DATA_TIMING_TERMS)
    context_terms = _matches_any(text, CLINICAL_CONTEXT_TERMS)

    if not any([result_terms, safety_terms, timing_terms, context_terms]):
        return None

    relevance = len(result_terms) * 4 + len(safety_terms) * 3 + len(timing_terms) * 2 + len(context_terms)
    if result_terms or safety_terms:
        state = "reported_data_signal"
    elif timing_terms:
        state = "future_data_timing_signal"
    else:
        state = "clinical_context_signal"

    terms = tuple(dict.fromkeys(result_terms + safety_terms + timing_terms + context_terms))
    return SponsorEvidenceItem(
        sponsor=sponsor,
        ticker=ticker,
        title=title,
        publisher=publisher,
        published_at=published_at,
        url=url,
        evidence_state=state,
        matched_terms=terms,
        relevance_score=relevance,
    )


def build_sponsor_evidence_summary(sponsors: Iterable[str]) -> SponsorEvidenceSummary:
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    sources = _select_sponsor_sources(sponsors)
    checked: list[str] = []
    items: list[SponsorEvidenceItem] = []
    errors: list[str] = []

    for source in sources:
        checked.append(source.sponsor)
        for ticker in source.tickers:
            try:
                for raw_item in _news_items_for_ticker(ticker):
                    item = _classify_item(source.sponsor, ticker, raw_item)
                    if item is not None:
                        items.append(item)
            except Exception as exc:  # upstream news failure should not break analysis
                errors.append(f"{source.sponsor} / {ticker}: {type(exc).__name__}: {exc}")
            # Small politeness pause; this is not a cache, just avoids hammering sequential tickers.
            time.sleep(0.03)

    # De-duplicate by title/ticker, then prioritize strongest evidence.
    deduped: dict[tuple[str, str], SponsorEvidenceItem] = {}
    for item in items:
        key = (_norm(item.title), item.ticker)
        existing = deduped.get(key)
        if existing is None or item.relevance_score > existing.relevance_score:
            deduped[key] = item
    ordered = sorted(deduped.values(), key=lambda i: (i.relevance_score, i.published_at), reverse=True)[:12]
    if ordered:
        status = "live"
    elif checked and errors:
        status = "degraded"
    elif checked:
        status = "empty"
    else:
        status = "unmapped"

    return SponsorEvidenceSummary(
        source_status=status,
        fetched_at_utc=fetched_at,
        sponsors_checked=tuple(checked),
        items=tuple(ordered),
        source_errors=tuple(errors),
    )


def sponsor_evidence_table(summary: SponsorEvidenceSummary):
    import pandas as pd

    return pd.DataFrame([
        {
            "Sponsor": item.sponsor,
            "Ticker": item.ticker,
            "Evidence State": item.evidence_state,
            "Title": item.title,
            "Publisher": item.publisher,
            "Published": item.published_at,
            "Matched Terms": ", ".join(item.matched_terms),
            "Relevance Score": item.relevance_score,
            "URL": item.url,
        }
        for item in summary.items
    ])
