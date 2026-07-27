import re
from typing import Iterable

_SECTION_ID_RE = re.compile(r"(?i)section\s+(\d+(?:\.\d+)*)")


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def extract_clause_ids(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    return _dedupe_preserve_order(match.group(1) for match in _SECTION_ID_RE.finditer(value))


def derive_cited_clause_ids(cited_clauses: object) -> list[str]:
    if not isinstance(cited_clauses, list):
        return []
    ids: list[str] = []
    for clause in cited_clauses:
        ids.extend(extract_clause_ids(clause))
    return _dedupe_preserve_order(ids)


def extract_rag_clause_ids(policy_results: object) -> list[str]:
    if not isinstance(policy_results, list):
        return []
    ids: list[str] = []
    for result in policy_results:
        if not isinstance(result, dict):
            continue
        ids.extend(extract_clause_ids(result.get("section")))
        ids.extend(extract_clause_ids(result.get("text")))
    return _dedupe_preserve_order(ids)
