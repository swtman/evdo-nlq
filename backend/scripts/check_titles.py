"""check_titles — offline grounding check on the title eval set (ADR-034). No LLM, no GraphDB.

WHAT IT MEASURES
----------------
For every item of ``prompts/eval-titles-grounding.yaml`` (built by S43) it runs the production
``build_grounding_hints`` on the question and reads the hint block the LLM would receive:

  named / one-word-cued   the question NAMES a title (``expected_titles``, title_key norms):
      found      — the expected title is among the "Title candidates" lines of its class
      top-1      — it is the FIRST candidate line of its class
      wrong class — it appears only under the other class ([Book] for a course, …)
  harder questions        a title among other words (user, 2026-09-26):
      long                — + department and university: also ``entities_ok`` (the department line
                            with that label lists the named university; the university line)
      two-titles          — ``found_all`` (both titles) next to found (at least one)
      title+topic         — also ``stems_ok`` for the topic words
      numbered-in-context — top-1 must be the exact numbered variant; university found
      partial             — a shortened title: found only (several titles may fit)
  nonexistent             a plausible title that is not in the KG:
      false candidate — any title candidate appears (it can only be a wrong one)
  topic-control / one-word-topic   the words DESCRIBE a topic (decision 1):
      false candidate — a title candidate appears anyway (allowed by v8, but a cost)
      stems ok        — every topic word's stem is in the "Topic stems" lines

WHY A SEPARATE CHECKER (and not eval.py)
----------------------------------------
Grounding can be measured for free and deterministically; eval.py needs the LLM and GraphDB. Branches
6–9 change title linking — this is the number they must move, on DEV only (decision 3: tune on dev,
look at test once at the end). The default split is therefore ``dev``.

Usage (from backend/):
    uv run python scripts/check_titles.py                  # dev split, report to notes/eval-runs/
    uv run python scripts/check_titles.py --split test     # only at the very end (decision 3)
    uv run python scripts/check_titles.py --split all --output path.md
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Allow running from backend/ with: uv run python scripts/check_titles.py
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

from app.grounding import db as grounding_db
from app.grounding.hints import build_grounding_hints
from app.grounding.normalize import title_key
from app.grounding.stem import MIN_STEM_LEN, topic_stem

logging.disable(logging.CRITICAL)  # the grounding module logs every input/output at INFO

_REPO_ROOT = Path(__file__).parent.parent.parent
_DEFAULT_FILE = _REPO_ROOT / "prompts" / "eval-titles-grounding.yaml"
_EVAL_RUNS_DIR = _REPO_ROOT / "notes" / "eval-runs"

_TITLE_LINE = re.compile(r'^- \[(Course|Book)\] (".*")$')
_STEM_LINE = re.compile(r"^- (\S+) → ")
_UNIVERSITY_LINE = re.compile(r"^- \[University\] (.+)$")
_DEPARTMENT_LINE = re.compile(r"^- \[Department @ (.+?)\] (.+)$")
NAMED_KINDS = ("named", "one-word-cued")
# Harder questions (user, 2026-09-26): the question names one or two titles among other words.
HARDER_KINDS = ("long", "two-titles", "title+topic", "numbered-in-context", "partial")
TITLE_KINDS = NAMED_KINDS + HARDER_KINDS


def parse_hint(hint: str) -> dict[str, list]:
    """Title-candidate norms per class (in line order), topic stems and entities of a hint block.

    A candidate line lists several spellings of ONE title (``"A" | "B"``); all map to the
    same ``title_key`` norm, so each line becomes one norm. Department lines keep their
    universities (``[Department @ U1 | U2] LABEL``, ADR-028).
    """
    parsed: dict[str, list] = {
        "course": [],
        "book": [],
        "stems": [],
        "universities": [],
        "departments": [],
    }
    for line in hint.splitlines():
        m = _TITLE_LINE.match(line)
        if m:
            first = m.group(2).split('" | "')[0].strip('"')
            parsed[m.group(1).lower()].append(title_key(first))
            continue
        m = _STEM_LINE.match(line)
        if m:
            parsed["stems"].append(m.group(1))
            continue
        m = _UNIVERSITY_LINE.match(line)
        if m:
            parsed["universities"].append(m.group(1))
            continue
        m = _DEPARTMENT_LINE.match(line)
        if m:
            parsed["departments"].append((m.group(2), m.group(1).split(" | ")))
    return parsed


def _entity_found(expected: dict[str, str], parsed: dict[str, list]) -> bool:
    """A university by its line; a department only if its line lists the named university."""
    if expected["type"] == "university":
        return expected["label"] in parsed["universities"]
    return any(
        label == expected["label"] and expected["university"] in unis
        for label, unis in parsed["departments"]
    )


def score_item(item: dict[str, Any], hint: str) -> dict[str, Any]:
    """Score one eval item against the hint block built for its question (pure function)."""
    parsed = parse_hint(hint)
    own = parsed[item["class"]]
    other = parsed["book" if item["class"] == "course" else "course"]
    any_candidate = bool(parsed["course"] or parsed["book"])
    score: dict[str, Any] = {
        "id": item["id"],
        "kind": item["kind"],
        "split": item["split"],
        "stratum": item.get("stratum", ""),
        "phrasing": item.get("phrasing", ""),
        "candidates": len(parsed["course"]) + len(parsed["book"]),
    }
    if item["kind"] in TITLE_KINDS:
        expected = set(item["expected_titles"])
        score["found"] = bool(expected & set(own))  # any of them (two-titles: at least one)
        score["found_all"] = expected <= set(own)
        score["top1"] = bool(own) and own[0] in expected
        score["wrong_class"] = not score["found"] and bool(expected & set(other))
        if item.get("expected_entities"):
            score["entities_ok"] = all(_entity_found(x, parsed) for x in item["expected_entities"])
    else:
        score["false_candidate"] = any_candidate
    if item.get("topic_words"):
        wanted = [topic_stem(w) for w in item["topic_words"]]
        wanted = [s for s in wanted if len(s) >= MIN_STEM_LEN]
        score["stems_ok"] = all(s in parsed["stems"] for s in wanted)
    return score


def _rate(rows: list[dict], key: str) -> str:
    hits = sum(bool(r[key]) for r in rows)
    return f"{hits}/{len(rows)} = {hits / len(rows):.0%}" if rows else "–"


def summarize(scores: list[dict]) -> list[str]:
    """Markdown tables: named items overall / by stratum / by phrasing; controls."""
    named = [s for s in scores if s["kind"] in NAMED_KINDS]
    lines = [
        "## Named titles (the question names a course/book)",
        "",
        "| group | n | found | top-1 | only under the other class |",
        "|---|---|---|---|---|",
    ]

    def row(label: str, group: list[dict]) -> None:
        lines.append(
            f"| {label} | {len(group)} | {_rate(group, 'found')} | {_rate(group, 'top1')} | "
            f"{_rate(group, 'wrong_class')} |"
        )

    row("**all named**", named)
    for key in ("kind", "stratum", "phrasing"):
        groups: dict[str, list[dict]] = defaultdict(list)
        for s in named:
            groups[s[key]].append(s)
        for label in sorted(groups):
            row(f"{key}: {label}", groups[label])
    lines += [
        "",
        "## Harder questions (a title among other words)",
        "",
        "| kind | n | found | all titles found | top-1 | entities found | topic stems |",
        "|---|---|---|---|---|---|---|",
    ]
    for kind in HARDER_KINDS:
        group = [s for s in scores if s["kind"] == kind]
        if not group:
            continue
        with_ent = [s for s in group if "entities_ok" in s]
        with_stems = [s for s in group if "stems_ok" in s]
        lines.append(
            f"| {kind} | {len(group)} | {_rate(group, 'found')} | "
            f"{_rate(group, 'found_all') if kind == 'two-titles' else '–'} | "
            f"{'–' if kind == 'partial' else _rate(group, 'top1')} | "
            f"{_rate(with_ent, 'entities_ok') if with_ent else '–'} | "
            f"{_rate(with_stems, 'stems_ok') if with_stems else '–'} |"
        )
    lines += [
        "",
        "## Controls (no title should be bound)",
        "",
        "| kind | n | a title candidate appears | topic stems present |",
        "|---|---|---|---|",
    ]
    for kind in ("nonexistent", "topic-control", "one-word-topic"):
        group = [s for s in scores if s["kind"] == kind]
        with_stems = [s for s in group if "stems_ok" in s]
        lines.append(
            f"| {kind} | {len(group)} | {_rate(group, 'false_candidate')} | "
            f"{_rate(with_stems, 'stems_ok') if with_stems else '–'} |"
        )
    return lines


def _provenance(path: Path) -> list[str]:
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--", "backend/app"],
            cwd=_REPO_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        sha, dirty = "unknown", ""
    db_path = grounding_db.DB_PATH
    conn = grounding_db.get_connection()
    try:
        snapshot = dict(conn.execute("SELECT key, value FROM meta").fetchall()).get("snapshot", "?")
    finally:
        conn.close()
    return [
        "| Field | Value |",
        "|---|---|",
        f"| git HEAD | `{sha}`{' + uncommitted backend/app changes' if dirty else ''} |",
        f"| {path.name} sha256[:12] | `{hashlib.sha256(path.read_bytes()).hexdigest()[:12]}` |",
        f"| entities.db sha256[:12] | `{hashlib.sha256(db_path.read_bytes()).hexdigest()[:12]}` "
        f"(snapshot {snapshot}) |",
    ]


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline grounding check on the title eval set.")
    parser.add_argument(
        "--file", type=Path, default=_DEFAULT_FILE, help="grounding-level eval file"
    )
    parser.add_argument(
        "--split",
        choices=["dev", "test", "all"],
        default="dev",
        help="dev (default) while tuning; test only once, at the end (decision 3)",
    )
    parser.add_argument("--output", default=None, help="report path (auto-named if omitted)")
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    items = yaml.safe_load(args.file.read_text(encoding="utf-8"))["examples"]
    if args.split != "all":
        items = [i for i in items if i["split"] == args.split]
    scores = [score_item(item, build_grounding_hints(item["question_greek"])) for item in items]

    run_at = datetime.now().strftime("%Y-%m-%dT%H:%M")
    lines = [
        f"# Title grounding check — {args.file.name} | split {args.split} | {run_at}",
        "",
        "## Provenance",
        "",
        *_provenance(args.file),
        "",
        *summarize(scores),
        "",
        "## Misses (named titles not found)",
        "",
    ]
    by_id = {i["id"]: i for i in items}
    for s in scores:
        if s["kind"] in TITLE_KINDS and not s["found"]:
            it = by_id[s["id"]]
            lines.append(
                f"- {s['id']} [{s['stratum']}; {s['phrasing']}] {it['question_greek']} "
                f"→ expected «{it['source_title']}»"
            )
    report = "\n".join(lines) + "\n"

    out = (
        Path(args.output)
        if args.output
        else (_EVAL_RUNS_DIR / f"{run_at[:10]}-titles-grounding-{args.split}.md")
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"{len(scores)} items ({args.split}) — report written to {out}")


if __name__ == "__main__":
    main()
