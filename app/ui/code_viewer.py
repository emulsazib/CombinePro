"""Interactive code viewer: syntax-highlighted source with line numbers, plus a
unified-diff mode that lights up when the open file changes on disk."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QKeySequence,
    QPainter,
    QPaintEvent,
    QResizeEvent,
    QTextCursor,
    QTextFormat,
)
from PyQt6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

from app.ui import theme
from app.ui.highlighter import CodeHighlighter, DiffHighlighter

_LANG_BY_EXT = {
    ".py": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".ts": "javascript", ".tsx": "javascript",
}


class _LineNumberArea(QWidget):
    def __init__(self, viewer: "CodeViewer") -> None:
        super().__init__(viewer)
        self._viewer = viewer

    def sizeHint(self) -> QSize:
        return QSize(self._viewer.line_number_width(), 0)

    def paintEvent(self, event: QPaintEvent) -> None:
        self._viewer.paint_line_numbers(event)


class CodeViewer(QPlainTextEdit):
    """Editable code editor. In file mode the user can type; Ctrl+S writes the
    buffer back to disk (the file watcher then picks up the real change). Diff
    mode is read-only."""

    saved = pyqtSignal(str)  # emits the saved file's label/path
    dirty_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(12)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self._line_area = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_area_width)
        self.updateRequest.connect(self._update_line_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_line_area_width(0)

        self._code_highlighter: CodeHighlighter | None = None
        self._diff_highlighter: DiffHighlighter | None = None
        self.current_path: str | None = None
        self.current_abs: Path | None = None
        self.mode: str = "file"  # "file" | "diff"
        self._dirty = False
        self.textChanged.connect(self._on_text_changed)
        self._highlight_current_line()

    # ------------------------------------------------------------- public API

    def show_file(self, path: Path, rel_label: str | None = None) -> None:
        try:
            text = path.read_text("utf-8", errors="replace")
        except OSError as exc:
            self.setReadOnly(True)
            self.setPlainText(f"<< cannot read {path}: {exc} >>")
            return
        self.mode = "file"
        self.current_path = rel_label or str(path)
        self.current_abs = path
        self._use_code_highlighter(path.suffix.lower())
        self.setReadOnly(False)
        self.setPlainText(text)
        self._set_dirty(False)

    def show_diff(self, rel_path: str, diff: str) -> None:
        self.mode = "diff"
        self.current_path = rel_path
        self.current_abs = None
        self.setReadOnly(True)
        self._use_diff_highlighter()
        self.setPlainText(diff or f"(no textual diff for {rel_path})")
        self._set_dirty(False)
        self._highlight_current_line()

    def show_text(self, text: str, label: str = "") -> None:
        self.mode = "file"
        self.current_path = label or None
        self.current_abs = None
        self.setReadOnly(True)
        self._use_code_highlighter("")
        self.setPlainText(text)
        self._set_dirty(False)

    # -------------------------------------------------------------- editing

    def save(self) -> bool:
        """Write the buffer to disk. Returns True on success."""
        if self.mode != "file" or self.current_abs is None:
            return False
        try:
            self.current_abs.write_text(self.toPlainText(), "utf-8")
        except OSError:
            return False
        self._set_dirty(False)
        self.saved.emit(self.current_path or str(self.current_abs))
        return True

    def keyPressEvent(self, event) -> None:  # noqa: ANN001
        if event.matches(QKeySequence.StandardKey.Save):
            self.save()
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_text_changed(self) -> None:
        if self.mode == "file" and not self.isReadOnly():
            self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        if dirty != self._dirty:
            self._dirty = dirty
            self.dirty_changed.emit(dirty)

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    # ---------------------------------------------------------- highlighting

    def _use_code_highlighter(self, ext: str) -> None:
        if self._diff_highlighter is not None:
            self._diff_highlighter.setDocument(None)
            self._diff_highlighter = None
        lang = _LANG_BY_EXT.get(ext, "python" if ext == ".py" else "generic")
        if self._code_highlighter is None:
            self._code_highlighter = CodeHighlighter(self.document(), lang)
        else:
            self._code_highlighter.set_language(lang)

    def _use_diff_highlighter(self) -> None:
        if self._code_highlighter is not None:
            self._code_highlighter.setDocument(None)
            self._code_highlighter = None
        if self._diff_highlighter is None:
            self._diff_highlighter = DiffHighlighter(self.document())

    # ---------------------------------------------------------- line numbers

    def line_number_width(self) -> int:
        digits = max(3, len(str(self.blockCount())))
        return 12 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_area_width(self, _count: int) -> None:
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def _update_line_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(), self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_area_width(0)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_width(), cr.height()))

    def _highlight_current_line(self) -> None:
        """Subtle full-width highlight of the caret's line (file mode only)."""
        selections: list[QTextEdit.ExtraSelection] = []
        if self.mode == "file":
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(QColor(theme.CURRENT_LINE))
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            cursor = self.textCursor()
            cursor.clearSelection()
            selection.cursor = cursor
            selections.append(selection)
        self.setExtraSelections(selections)

    def paint_line_numbers(self, event: QPaintEvent) -> None:
        painter = QPainter(self._line_area)
        painter.fillRect(event.rect(), QColor(theme.GUTTER_BG))
        painter.setPen(QColor(theme.GUTTER_FG))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(
                    0, top, self._line_area.width() - 6, self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight, str(block_number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1
