"""Lightweight regex syntax highlighting for the code viewer.

Deliberately simple — tree-sitter stays in the context engine; the UI only
needs readable source. Two highlighters: CodeHighlighter (per-language rules)
and DiffHighlighter (unified-diff +/− coloring).
"""
from __future__ import annotations

import re

from PyQt6.QtCore import QRegularExpression
from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextDocument

from app.ui import theme

PY_KEYWORDS = (
    "False None True and as assert async await break class continue def del elif else "
    "except finally for from global if import in is lambda nonlocal not or pass raise "
    "return try while with yield match case"
).split()

JS_KEYWORDS = (
    "abstract async await break case catch class const continue debugger default delete do "
    "else enum export extends false finally for function if implements import in instanceof "
    "interface let new null of private protected public return static super switch this throw "
    "true try type typeof var void while with yield"
).split()


def _fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    if italic:
        fmt.setFontItalic(True)
    return fmt


class CodeHighlighter(QSyntaxHighlighter):
    def __init__(self, document: QTextDocument, language: str = "python") -> None:
        super().__init__(document)
        self.rules: list[tuple[QRegularExpression, QTextCharFormat]] = []
        self._multiline_start = QRegularExpression()
        self._multiline_end = QRegularExpression()
        self._multiline_fmt = _fmt(theme.SYN_COMMENT, italic=True)
        self.set_language(language)

    def set_language(self, language: str) -> None:
        self.rules = []
        kw = _fmt(theme.SYN_KEYWORD, bold=True)
        string_f = _fmt(theme.SYN_STRING)
        comment_f = _fmt(theme.SYN_COMMENT, italic=True)
        number_f = _fmt(theme.SYN_NUMBER)
        deco_f = _fmt(theme.SYN_DECORATOR)
        defname_f = _fmt(theme.SYN_DEFNAME, bold=True)

        if language == "python":
            keywords = PY_KEYWORDS
            self.rules.append((QRegularExpression(r"@[A-Za-z_][\w.]*"), deco_f))
            self.rules.append((QRegularExpression(r"\b(def|class)\s+([A-Za-z_]\w*)"), defname_f))
            self.rules.append((QRegularExpression(r"#[^\n]*"), comment_f))
            self._multiline_start = QRegularExpression(r'"""|\'\'\'')
            self._multiline_end = QRegularExpression(r'"""|\'\'\'')
        else:
            keywords = JS_KEYWORDS
            self.rules.append((QRegularExpression(r"\b(function|class)\s+([A-Za-z_$][\w$]*)"), defname_f))
            self.rules.append((QRegularExpression(r"//[^\n]*"), comment_f))
            self._multiline_start = QRegularExpression(r"/\*")
            self._multiline_end = QRegularExpression(r"\*/")

        pattern = r"\b(" + "|".join(re.escape(k) for k in keywords) + r")\b"
        self.rules.insert(0, (QRegularExpression(pattern), kw))
        self.rules.append((QRegularExpression(r"\b\d+(\.\d+)?\b"), number_f))
        self.rules.append((QRegularExpression(r'"[^"\n]*"'), string_f))
        self.rules.append((QRegularExpression(r"'[^'\n]*'"), string_f))
        self.rules.append((QRegularExpression(r"`[^`\n]*`"), string_f))
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        for regex, fmt in self.rules:
            it = regex.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)
        # Multiline strings/comments
        self.setCurrentBlockState(0)
        start = 0
        if self.previousBlockState() != 1:
            m = self._multiline_start.match(text)
            start = m.capturedStart() if m.hasMatch() else -1
        while start >= 0:
            m_end = self._multiline_end.match(text, start + 3)
            if not m_end.hasMatch():
                self.setCurrentBlockState(1)
                self.setFormat(start, len(text) - start, self._multiline_fmt)
                break
            end = m_end.capturedEnd()
            self.setFormat(start, end - start, self._multiline_fmt)
            m_next = self._multiline_start.match(text, end)
            start = m_next.capturedStart() if m_next.hasMatch() else -1


class DiffHighlighter(QSyntaxHighlighter):
    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self._add = _fmt(theme.DIFF_ADD)
        self._del = _fmt(theme.DIFF_DEL)
        self._hunk = _fmt(theme.DIFF_HUNK, bold=True)
        self._meta = _fmt(theme.DIFF_META, italic=True)

    def highlightBlock(self, text: str) -> None:
        if text.startswith("@@"):
            self.setFormat(0, len(text), self._hunk)
        elif text.startswith("+++") or text.startswith("---"):
            self.setFormat(0, len(text), self._meta)
        elif text.startswith("+"):
            self.setFormat(0, len(text), self._add)
        elif text.startswith("-"):
            self.setFormat(0, len(text), self._del)
