"""Sponsor evidence-source configuration.

This file intentionally separates trial sponsors from evidence-search handles.
ClinicalTrials.gov tells us who is running trials; this map tells the prototype
how to look for recent sponsor communications without hardcoding executive
answers. Later this can be replaced by a database table or richer source router.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SponsorEvidenceSource:
    sponsor: str
    tickers: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    priority: int = 50


SPONSOR_EVIDENCE_LOOKUP: tuple[SponsorEvidenceSource, ...] = (
    SponsorEvidenceSource("Daiichi Sankyo", ("4568.T",), ("Daiichi", "datopotamab", "DS-6000", "raludotatug"), 1),
    SponsorEvidenceSource("AstraZeneca", ("AZN",), ("AstraZeneca PLC", "AZ"), 2),
    SponsorEvidenceSource("Genmab", ("GMAB",), ("Genmab A/S",), 3),
    SponsorEvidenceSource("Bristol-Myers Squibb", ("BMY",), ("BMS", "Bristol Myers"), 4),
    SponsorEvidenceSource("Novartis Pharmaceuticals", ("NVS",), ("Novartis",), 5),
    SponsorEvidenceSource("Eli Lilly and Company", ("LLY",), ("Eli Lilly", "Lilly"), 6),
    SponsorEvidenceSource("BioNTech SE", ("BNTX",), ("BioNTech",), 7),
    SponsorEvidenceSource("Merck Sharp & Dohme LLC", ("MRK",), ("Merck", "MSD"), 8),
    SponsorEvidenceSource("Pfizer", ("PFE",), ("Pfizer Inc",), 9),
    SponsorEvidenceSource("BeOne Medicines", ("ONC", "BGNE"), ("BeiGene", "BeOne"), 10),
)


MAX_SPONSORS_PER_RUN = 8
MAX_NEWS_ITEMS_PER_TICKER = 8
