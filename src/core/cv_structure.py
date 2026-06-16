"""
cv_structure.py — parse a CV plain-text extract into a fixed section/entry blueprint
and enforce that blueprint on optimizer HTML output.

The LLM alone cannot reliably mirror section order (it follows resume "templates").
This module makes structure deterministic: parse once from reading-order text, pass
an explicit blueprint to the optimizer, then strip any extra sections from HTML.
"""

from __future__ import annotations

import re
from typing import Any

# Known CV section keywords — a heading must contain one (avoids matching the
# candidate's ALL-CAPS name in the header block).
_SECTION_KEYWORDS = (
    "SKILLS",
    "EXPERIENCE",
    "EDUCATION",
    "PROJECT",
    "CERTIFICATION",
    "TRAINING",
    "AVAILABILITY",
    "SUMMARY",
    "OBJECTIVE",
    "REFERENCE",
    "AWARD",
    "PUBLICATION",
    "VOLUNTEER",
)

_SECTION_HEADER_RE = re.compile(
    r"^[A-Z][A-Z0-9 &/\-]{2,}$"
)

# Job / project title row: "Company | Role | Jan 2024 – Jul 2025" or "Project | stack | links"
_ENTRY_LINE_RE = re.compile(r"\s\|\s")

# Experience rows usually contain a month/year date range.
_DATE_RANGE_RE = re.compile(
    r"\b("
    r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
    r"|\d{4}"
    r")\s*[–\-]\s*("
    r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
    r"|\d{4}"
    r")\b",
    re.IGNORECASE,
)

# Project rows often include demo/repo link labels.
_PROJECT_LINK_RE = re.compile(r"\[(?:GitHub|Live)\s*Link\]", re.IGNORECASE)

# Labelled skill row: "Languages: Python, …"
_SKILL_LINE_RE = re.compile(r"^[A-Za-z0-9 &/+\-]+:\s+\S")

# Common sections the model invents when not present in source CV.
_COMMON_INVENTED_SECTIONS = frozenset(
    {
        "TRAINING & CERTIFICATIONS",
        "TRAINING AND CERTIFICATIONS",
        "TRAINING",
        "CERTIFICATIONS",
        "AVAILABILITY",
        "SUMMARY",
        "PROFESSIONAL SUMMARY",
        "OBJECTIVE",
        "REFERENCES",
    }
)


def _normalize_heading(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().upper())


def _is_section_header(line: str) -> bool:
    s = line.strip()
    if len(s) < 4:
        return False
    if not _SECTION_HEADER_RE.match(s):
        return False
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    upper = sum(c.isupper() for c in letters)
    if upper / len(letters) < 0.85:
        return False
    upper_s = s.upper()
    return any(kw in upper_s for kw in _SECTION_KEYWORDS)


def _append_bullet(entry: dict[str, Any], line: str) -> None:
    """Append a bullet, merging PDF line-wrap continuations into the previous bullet."""
    bullets: list[str] = entry.setdefault("bullets", [])
    if not bullets:
        bullets.append(line)
        return
    prev = bullets[-1]
    if not prev.rstrip().endswith((".", ";", ":", "!", "?")) or (
        line and line[0].islower()
    ):
        bullets[-1] = prev + " " + line
    else:
        bullets.append(line)


def _is_entry_line(line: str, *, current_section: str) -> bool:
    """True if this line starts a job/project/experience block."""
    s = line.strip()
    if not _ENTRY_LINE_RE.search(s):
        return False
    if _SKILL_LINE_RE.match(s):
        return False

    section = _normalize_heading(current_section)

    if section == "ENGINEERING PROJECTS":
        # Under projects: title rows with stack and/or link labels (usually no date range).
        if _PROJECT_LINK_RE.search(s):
            return True
        if not _DATE_RANGE_RE.search(s):
            return True

    if section == "PROFESSIONAL EXPERIENCE":
        # Under experience: rows with a date range, or company | role pattern without project links.
        if _DATE_RANGE_RE.search(s):
            return True
        if _PROJECT_LINK_RE.search(s):
            return False
        return True

    # Education / other: single-line entries with pipes are rare; treat conservatively.
    if section == "EDUCATION" and _DATE_RANGE_RE.search(s):
        return True

    return False


