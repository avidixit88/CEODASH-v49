from __future__ import annotations

import json
from unittest.mock import patch

from engines.clinical_trials_engine import build_clinical_trials_intelligence


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps({
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {"nctId": "NCT00000001", "briefTitle": "B7-H4 ADC in Solid Tumors"},
                        "statusModule": {
                            "overallStatus": "Recruiting",
                            "startDateStruct": {"date": "2025-01"},
                            "lastUpdatePostDateStruct": {"date": "2026-05-01"},
                        },
                        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Bio"}},
                        "designModule": {"phases": ["PHASE1"]},
                        "conditionsModule": {"conditions": ["Ovarian Cancer"]},
                        "armsInterventionsModule": {"interventions": [{"name": "Example ADC"}]},
                    }
                }
            ]
        }).encode("utf-8")


@patch("engines.clinical_trials_engine.urlopen", return_value=_FakeResponse())
def test_clinical_trials_live_pull_contract(_mock_urlopen):
    summary = build_clinical_trials_intelligence()
    assert summary.total_trials == 1
    assert summary.active_trials == 1
    assert summary.source_status == "live"
    assert not summary.trial_table.empty
    assert summary.persistence_payload[0]["source"] == "clinicaltrials.gov"
    assert any(signal.bucket == "new_information" for signal in summary.signals)


@patch("engines.clinical_trials_engine.urlopen", return_value=_FakeResponse())
def test_clinical_trials_executive_language_avoids_dump_terms(_mock_urlopen):
    summary = build_clinical_trials_intelligence()
    executive_text = " ".join(signal.finding for signal in summary.signals)
    banned = [
        "returned records", "normalized records", "configured lanes", "+ more", "the new layer compares",
        "CDH6 answer", "Ovarian ADC answer", "B7-H4 answer", "active category context",
        "Core battlefield read", "Comparator read",
    ]
    assert not any(term in executive_text for term in banned)
    assert "ClinicalTrials.gov" not in executive_text or "ClinicalTrials.gov did not provide" in executive_text

class _FakeResultsResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps({
            "studies": [
                {
                    "protocolSection": {
                        "identificationModule": {"nctId": "NCT00000002", "briefTitle": "CDH6 ADC in Ovarian Cancer"},
                        "statusModule": {
                            "overallStatus": "Recruiting",
                            "startDateStruct": {"date": "2025-01"},
                            "lastUpdatePostDateStruct": {"date": "2026-05-01"},
                        },
                        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Daiichi Sankyo"}},
                        "designModule": {"phases": ["PHASE3"], "enrollmentInfo": {"count": 500}},
                        "conditionsModule": {"conditions": ["Platinum Resistant Ovarian Cancer"]},
                        "armsInterventionsModule": {"interventions": [{"name": "CDH6 ADC plus pembrolizumab"}]},
                        "outcomesModule": {
                            "primaryOutcomes": [{"measure": "Objective Response Rate (ORR)"}],
                            "secondaryOutcomes": [{"measure": "Progression-Free Survival (PFS)"}],
                        },
                        "eligibilityModule": {"eligibilityCriteria": "CDH6 expression positive biomarker selected recurrent platinum resistant ovarian cancer"},
                    },
                    "resultsSection": {
                        "outcomeMeasuresModule": {
                            "outcomeMeasures": [
                                {
                                    "title": "Objective Response Rate",
                                    "paramType": "Percentage",
                                    "unitOfMeasure": "%",
                                    "classes": [{"categories": [{"measurements": [{"value": "23"}]}]}],
                                }
                            ]
                        }
                    },
                }
            ]
        }).encode("utf-8")


@patch("engines.clinical_trials_engine.urlopen", return_value=_FakeResultsResponse())
def test_clinical_trials_surfaces_posted_result_values(_mock_urlopen):
    summary = build_clinical_trials_intelligence()
    executive_text = " ".join(signal.finding for signal in summary.signals)
    assert "Observed-result evidence surfaced" in executive_text
    assert "Objective Response Rate" in executive_text
    assert "23 %" in executive_text

from engines.sponsor_evidence_engine import build_sponsor_evidence_summary


def test_sponsor_evidence_layer_classifies_result_language(monkeypatch):
    def fake_news(_ticker):
        return [{
            "title": "Daiichi Sankyo reports updated ORR and safety data in ovarian ADC program at ASCO",
            "publisher": "Example Wire",
            "providerPublishTime": 1760000000,
            "link": "https://example.com/daiichi-orr-safety",
        }]

    monkeypatch.setattr("engines.sponsor_evidence_engine._news_items_for_ticker", fake_news)
    summary = build_sponsor_evidence_summary(["Daiichi Sankyo"])
    assert summary.source_status == "live"
    assert summary.result_items
    assert summary.result_items[0].evidence_state == "reported_data_signal"
    assert "orr" in summary.result_items[0].matched_terms
