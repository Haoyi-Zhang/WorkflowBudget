#!/usr/bin/env python3
"""Offline bibliography and citation consistency checks.

This checker deliberately does not use the network.  The dated verification
ledger records the scholarly/publisher records inspected during manuscript
preparation; this program checks that the delivered BibTeX, paper citations,
calibration sets, and mirrored files still agree with that frozen ledger.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Dict, Iterable, Tuple

EXPECTED_COUNT = 69
CHECKED_ON = {"2026-09-16", "2026-09-17", "2026-09-19", "2026-10-06"}

CORRECTED_DOIS = {
    "li2025encompass": "10.52202/085713-3533",
    "hanus2020memoized": "10.1007/978-3-030-75333-7_4",
    "hanus2026monadic": "10.1017/S1471068426100453",
    "antoy2011pulltabbing": "10.1017/S1471068411000263",
    "papadimitriou1984facet": "10.1016/0022-0000(84)90068-0",
    "godefroid1991partial": "10.1007/3-540-55179-4_32",
}

KNOWN_BAD_IDENTIFIERS = {
    "10.4204/eptcs.332.1",
    "10.1145/2003476.2003477",
    "10.1016/0022-0000(84)90012-3",
    "10.48550/arxiv.2512.03571",
    "10.48550/arxiv.2604.27863",
    "10.1007/3-540-55179-4_30",
}

TOPLAS_KEYS = {
    "banerjee2023relational", "inverso2022bounded", "abate2021trace",
    "reps2010finite", "jeannet2010relational", "kalvala2009transformations",
    "tardieu2007esterel", "botincan2013parallelization",
    "giacobazzi1998logical", "jagadeesan1991fully",
    "clarke1986automatic", "paige1982finite",
}
INFLUENTIAL_KEYS = {
    "bryant1986graph", "cousot1977abstract", "barthe2011product",
    "godefroid1996partial", "necula1997pcc",
}
ADJACENT_KEYS = {
    "li2025encompass", "hanus2020memoized", "hanus2026monadic",
    "schrijvers2013search", "pous2015symbolic",
}


def _balanced_value(text: str, pos: int) -> Tuple[str, int]:
    """Parse a BibTeX value beginning at *pos* and return value/end position."""
    if pos >= len(text):
        raise ValueError("missing BibTeX value")
    if text[pos] == "{":
        depth, i = 1, pos + 1
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        if depth:
            raise ValueError("unclosed BibTeX brace")
        return text[pos + 1:i - 1].strip(), i
    if text[pos] == '"':
        i, escaped = pos + 1, False
        while i < len(text):
            ch = text[i]
            if ch == '"' and not escaped:
                return text[pos + 1:i].strip(), i + 1
            escaped = ch == "\\" and not escaped
            if ch != "\\":
                escaped = False
            i += 1
        raise ValueError("unclosed BibTeX quote")
    i = pos
    while i < len(text) and text[i] not in ",\n":
        i += 1
    return text[pos:i].strip(), i


def parse_bib(path: Path) -> Dict[str, dict]:
    text = path.read_text(encoding="utf-8")
    entries: Dict[str, dict] = {}
    pos = 0
    header = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.I)
    while True:
        match = header.search(text, pos)
        if not match:
            break
        entry_type, key = match.group(1).lower(), match.group(2)
        i, depth = match.end(), 1
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        if depth:
            raise ValueError(f"unclosed entry {key}")
        body = text[match.end():i - 1]
        fields: Dict[str, str] = {}
        j = 0
        while j < len(body):
            while j < len(body) and (body[j].isspace() or body[j] == ","):
                j += 1
            if j >= len(body):
                break
            fm = re.match(r"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*", body[j:])
            if not fm:
                raise ValueError(f"cannot parse field in {key} near {body[j:j+40]!r}")
            name = fm.group(1).lower()
            j += fm.end()
            value, j = _balanced_value(body, j)
            fields[name] = value
        if key in entries:
            raise ValueError(f"duplicate BibTeX key {key}")
        entries[key] = {"type": entry_type, **fields}
        pos = i
    return entries


def _strip_tex_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        match = re.search(r"(?<!\\)%", line)
        lines.append(line[:match.start()] if match else line)
    return "\n".join(lines)


def cited_keys(paths: Iterable[Path]) -> set[str]:
    out: set[str] = set()
    pattern = re.compile(
        r"\\cite(?!style)[a-zA-Z*]*\s*(?:\[[^\]]*\]\s*){0,2}\{([^}]*)\}", re.S
    )
    for path in paths:
        text = _strip_tex_comments(path.read_text(encoding="utf-8"))
        for group in pattern.findall(text):
            out.update(key.strip() for key in group.split(",") if key.strip())
    return out


def fail(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--paper-dir", type=Path,
        help="also verify the paper's BibTeX mirror and all LaTeX citations",
    )
    parser.add_argument(
        "--no-write", action="store_true",
        help="perform all checks without changing results/reference-checks.json",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    bib_path = root / "docs" / "references.bib"
    audit_path = root / "results" / "reference-audit.csv"
    output_path = root / "results" / "reference-checks.json"

    entries = parse_bib(bib_path)
    fail(len(entries) == EXPECTED_COUNT,
         f"expected {EXPECTED_COUNT} bibliography entries, found {len(entries)}")
    fail(all("title" in e and ("author" in e or "editor" in e) and "year" in e
             for e in entries.values()),
         "every entry must have author/editor, title, and year")

    for key, entry in entries.items():
        if entry.get("articleno"):
            fail(bool(entry.get("numpages")),
                 f"article-number record lacks numpages: {key}")

    dois = {key: entry.get("doi", "").strip() for key, entry in entries.items()}
    doi_values = [value.lower() for value in dois.values() if value]
    fail(len(doi_values) == len(set(doi_values)), "duplicate DOI in bibliography")
    fail(not (set(doi_values) & KNOWN_BAD_IDENTIFIERS),
         "a known-invalid or misassigned DOI remains in the bibliography")
    for key, expected in CORRECTED_DOIS.items():
        fail(dois.get(key, "").lower() == expected.lower(),
             f"{key} must use corrected DOI {expected}")

    with audit_path.open(newline="", encoding="utf-8") as handle:
        audit_rows = list(csv.DictReader(handle))
    required_columns = {
        "bibkey", "entry_type", "creators", "title", "venue", "locator", "year",
        "identifier_kind", "identifier", "record_url", "verification_basis",
        "checked_on", "notes",
    }
    fail(set(audit_rows[0]) == required_columns, "reference audit columns changed")
    fail(len(audit_rows) == EXPECTED_COUNT,
         f"reference audit must contain {EXPECTED_COUNT} rows")
    audit_by_key = {row["bibkey"]: row for row in audit_rows}
    fail(len(audit_by_key) == EXPECTED_COUNT, "duplicate key in reference audit")
    fail(set(audit_by_key) == set(entries), "reference audit/BibTeX key mismatch")
    for key, entry in entries.items():
        row = audit_by_key[key]
        fail(row["entry_type"] == entry["type"], f"entry type mismatch for {key}")
        creators = entry.get("author", entry.get("editor", ""))
        venue = entry.get("journal", entry.get("booktitle", entry.get("publisher", entry.get("institution", ""))))
        locator = "; ".join(
            f"{name}={entry[name]}" for name in
            ("volume", "number", "articleno", "pages", "numpages") if entry.get(name)
        )
        fail(row["creators"] == creators, f"creator mismatch for {key}")
        fail(row["title"] == entry["title"], f"title mismatch for {key}")
        fail(row["venue"] == venue, f"venue mismatch for {key}")
        fail(row["locator"] == locator, f"locator mismatch for {key}")
        fail(row["year"] == entry["year"], f"year mismatch for {key}")
        fail(row["checked_on"] in CHECKED_ON, f"unexpected audit date for {key}")
        if entry.get("doi"):
            fail(row["identifier_kind"] == "DOI", f"DOI row mislabeled for {key}")
            fail(row["identifier"].lower() == entry["doi"].lower(),
                 f"audit DOI mismatch for {key}")
            fail(row["record_url"].lower() == "https://doi.org/" + entry["doi"].lower(),
                 f"audit DOI URL mismatch for {key}")
        else:
            fail(row["identifier_kind"] != "DOI", f"non-DOI row mislabeled for {key}")
            fail(row["record_url"].startswith("https://"),
                 f"non-DOI row lacks stable HTTPS record for {key}")

    calibration = {
        "toplas": TOPLAS_KEYS,
        "influential": INFLUENTIAL_KEYS,
        "adjacent": ADJACENT_KEYS,
    }
    fail(len(TOPLAS_KEYS) == 12 and len(INFLUENTIAL_KEYS) == 5 and len(ADJACENT_KEYS) == 5,
         "calibration quota constants are malformed")
    fail(all(keys <= set(entries) for keys in calibration.values()),
         "calibration key missing from bibliography")

    cited: set[str] = set()
    if args.paper_dir:
        paper_dir = args.paper_dir.resolve()
        paper_bib = paper_dir / "references.bib"
        fail(paper_bib.read_bytes() == bib_path.read_bytes(),
             "paper and artifact BibTeX files differ")
        tex_files = sorted(paper_dir.glob("*.tex"))
        cited = cited_keys(tex_files)
        fail(cited == set(entries),
             "paper citations and bibliography differ: "
             f"uncited={sorted(set(entries)-cited)}, missing={sorted(cited-set(entries))}")

    summary = {
        "all_succeeded": True,
        "checked_on": sorted({row["checked_on"] for row in audit_rows}),
        "bibliography_entries": len(entries),
        "doi_backed_entries": len(doi_values),
        "stable_non_doi_entries": len(entries) - len(doi_values),
        "unique_dois": len(set(doi_values)),
        "audit_rows": len(audit_rows),
        "paper_cited_entries": len(cited) if args.paper_dir else None,
        "toplas_calibration_entries": len(TOPLAS_KEYS),
        "influential_calibration_entries": len(INFLUENTIAL_KEYS),
        "adjacent_calibration_entries": len(ADJACENT_KEYS),
        "scope": (
            "Offline consistency against the dated verification ledger; "
            "not live DOI resolution or an exhaustive novelty search."
        ),
    }
    if not args.no_write:
        output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
