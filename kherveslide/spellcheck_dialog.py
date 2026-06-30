"""A deck-wide spell-check dialog (Word-style F7).

Walks the unique misspelled words across every text box in the deck and,
for each, offers suggestions plus Change-all / Ignore / Add-to-dictionary.
"""
from __future__ import annotations

import re

from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton,
    QVBoxLayout,
)

from . import spellcheck
from .model import SlideText


class SpellCheckDialog(QDialog):
    def __init__(self, deck, parent=None, on_changed=None):
        super().__init__(parent)
        self.setWindowTitle("Spell check")
        self.resize(440, 320)
        self._deck = deck
        self._on_changed = on_changed
        self.changed = 0

        # Queue of unique misspelled words across all text boxes.
        self._words: list[str] = []
        seen: set[str] = set()
        for slide in deck.slides:
            for obj in slide.objects:
                if isinstance(obj, SlideText):
                    for w in spellcheck.misspelled_words(obj.text):
                        if w not in seen:
                            seen.add(w)
                            self._words.append(w)
        self._idx = 0

        v = QVBoxLayout(self)
        self._head = QLabel()
        v.addWidget(self._head)
        self._word = QLineEdit()      # editable: type any replacement
        v.addWidget(self._word)
        v.addWidget(QLabel("Suggestions:"))
        self._sugg = QListWidget()
        self._sugg.itemDoubleClicked.connect(lambda _it: self._change())
        v.addWidget(self._sugg, 1)

        row = QHBoxLayout()
        self._btn_change = QPushButton("Change")
        self._btn_change.clicked.connect(self._change)
        self._btn_ignore = QPushButton("Ignore")
        self._btn_ignore.clicked.connect(self._next)
        self._btn_add = QPushButton("Add to dictionary")
        self._btn_add.clicked.connect(self._add)
        for b in (self._btn_change, self._btn_ignore, self._btn_add):
            row.addWidget(b)
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        v.addLayout(row)

        self._show_current()

    def has_issues(self) -> bool:
        return bool(self._words)

    def _show_current(self):
        done = self._idx >= len(self._words)
        for b in (self._btn_change, self._btn_ignore, self._btn_add):
            b.setEnabled(not done)
        self._word.setEnabled(not done)
        self._sugg.clear()
        if done:
            n = self.changed
            self._head.setText(
                f"Spell check complete — {n} word(s) changed."
                if self._words else "No misspellings found.")
            self._word.clear()
            return
        word = self._words[self._idx]
        self._head.setText(f"<b>Not in dictionary:</b> "
                           f"{self._idx + 1} of {len(self._words)}")
        self._word.setText(word)
        for s in spellcheck.suggestions(word):
            self._sugg.addItem(s)
        if self._sugg.count():
            self._sugg.setCurrentRow(0)

    def _replacement(self) -> str:
        item = self._sugg.currentItem()
        if item is not None and self._sugg.hasFocus():
            return item.text()
        # Prefer the edit field if the user typed something different.
        typed = self._word.text().strip()
        if typed and typed != self._words[self._idx]:
            return typed
        return item.text() if item is not None else typed

    def _change(self):
        if self._idx >= len(self._words):
            return
        word = self._words[self._idx]
        repl = self._replacement() or word
        if repl != word:
            self._replace_all(word, repl)
            self.changed += 1
        self._next()

    def _add(self):
        if self._idx < len(self._words):
            spellcheck.add_word(self._words[self._idx])
        self._next()

    def _next(self):
        self._idx += 1
        self._show_current()

    def _replace_all(self, word, repl):
        pat = re.compile(r"\b" + re.escape(word) + r"\b")
        for slide in self._deck.slides:
            for obj in slide.objects:
                if isinstance(obj, SlideText) and pat.search(obj.text):
                    obj.text = pat.sub(repl, obj.text)
        if self._on_changed:
            self._on_changed()
