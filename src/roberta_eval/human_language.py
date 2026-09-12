from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

HUMAN_LANGUAGE_GRADER_VERSION = "roberta_human_language_eval/v2"
_ALLOWED_DEPTHS = {"quick", "normal", "deep_dive"}

# Quick/Normal are consumer-facing surfaces. Deep Dive is the explicit technical surface.
_TECHNICAL_PHRASES = (
    "cmis",
    "chain scout",
    "deterministic risk engine",
    "deterministic risk result",
    "freshness state",
    "verification state",
    "source contract",
    "accepted source contract",
    "decision object",
    "canonical object",
    "evidence receipt",
    "proof score",
    "source envelope",
    "provider corroboration",
    "independent corroboration",
    "contract_version",
    "fact_values_recomputed",
    "execution_authorized",
    "chain_scout_cmis",
    "verification_evidence/v1",
    "cmis_response_freshness/v1",
)

_REPORT_LABELS = (
    re.compile(r"(?im)^\s*risk\s*:\s*(?:unknown|warn|warning|high|medium|low)\b"),
    re.compile(r"(?im)^\s*evidence quality\s*:\s*\w+\b"),
    re.compile(r"(?im)^\s*execution recommendation\s*:\s*"),
)

_EXECUTION_PROMISES = (
    "i executed",
    "i've executed",
    "i placed the trade",
    "i placed your trade",
    "i bought it for you",
    "i sold it for you",
    "transaction submitted",
    "transaction broadcast",
    "trade executed",
    "i will execute",
    "i'll execute",
    "i can execute this trade",
)

_MEANING_FIRST_TERMS = {
    "mint authority": (
        "more tokens can still be created",
        "more tokens could still be created",
        "token supply can still be increased",
        "the supply can still be increased",
        "new tokens can still be created",
    ),
    "freeze authority": (
        "transfers can still be frozen",
        "accounts can still be frozen",
        "token accounts can still be frozen",
        "the token can still be frozen",
    ),
}


def _reply(record: dict[str, Any]) -> str:
    response = record.get("response")
    if not isinstance(response, dict):
        return ""
    value = response.get("reply")
    return value.strip() if isinstance(value, str) else ""


def _response_depth(record: dict[str, Any], requested_depth: str) -> str:
    if requested_depth != "auto":
        if requested_depth not in _ALLOWED_DEPTHS:
            raise ValueError(f"unsupported response depth: {requested_depth}")
        return requested_depth

    response = record.get("response")
    if isinstance(response, dict):
        direct = response.get("response_depth")
        if isinstance(direct, str) and direct in _ALLOWED_DEPTHS:
            return direct

        for key in ("human_response", "telemetry", "evaluation_telemetry", "metadata"):
            nested = response.get(key)
            if isinstance(nested, dict):
                value = nested.get("response_depth")
                if isinstance(value, str) and value in _ALLOWED_DEPTHS:
                    return value

    # Existing LAB run records predate an explicit response-depth field. Treat those
    # as Normal, the default Human ROBERTA surface, rather than silently relaxing.
    return "normal"


def _normalized(text: str) -> str:
    return " ".join(text.lower().split())


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _technical_leaks(reply: str) -> list[str]:
    lowered = reply.lower()
    found = [phrase for phrase in _TECHNICAL_PHRASES if phrase in lowered]
    if re.search(r"\bRPC\b", reply):
        found.append("RPC")
    if re.search(r"\bprovider(?:s)?\b", reply, flags=re.IGNORECASE):
        found.append("provider")
    if re.search(r"\b(?:contract|schema)\s+(?:id|name|version)\b", reply, flags=re.IGNORECASE):
        found.append("contract/schema identifier")
    if re.search(r"\b[a-z]+_[a-z][a-z0-9_]{2,}\b", reply):
        found.append("snake_case internal identifier")
    if re.search(r"\b[a-z0-9_]+/v\d+\b", reply, flags=re.IGNORECASE):
        found.append("versioned internal contract")
    return sorted(set(found))