def parse_cv_structure(cv_text: str) -> dict[str, Any]:
    """
    Parse reading-order CV text into header + ordered sections + entries + bullets.

    Returns:
        {
          "header_lines": [...],
          "sections": [
            {"heading": "TECHNICAL SKILLS", "skill_lines": [...], "entries": []},
            {"heading": "ENGINEERING PROJECTS", "skill_lines": [], "entries": [
                {"title_line": "...", "bullets": [...]},
            ]},
            ...
          ],
          "forbidden_sections": ["TRAINING & CERTIFICATIONS", ...],
        }
    """
    lines = [ln.strip() for ln in cv_text.splitlines() if ln.strip()]

    header_lines: list[str] = []
    sections: list[dict[str, Any]] = []
    current_section: dict[str, Any] | None = None
    current_entry: dict[str, Any] | None = None

    def _flush_entry() -> None:
        nonlocal current_entry
        if current_section is not None and current_entry is not None:
            current_section["entries"].append(current_entry)
        current_entry = None

    def _flush_section() -> None:
        nonlocal current_section
        _flush_entry()
        if current_section is not None:
            sections.append(current_section)
        current_section = None

    for line in lines:
        if _is_section_header(line):
            _flush_section()
            current_section = {
                "heading": line.strip(),
                "skill_lines": [],
                "entries": [],
            }
            continue

        if current_section is None:
            header_lines.append(line)
            continue

        heading_norm = _normalize_heading(current_section["heading"])

        if heading_norm == "TECHNICAL SKILLS":
            if _SKILL_LINE_RE.match(line) or not current_section["skill_lines"]:
                current_section["skill_lines"].append(line)
            else:
                current_section["skill_lines"][-1] += " " + line
            continue

        if _is_entry_line(line, current_section=current_section["heading"]):
            _flush_entry()
            current_entry = {"title_line": line, "bullets": []}
            continue

        if current_entry is not None:
            _append_bullet(current_entry, line)
        elif heading_norm == "EDUCATION":
            if not current_section["entries"]:
                current_section["entries"].append({"title_line": line, "bullets": []})
            else:
                last = current_section["entries"][-1]
                if last["bullets"]:
                    _append_bullet(last, line)
                else:
                    last["bullets"] = [line]
        elif current_section["entries"]:
            last = current_section["entries"][-1]
            if last["bullets"]:
                _append_bullet(last, line)
            else:
                last["title_line"] = last["title_line"] + " " + line

    _flush_section()

    present = {_normalize_heading(s["heading"]) for s in sections}
    forbidden = sorted(
        s for s in _COMMON_INVENTED_SECTIONS if s not in present
    )

    return {
        "header_lines": header_lines,
        "sections": sections,
        "forbidden_sections": forbidden,
    }


def format_structure_blueprint(structure: dict[str, Any]) -> str:
    """Human-readable blueprint the optimizer MUST follow."""
    out: list[str] = [
        "STRUCTURE BLUEPRINT (mandatory — your HTML must match this exactly):",
        "",
        "HEADER (no <h2> — use <h1> + contact lines only):",
    ]
    for ln in structure.get("header_lines") or []:
        out.append(f"  - {ln}")

    for idx, sec in enumerate(structure.get("sections") or [], 1):
        heading = sec["heading"]
        out.append("")
        out.append(f'Section {idx}: <h2>{heading}</h2>')
        for skill in sec.get("skill_lines") or []:
            out.append(f"  skill-line: {skill}")
        for e_idx, entry in enumerate(sec.get("entries") or [], 1):
            out.append(f"  Entry {e_idx} title (keep in this section): {entry['title_line']}")
            bullets = entry.get("bullets") or []
            out.append(f"    bullets: exactly {len(bullets)} (rephrase only, do not add/remove)")
            for b in bullets:
                out.append(f"      • {b[:120]}{'…' if len(b) > 120 else ''}")

    forbidden = structure.get("forbidden_sections") or []
    if forbidden:
        out.append("")
        out.append("FORBIDDEN — do NOT add these sections (not in original CV):")
        for name in forbidden:
            out.append(f"  - {name}")

    out.append("")
    out.append(
        "RULE: Copy this blueprint's section order, section names, entry placement, "
        "and bullet counts. Optimise wording only."
    )
    return "\n".join(out)


def allowed_section_headings(structure: dict[str, Any]) -> set[str]:
    return {_normalize_heading(s["heading"]) for s in structure.get("sections") or []}


def enforce_cv_structure(html: str, structure: dict[str, Any]) -> str:
    """
    Remove <h2> sections from HTML that are not in the parsed original CV.
    Strips common invented blocks (Training, Availability, etc.).
    """
    allowed = allowed_section_headings(structure)
    if not allowed:
        return html

    # Split on h2 tags (case-insensitive).
    parts = re.split(r"(?is)(<h2[^>]*>.*?</h2>)", html)
    if len(parts) <= 1:
        return html

    kept: list[str] = [parts[0]]
    i = 1
    while i < len(parts):
        h2_block = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        i += 2

        inner = re.sub(r"(?is)<h2[^>]*>(.*?)</h2>", r"\1", h2_block)
        inner_clean = re.sub(r"<[^>]+>", "", inner)
        heading = _normalize_heading(inner_clean)

        if heading in allowed:
            kept.append(h2_block)
            kept.append(body)
        # else: drop invented section (h2 + body)

    return "".join(kept)
