"""ΟΝΤΟΛΟΓΙΑ page search — the word index in entities.db (ADR-030, plan step 2).

For each class in ``schema.SEARCH_CLASSES`` (university, department) the database holds:
  ``{class}_name``     one row per EXACT name (norm = group key, surface = raw literal,
                       words = search_fold of the surface);
  ``{class}_name_fts`` FTS5 over ``words`` (candidate retrieval);
  ``{class}_vocab``    every distinct word, flagged when it is a connector (whole-word only).
``schema.sync_search_index`` builds them from the class's base table — used by the builder
script and by these in-memory fixtures alike.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.grounding.db import DB_PATH
from app.grounding.normalize import normalize_greek, search_words
from app.grounding.schema import SEARCH_CLASSES, create_schema, sync_search_index


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    create_schema(c)
    rows = [
        ("ΝΟΣΗΛΕΥΤΙΚΗΣ", "ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΑΤΡΩΝ"),
        ("ΝΟΣΗΛΕΥΤΙΚΗΣ", "ΠΑΝΕΠΙΣΤΗΜΙΟ ΔΥΤΙΚΗΣ ΑΤΤΙΚΗΣ"),  # same name, 2nd university
        ("ΝΟΣΗΛΕΥΤΙΚΗΣ (ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ)", "ΔΗΜΟΚΡΙΤΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΡΑΚΗΣ"),
        ("ΕΜΠΟΡΙΑΣ & ΔΙΑΦΗΜΙΣΗΣ", "ΤΕΙ ΑΘΗΝΑΣ"),
    ]
    c.executemany(
        "INSERT INTO department(norm, family, surface, parent) VALUES (?, NULL, ?, ?)",
        [(normalize_greek(s), s, p) for s, p in rows],
    )
    sync_search_index(c, "department")
    return c


def test_search_classes() -> None:
    assert SEARCH_CLASSES == ("university", "department")


def test_one_row_per_exact_name(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT norm, surface, words FROM department_name ORDER BY surface"
    ).fetchall()
    assert [r[1] for r in rows] == [
        "ΕΜΠΟΡΙΑΣ & ΔΙΑΦΗΜΙΣΗΣ",
        "ΝΟΣΗΛΕΥΤΙΚΗΣ",
        "ΝΟΣΗΛΕΥΤΙΚΗΣ (ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ)",
    ]
    for norm, surface, words in rows:
        assert norm == normalize_greek(surface)  # the group key the API already uses
        assert words == " ".join(search_words(surface))


def test_fts_finds_words_including_the_tail(conn: sqlite3.Connection) -> None:
    hits = conn.execute(
        "SELECT n.surface FROM department_name_fts f JOIN department_name n ON n.id = f.rowid "
        "WHERE department_name_fts MATCH ?",
        ('"αλεξανδρουπολη"',),
    ).fetchall()
    assert hits == [("ΝΟΣΗΛΕΥΤΙΚΗΣ (ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ)",)]


def test_vocab_flags_connectors(conn: sqlite3.Connection) -> None:
    vocab = dict(conn.execute("SELECT word, is_connector FROM department_vocab").fetchall())
    assert vocab["και"] == 1  # from «&» via the synonym
    assert vocab["νοσηλευτικησ"] == 0
    assert "λαρισα" not in vocab


def test_sync_rejects_non_search_classes() -> None:
    c = sqlite3.connect(":memory:")
    create_schema(c)
    with pytest.raises(ValueError):
        sync_search_index(c, "course")


# ---------------------------------------------------------------------------
# The committed entities.db (rebuilt from the frozen 2026-09-24 dump)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", SEARCH_CLASSES)
def test_committed_db_has_every_exact_name(cls: str) -> None:
    db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        names = db.execute(f"SELECT COUNT(*) FROM {cls}_name").fetchone()[0]
        distinct = db.execute(
            f"SELECT COUNT(*) FROM (SELECT DISTINCT norm, surface FROM {cls})"
        ).fetchone()[0]
        fts = db.execute(f"SELECT COUNT(*) FROM {cls}_name_fts").fetchone()[0]
        vocab = db.execute(f"SELECT COUNT(*) FROM {cls}_vocab").fetchone()[0]
    finally:
        db.close()
    assert names == distinct > 0
    assert fts == names
    assert vocab > 0
