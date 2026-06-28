"""PDF preview pane backed by Qt's own QPdfView.

Previously we rasterised every page to a QImage and wrapped each one in
a QLabel; that always looked flat because it was, literally, a PNG on a
grey background. QPdfView renders the actual PDF — with proper page
shadows, smooth scrolling, anti-aliased text — and integrates with the
status-bar zoom slider via setZoomFactor.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QModelIndex, QPointF, Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QVBoxLayout, QWidget,
)


try:
    from PySide6.QtPdf import QPdfDocument, QPdfSearchModel
    from PySide6.QtPdfWidgets import QPdfView
    _QTPDF_AVAILABLE = True
except ImportError:                           # pragma: no cover
    QPdfDocument = None                       # type: ignore
    QPdfSearchModel = None                    # type: ignore
    QPdfView = None                           # type: ignore
    _QTPDF_AVAILABLE = False


class PdfPreview(QWidget):
    """Embedded PDF viewer with a status header and live zoom."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._zoom_percent = 100
        self._fit_to_width = True
        self._current_pdf: Path | None = None
        self._extra_context_actions: list[tuple[str, object]] = []

        self._status = QLabel(self)
        self._status.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if _QTPDF_AVAILABLE:
            self._doc = QPdfDocument(self)
            self._search_model = QPdfSearchModel(self)
            self._search_model.setDocument(self._doc)

            self._view = QPdfView(self)
            self._view.setDocument(self._doc)
            self._view.setSearchModel(self._search_model)
            self._view.setPageMode(QPdfView.PageMode.MultiPage)
            self._view.setZoomMode(QPdfView.ZoomMode.Custom)
            self._view.setZoomFactor(1.0)
            self._view.setPageSpacing(18)
            self._view.setContextMenuPolicy(Qt.CustomContextMenu)
            self._view.customContextMenuRequested.connect(
                self._show_context_menu)
            layout.addWidget(self._view, 1)

            # Find bar (hidden until triggered)
            self._find_bar = QWidget(self)
            fb = QHBoxLayout(self._find_bar)
            fb.setContentsMargins(4, 2, 4, 2)
            self._find_field = QLineEdit()
            self._find_field.setPlaceholderText("Find in PDF…")
            self._find_field.returnPressed.connect(self._find_next)
            self._find_field.textChanged.connect(self._on_find_text_changed)
            fb.addWidget(self._find_field, 1)
            self._find_count = QLabel("")
            fb.addWidget(self._find_count)
            btn_prev = QPushButton("▲")
            btn_prev.setFixedWidth(28)
            btn_prev.setToolTip("Previous match")
            btn_prev.clicked.connect(self._find_prev)
            fb.addWidget(btn_prev)
            btn_next = QPushButton("▼")
            btn_next.setFixedWidth(28)
            btn_next.setToolTip("Next match")
            btn_next.clicked.connect(self._find_next)
            fb.addWidget(btn_next)
            btn_close = QPushButton("✕")
            btn_close.setFixedWidth(28)
            btn_close.clicked.connect(self._close_find)
            fb.addWidget(btn_close)
            self._find_bar.hide()
            layout.addWidget(self._find_bar)
        else:
            self._view = None
            self._search_model = None
            fallback = QLabel(
                "PDF preview needs QtPdf / QtPdfWidgets.\n"
                "Try:  pip install --upgrade PySide6 PySide6-Addons", self)
            fallback.setAlignment(Qt.AlignCenter)
            fallback.setWordWrap(True)
            layout.addWidget(fallback, 1)

    # ----- public API (unchanged contract with MainWindow) -----

    def show_message(self, msg: str) -> None:
        self._status.setText(msg)
        self._status.setStyleSheet(
            "color: #333; padding: 8px; background: #f0f0f0; "
            "border-bottom: 1px solid #c0c0c0;")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.show()
        if _QTPDF_AVAILABLE and self._view is not None:
            self._doc.close()
            self._current_pdf = None

    def show_pdf(self, pdf_path: Path) -> None:
        if not _QTPDF_AVAILABLE or self._view is None:
            return
        vbar = self._view.verticalScrollBar()
        saved_scroll = vbar.value() if vbar else 0
        self._current_pdf = Path(pdf_path)
        self._doc.close()
        self._doc.load(str(pdf_path))
        if self._fit_to_width:
            self._view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        else:
            self._view.setZoomFactor(self._zoom_percent / 100.0)
        self._status.hide()
        if saved_scroll:
            QTimer.singleShot(0, lambda: vbar.setValue(saved_scroll))

    def set_zoom_percent(self, percent: int) -> None:
        self._zoom_percent = max(25, min(400, int(percent)))
        self._fit_to_width = False
        if _QTPDF_AVAILABLE and self._view is not None:
            self._view.setZoomMode(QPdfView.ZoomMode.Custom)
            self._view.setZoomFactor(self._zoom_percent / 100.0)

    def set_fit_to_width(self, enabled: bool) -> None:
        self._fit_to_width = enabled
        if enabled and _QTPDF_AVAILABLE and self._view is not None:
            self._view.setZoomMode(QPdfView.ZoomMode.FitToWidth)

    def fit_to_width(self) -> bool:
        return self._fit_to_width

    def zoom_percent(self) -> int:
        return self._zoom_percent

    def current_page(self) -> int:
        """Return the 0-based page index currently most visible."""
        if not _QTPDF_AVAILABLE or self._view is None:
            return 0
        nav = self._view.pageNavigator()
        return nav.currentPage() if nav else 0

    def go_to_page(self, page: int) -> None:
        """Scroll to the given 0-based page."""
        if not _QTPDF_AVAILABLE or self._view is None:
            return
        n = self._doc.pageCount()
        if n < 1 or page < 0:
            return
        page = min(page, n - 1)
        nav = self._view.pageNavigator()
        if nav:
            nav.jump(page, QPointF(0, 0))
        zoom = self._view.zoomFactor()
        spacing = self._view.pageSpacing()
        # pagePointSize returns points (1/72 in); convert to pixels
        scr = self._view.screen()
        dpi_scale = (scr.logicalDotsPerInchY() / 72.0) if scr else (96.0 / 72.0)
        y = 0.0
        for i in range(page):
            size = self._doc.pagePointSize(i)
            y += size.height() * zoom * dpi_scale + spacing
        vbar = self._view.verticalScrollBar()
        if vbar:
            vbar.setValue(int(y))

    def find_text(self, text: str) -> None:
        """Search for *text* in the PDF, highlight all matches, and jump
        to the first one. Used by 'Show in PDF' cross-tab navigation."""
        if not _QTPDF_AVAILABLE or self._search_model is None:
            return
        self._search_model.setSearchString(text)
        QTimer.singleShot(300, self._jump_to_first_result)

    def show_find_bar(self) -> None:
        """Show the find bar and focus the input field."""
        if not _QTPDF_AVAILABLE:
            return
        self._find_bar.show()
        self._find_field.setFocus()
        self._find_field.selectAll()

    def hide_find_bar(self) -> None:
        if not _QTPDF_AVAILABLE:
            return
        self._find_bar.hide()
        if self._search_model:
            self._search_model.setSearchString("")

    def page_count(self) -> int:
        if not _QTPDF_AVAILABLE:
            return 0
        return self._doc.pageCount()

    # ----- find bar internals -----

    def _on_find_text_changed(self, text: str) -> None:
        if self._search_model is None:
            return
        self._search_model.setSearchString(text)
        if text:
            QTimer.singleShot(300, self._update_find_count)
            QTimer.singleShot(300, self._jump_to_first_result)
        else:
            self._find_count.setText("")

    def _update_find_count(self) -> None:
        if self._search_model is None:
            return
        n = self._search_model.rowCount(QModelIndex())
        idx = self._view.currentSearchResultIndex()
        if n > 0:
            self._find_count.setText(f"{idx + 1} / {n}")
        else:
            self._find_count.setText("No matches")

    def _find_next(self) -> None:
        if self._search_model is None or self._view is None:
            return
        n = self._search_model.rowCount(QModelIndex())
        if n < 1:
            return
        idx = self._view.currentSearchResultIndex()
        new_idx = (idx + 1) % n
        self._view.setCurrentSearchResultIndex(new_idx)
        self._scroll_to_current_result(new_idx)
        self._update_find_count()

    def _find_prev(self) -> None:
        if self._search_model is None or self._view is None:
            return
        n = self._search_model.rowCount(QModelIndex())
        if n < 1:
            return
        idx = self._view.currentSearchResultIndex()
        new_idx = (idx - 1) % n
        self._view.setCurrentSearchResultIndex(new_idx)
        self._scroll_to_current_result(new_idx)
        self._update_find_count()

    def _close_find(self) -> None:
        self._find_bar.hide()
        if self._search_model:
            self._search_model.setSearchString("")
        self._find_count.setText("")

    def _jump_to_first_result(self) -> None:
        if self._search_model is None or self._view is None:
            return
        if self._search_model.rowCount(QModelIndex()) > 0:
            self._view.setCurrentSearchResultIndex(0)
            self._scroll_to_current_result(0)

    def _scroll_to_current_result(self, index: int) -> None:
        """Scroll the viewport so that search result *index* is visible."""
        if self._search_model is None or self._view is None:
            return
        try:
            result = self._search_model.resultAtIndex(index)
            if result is not None:
                self.go_to_page(result.page())
        except (AttributeError, TypeError):
            pass

    def _show_context_menu(self, pos) -> None:
        if not self._extra_context_actions:
            return
        menu = QMenu(self)
        for label, callback in self._extra_context_actions:
            menu.addAction(label, callback)
        menu.exec(self._view.viewport().mapToGlobal(pos))
