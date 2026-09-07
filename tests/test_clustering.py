from roberta_eval.clustering import cluster_findings, cluster_summary


def _finding(fid, *, category="NUMERICAL_ERROR", service="market_report", reason="field_check_failed", severity="HIGH"):
    return {
        "finding_id": fid,
        "category": category,
        "service": service,
        "reason": reason,
        "severity": severity,
        "run_id": "run1",
        "case_id": fid,
    }


def test_same_material_failure_collapses_into_one_cluster() -> None:
    findings = [_finding("a"), _finding("b"), _finding("c")]
    localizations = [
        {"finding_id": "a", "likely_layer": "roberta"},
        {"finding_id": "b", "likely_layer": "roberta"},
        {"finding_id": "c", "likely_layer": "roberta"},
    ]
    clusters = cluster_findings(findings, localizations)
    assert len(clusters) == 1
    assert clusters[0]["occurrence_count"] == 3
    assert clusters[0]["likely_layer"] == "roberta"


def test_different_reason_or_layer_stays_separate() -> None:
    findings = [_finding("a"), _finding("b", reason="other")]
    localizations = [
        {"finding_id": "a", "likely_layer": "cmis"},
        {"finding_id": "b", "likely_layer": "cmis"},
    ]
    assert len(cluster_findings(findings, localizations)) == 2


def test_highest_member_severity_wins() -> None:
    findings = [
        _finding("a", severity="HIGH"),
        _finding("b", severity="CRITICAL"),
    ]
    clusters = cluster_findings(findings)
    assert clusters[0]["severity"] == "CRITICAL"


def test_unknown_localization_remains_unknown() -> None:
    cluster = cluster_findings([_finding("a")])[0]
    assert cluster["likely_layer"] == "unknown"


def test_evaluation_incomplete_is_not_product_defect() -> None:
    cluster = cluster_findings([
        _finding("a", category="EVALUATION_INCOMPLETE", reason="structured_evidence_unavailable")
    ])[0]
    assert cluster["evaluation_incomplete"] is True
    assert cluster["actionable_product_defect"] is False


def test_clustering_is_reproducible() -> None:
    findings = [_finding("b"), _finding("a")]
    assert cluster_findings(findings) == cluster_findings(list(reversed(findings)))


def test_summary_counts_occurrences() -> None:
    clusters = cluster_findings([_finding("a"), _finding("b")])
    summary = cluster_summary(clusters)
    assert summary["cluster_count"] == 1
    assert summary["occurrence_count"] == 2
