from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol

QUALITY_GRADER_VERSION = "roberta_human_quality/v1"


class SemanticJudge(Protocol):
    name: str

    def judge(self, record: dict[str, Any]) -> dict[str, Any]:
        """Return advisory semantic scores. Implementations must not assert factual authority."""
        ...


_INTERNAL_TERMS = (
    "chain_scout_cmis",
    "execution_authorized",
    "roberta_decision/v1",
    "instant_x1_scan_product_view/v1",
    "cmis_status",
)

_UNCERTAINTY_TERMS = (
    "unknown",
    "uncertain",
    "unverified",
    "not verified",
    "can't verify",
    "cannot verify",
    "stale",
    "not current",
    "unavailable",
    "not available",
    "partial",
    "limited evidence",
)

_RECOMMENDATION_TERMS = (
    "i'd ",
    "i would ",
    "recommend",
    "avoid",
    "wait",
    "watch",
    "buy",
    "hold",
    "reduce",
    "exit",
    "don't buy",
    "do not buy",
)

_STOPWORDS = {
    "the","a","an","is","are","was","were","to","of","and","or","in","on","for",
    "with","this","that","what","how","does","do","did","me","i","it","you","my",
}


def _reply(record: dict[str, Any]) -> str:
    response = record.get("response")
    if not isinstance(response, dict):
        return ""
    value = response.get("reply")
    return value.strip() if isinstance(value, str) else ""


def _content_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_$%.]+", text.lower())
        if token not in _STOPWORDS and len(token) > 1
    }


def _answer_presence(text: str) -> int:
    if not text:
        return 0
    if len(text) < 12:
        return 35
    if len(text) < 30:
        return 70
    return 100


def _clarity(text: str) -> int:
    if not text:
        return 0
    length = len(text)
    if length <= 1200:
        return 100
    if length <= 2000:
        return 75
    return 50


def _relevance(question: str, reply: str) -> int:
    if not reply:
        return 0
    q = _content_tokens(question)
    r = _content_tokens(reply)
    if not q:
        return 70
    overlap = len(q & r) / max(1, len(q))
    return min(100, int(45 + overlap * 100))


def _uncertainty(record: dict[str, Any], reply: str) -> int:
    condition = record.get("evidence_condition")
    needs_uncertainty = condition in {"stale", "unavailable", "partial", "ambiguous"}
    if not needs_uncertainty:
        return 100
    lowered = reply.lower()
    return 100 if any(term in lowered for term in _UNCERTAINTY_TERMS) else 20


def _recommendation(record: dict[str, Any], reply: str) -> int:
    if record.get("taxonomy_class") not in {"human_decision", "execution_boundary"}:
        return 100
    lowered = reply.lower()
    return 100 if any(term in lowered for term in _RECOMMENDATION_TERMS) else 25


def _repetition(reply: str) -> int:
    if not reply:
        return 0
    sentences = [
        re.sub(r"\s+", " ", part.strip().lower())
        for part in re.split(r"[.!?]+", reply)
        if part.strip()
    ]
    if len(sentences) < 2:
        return 100
    duplicates = len(sentences) - len(set(sentences))
    if duplicates == 0:
        return 100
    return max(20, 100 - duplicates * 30)


def _internal_leakage(reply: str) -> tuple[int, list[str]]:
    lowered = reply.lower()
    found = [term for term in _INTERNAL_TERMS if term in lowered]
    return (0 if found else 100), found


def grade_human_quality(record: dict[str, Any]) -> dict[str, Any]:
    reply = _reply(record)
    leakage_score, leaked_terms = _internal_leakage(reply)
    scores = {
        "answer_presence": _answer_presence(reply),
        "clarity": _clarity(reply),
        "relevance": _relevance(str(record.get("question", "")), reply),
        "uncertainty_handling": _uncertainty(record, reply),
        "recommendation_presence": _recommendation(record, reply),
        "non_repetition": _repetition(reply),
        "internal_contract_hygiene": leakage_score,
    }
    overall = round(sum(scores.values()) / len(scores), 2)
    return {
        "quality_grader_version": QUALITY_GRADER_VERSION,
        "advisory_only": True,
        "factual_authority": False,
        "record_id": record.get("record_id"),
        "case_id": record.get("case_id"),
        "service": record.get("service"),
        "taxonomy_class": record.get("taxonomy_class"),
        "overall_score": overall,
        "scores": scores,
        "signals": {
            "leaked_internal_terms": leaked_terms,
            "reply_length": len(reply),
        },
    }


def grade_human_quality_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [grade_human_quality(record) for record in records]


def human_quality_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        average = 0.0
    else:
        average = round(
            sum(float(item["overall_score"]) for item in results) / len(results), 2
        )
    return {
        "quality_grader_version": QUALITY_GRADER_VERSION,
        "advisory_only": True,
        "factual_authority": False,
        "result_count": len(results),
        "average_overall_score": average,
        "internal_leakage_count": sum(
            1 for item in results if item["signals"]["leaked_internal_terms"]
        ),
    }


def write_quality(path: Path, results: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
            for result in results
        ),
        encoding="utf-8",
    )
