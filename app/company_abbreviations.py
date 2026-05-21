from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re


@dataclass(frozen=True)
class CompanyAbbreviation:
    name: str
    abbreviation: str


_DATA_PATH = Path(__file__).with_name("company_abbreviations.csv")
_DROP_WORDS = {"company", "comp", "co", "inc", "llc", "ltd"}


def _normalize(value: str) -> str:
    text = value.lower().replace("&", " and ")
    text = re.sub(r"\bgcc\b", "golf country club", text)
    text = re.sub(r"\bone\b", "1", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _without_drop_words(value: str) -> str:
    tokens = [token for token in _normalize(value).split() if token not in _DROP_WORDS]
    return " ".join(tokens)


def _candidate_names(value: str) -> list[str]:
    if ">" in value:
        parts = [part.strip() for part in value.split(">") if part.strip()]
        return list(reversed(parts)) + [value]
    return [value] if value.strip() else []


@lru_cache(maxsize=1)
def _entries() -> tuple[CompanyAbbreviation, ...]:
    if not _DATA_PATH.exists():
        return ()
    with _DATA_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return tuple(
            CompanyAbbreviation(
                name=(row.get("Company Name") or "").strip(),
                abbreviation=(row.get("Abbrv") or "").strip(),
            )
            for row in reader
            if (row.get("Company Name") or "").strip() and (row.get("Abbrv") or "").strip()
        )


@lru_cache(maxsize=1)
def _exact_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for entry in _entries():
        for key in {_normalize(entry.name), _without_drop_words(entry.name)}:
            if key:
                index[key] = entry.abbreviation
    return index


def company_abbreviation(company_name: str) -> str:
    sorted_entries = sorted(_entries(), key=lambda entry: len(_normalize(entry.name)), reverse=True)
    for candidate in _candidate_names(company_name):
        candidate_keys = [key for key in (_normalize(candidate), _without_drop_words(candidate)) if key]
        for key in candidate_keys:
            if key and key in _exact_index():
                return _exact_index()[key]
        for entry in sorted_entries:
            entry_keys = {_normalize(entry.name), _without_drop_words(entry.name)}
            if any(key and any(key in candidate_key or candidate_key in key for candidate_key in candidate_keys) for key in entry_keys):
                return entry.abbreviation
    return ""


def company_full_name(company_name_or_abbreviation: str) -> str:
    text = str(company_name_or_abbreviation or "").strip()
    if not text:
        return ""
    sorted_entries = sorted(_entries(), key=lambda entry: len(_normalize(entry.name)), reverse=True)
    for entry in sorted_entries:
        if text.lower() == entry.abbreviation.lower():
            return entry.name
    for candidate in _candidate_names(text):
        candidate_keys = [key for key in (_normalize(candidate), _without_drop_words(candidate)) if key]
        for entry in sorted_entries:
            entry_keys = {_normalize(entry.name), _without_drop_words(entry.name)}
            if any(key and key in entry_keys for key in candidate_keys):
                return entry.name
        for entry in sorted_entries:
            entry_keys = {_normalize(entry.name), _without_drop_words(entry.name)}
            if any(key and any(key in candidate_key or candidate_key in key for candidate_key in candidate_keys) for key in entry_keys):
                return entry.name
    return text


def abbreviate_company(company_name: str) -> str:
    text = str(company_name or "").strip()
    if not text:
        return ""
    return company_abbreviation(text) or text
