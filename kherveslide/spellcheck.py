"""Spell-checking for the in-place text editor.

A thin wrapper over the optional ``pyspellchecker`` package plus a
personal word list kept in ``QSettings`` so user jargon (institute
names, acronyms) can be remembered. If the package is missing every
word is treated as correct, so the editor degrades gracefully.
"""
from __future__ import annotations

import re

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z']+")
_SETTINGS = ("kherveDOC", "KherveSlide")
_PERSONAL_KEY = "personal_dictionary"

_checker = None
_checker_tried = False


def available() -> bool:
    return _get_checker() is not None


def _get_checker():
    global _checker, _checker_tried
    if not _checker_tried:
        _checker_tried = True
        try:
            from spellchecker import SpellChecker
            _checker = SpellChecker()
        except Exception:
            _checker = None
    return _checker


def _personal() -> set[str]:
    raw = QSettings(*_SETTINGS).value(_PERSONAL_KEY, [])
    if isinstance(raw, str):
        raw = [raw]
    return {str(w).lower() for w in (raw or [])}


def add_word(word: str) -> None:
    """Remember *word* as correctly spelled (persists across sessions)."""
    words = _personal()
    words.add(word.lower())
    QSettings(*_SETTINGS).setValue(_PERSONAL_KEY, sorted(words))


def is_misspelled(word: str) -> bool:
    sc = _get_checker()
    if sc is None or len(word) < 2:
        return False
    w = word.lower()
    if w in _personal():
        return False
    return bool(sc.unknown([w]))


def suggestions(word: str, limit: int = 7) -> list[str]:
    sc = _get_checker()
    if sc is None:
        return []
    cands = sc.candidates(word.lower())
    if not cands:
        return []
    cands = [c for c in cands if c != word.lower()]
    # Best correction first, then the rest alphabetically.
    best = sc.correction(word.lower())
    out = [best] if best and best in cands else []
    out += sorted(c for c in cands if c not in out)
    # Preserve the original capitalisation pattern for a Title-case word.
    if word[:1].isupper():
        out = [c.capitalize() for c in out]
    return out[:limit]


class SpellHighlighter(QSyntaxHighlighter):
    """Red wavy underline under words the checker doesn't recognise."""

    def __init__(self, document):
        super().__init__(document)
        self._fmt = QTextCharFormat()
        self._fmt.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)
        self._fmt.setUnderlineColor(QColor(220, 40, 40))
        self.enabled = available()

    def highlightBlock(self, text: str) -> None:
        if not self.enabled or _get_checker() is None:
            return
        personal = _personal()
        sc = _get_checker()
        for m in _WORD_RE.finditer(text):
            w = m.group(0)
            if len(w) < 2 or w.lower() in personal:
                continue
            if sc.unknown([w.lower()]):
                self.setFormat(m.start(), len(w), self._fmt)