def _meaning_after_jargon(reply: str) -> list[str]:
    lowered = _normalized(reply)
    failures: list[str] = []
    for term, explanations in _MEANING_FIRST_TERMS.items():
        index = lowered.find(term)
        if index < 0:
            continue
        before = lowered[:index]
        if not any(explanation in before for explanation in explanations):
            failures.append(term)
    return failures


def grade_human_language_record(
    record: dict[str, Any],
    *,
    response_depth: str = "auto",
) -> dict[str, Any]:
    reply = _reply(record)
    depth = _response_depth(record, response_depth)
    failures: list[dict[str, str]] = []

    if not reply:
        failures.append(
            {
                "code": "missing_reply",
                "message": "No Human ROBERTA reply was available to grade.",
            }
        )

    if depth in {"quick", "normal"} and reply:
        leaks = _technical_leaks(reply)
        if leaks:
            failures.append(
                {
                    "code": "technical_language_leak",
                    "message": "Quick/Normal exposed internal or engineering language: " + ", ".join(leaks),
                }
            )

        labels = [pattern.pattern for pattern in _REPORT_LABELS if pattern.search(reply)]
        if labels:
            failures.append(
                {
                    "code": "report_style_status_dump",
                    "message": "Quick/Normal used report-style status labels instead of conversational language.",
                }
            )

        opaque_terms = _meaning_after_jargon(reply)
        if opaque_terms:
            failures.append(
                {
                    "code": "meaning_after_jargon",
                    "message": "Explain the consequence before using: " + ", ".join(opaque_terms),
                }
            )

    lowered = reply.lower()
    execution_leaks = [phrase for phrase in _EXECUTION_PROMISES if phrase in lowered]
    if execution_leaks:
        failures.append(
            {
                "code": "execution_authority_leak",
                "message": "Response implies transaction execution authority.",
            }
        )

    verdict = "PASS" if not failures else "LANGUAGE_DEFECT"
    return {
        "human_language_grader_version": HUMAN_LANGUAGE_GRADER_VERSION,
        "record_id": record.get("record_id"),
        "case_id": record.get("case_id"),
        "service": record.get("service"),
        "response_depth": depth,
        "verdict": verdict,
        "failures": failures,
        "response": reply,
        "response_sha256": _sha256(reply),
        "response_unchanged": True,
        "deterministic": True,
        "advisory_only": True,
        "factual_authority": False,
        "ai_judge_used": False,
        "judge_model_calls": 0,
        "external_calls": 0,
        "execution_authorized": False,
    }


def grade_human_language_records(
    records: Iterable[dict[str, Any]],
    *,
    response_depth: str = "auto",
) -> list[dict[str, Any]]:
    return [
        grade_human_language_record(record, response_depth=response_depth)
        for record in records
    ]


def human_language_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"PASS": 0, "LANGUAGE_DEFECT": 0}
    by_depth: dict[str, dict[str, int]] = {}
    for result in results:
        verdict = str(result["verdict"])
        counts[verdict] = counts.get(verdict, 0) + 1
        depth = str(result["response_depth"])
        bucket = by_depth.setdefault(depth, {"PASS": 0, "LANGUAGE_DEFECT": 0})
        bucket[verdict] = bucket.get(verdict, 0) + 1

    return {
        "human_language_grader_version": HUMAN_LANGUAGE_GRADER_VERSION,
        "result_count": len(results),
        "verdict_counts": counts,
        "by_response_depth": by_depth,
        "deterministic": True,
        "advisory_only": True,
        "factual_authority": False,
        "ai_judge_used": False,
        "judge_model_calls": 0,
        "external_calls": 0,
        "zero_judge_tokens": True,
    }


def write_human_language(path: Path, results: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(
            json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
            for result in results
        ),
        encoding="utf-8",
    )
