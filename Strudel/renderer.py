from __future__ import annotations

import math
import random
import re
from pathlib import Path
from typing import Final, Iterable, Optional, Protocol, final

from PySide6.QtCore import Signal, QTimer, QPointF, QRectF, Qt, QSize
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPainterPath, QPen,
    QTextCharFormat, QTextCursor, QSyntaxHighlighter
)
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget
)

from core import log, TICK_MS, VisualizationMode, clamp

# ============================================================================= Visual Constants
VIS_PALETTES: Final[dict[str, dict[str, str]]] = {
    "Mocha": {
        "base": "#1e1e2e", "mantle": "#181825", "crust": "#11111b",
        "surface0": "#313244", "surface1": "#45475a", "surface2": "#585b70",
        "overlay0": "#6c7086", "overlay1": "#7f849c", "overlay2": "#9399b2",
        "text": "#cdd6f4", "subtext0": "#a6adc8", "subtext1": "#bac2de",
        "lavender": "#b4befe", "blue": "#89b4fa", "sapphire": "#74c7ec",
        "sky": "#89dceb", "teal": "#94e2d5", "green": "#a6e3a1",
        "yellow": "#f9e2af", "peach": "#fab387", "maroon": "#eba0ac",
        "red": "#f38ba8", "mauve": "#cba6f7", "pink": "#f5c2e7",
        "rosewater": "#f5e0dc", "flamingo": "#f2cdcd",
    },
    "Synthwave": {
        "base": "#1a103c", "mantle": "#160c33", "crust": "#0d0722",
        "surface0": "#2a1c5a", "surface1": "#3a2880", "surface2": "#4d35a8",
        "overlay0": "#6b54c2", "overlay1": "#8a6ed8", "overlay2": "#a98ee8",
        "text": "#f5e9ff", "subtext0": "#d6c2ed", "subtext1": "#e8def7",
        "lavender": "#c4a5ff", "blue": "#7c9cff", "sapphire": "#5fd3ff",
        "sky": "#7ee8ff", "teal": "#6ff5d4", "green": "#8effa8",
        "yellow": "#ffe066", "peach": "#ffa05c", "maroon": "#ff70a6",
        "red": "#ff4e88", "mauve": "#d56eff", "pink": "#ff7ed0",
        "rosewater": "#ffe0e0", "flamingo": "#ffb3b3",
    },
    "Nord": {
        "base": "#2e3440", "mantle": "#272c36", "crust": "#1e222a",
        "surface0": "#3b4252", "surface1": "#434c5e", "surface2": "#4c566a",
        "overlay0": "#5e6779", "overlay1": "#727d8f", "overlay2": "#8b95a5",
        "text": "#eceff4", "subtext0": "#d8dee9", "subtext1": "#c3cddb",
        "lavender": "#b48ead", "blue": "#81a1c1", "sapphire": "#8fbcbb",
        "sky": "#88c0d0", "teal": "#8fbcbb", "green": "#a3be8c",
        "yellow": "#ebcb8b", "peach": "#d08770", "maroon": "#bf616a",
        "red": "#bf616a", "mauve": "#b48ead", "pink": "#b48ead",
        "rosewater": "#eceff4", "flamingo": "#d8dee9",
    },
}

C: dict[str, str] = VIS_PALETTES["Mocha"]

KEYWORDS: Final[frozenset[str]] = frozenset({
    "const", "let", "var", "function", "return", "if", "else", "for",
    "while", "do", "switch", "case", "break", "continue", "new", "this",
    "class", "extends", "import", "export", "from", "default", "async",
    "await", "try", "catch", "finally", "throw", "typeof", "instanceof",
    "true", "false", "null", "undefined", "of", "in", "yield", "silence",
    "rest", "cat", "stack", "seq", "fast", "slow", "rev", "every", "hush",
})

FUNCTIONS: Final[frozenset[str]] = frozenset({
    "sine", "cosine", "tri", "saw", "square", "perlin", "range", "irand",
    "rand", "never", "sometimes", "often", "always", "_", "bd", "sd", "hh",
    "oh", "cp", "crash", "rim", "clap", "tom", "perc", "kick", "snare",
    "hihat", "openhat", "cymbal", "bass", "gain", "pan", "speed", "room",
    "delay", "delaytime", "delayfeedback", "cutoff", "resonance", "note", "s",
})

# ============================================================================= Syntax highlighter
@final
class StrudelHighlighter(QSyntaxHighlighter):
    _RE_WORD: Final[re.Pattern[str]] = re.compile(r"[a-zA-Z_$][\w$]*")
    _RULES: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
        (re.compile(r"//[^\n]*"),                       "cmt"),
        (re.compile(r"/\*.*?\*/", re.DOTALL),           "cmt"),
        (re.compile(r'"(?:[^"\\]|\\.)*"'),              "str"),
        (re.compile(r"'(?:[^'\\]|\\.)*'"),              "str"),
        (re.compile(r"`(?:[^`\\]|\\.)*`"),              "str"),
        (re.compile(r"\b\d+\.?\d*\b"),                  "num"),
        (re.compile(r"[+\-*/%=<>!&|^~?:]"),             "op"),
        (re.compile(r"[(){}\[\],;.]"),                  "punc"),
    )

    def __init__(self, doc) -> None:
        super().__init__(doc)
        self._fmt: dict[str, QTextCharFormat] = {}
        self._build_formats()

    def _f(self, color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        if bold: f.setFontWeight(QFont.Weight.Bold)
        if italic: f.setFontItalic(True)
        return f

    def _build_formats(self) -> None:
        self._fmt = {
            "kw":   self._f(C["mauve"], bold=True),
            "fn":   self._f(C["blue"]),
            "str":  self._f(C["green"]),
            "num":  self._f(C["peach"]),
            "cmt":  self._f(C["overlay0"], italic=True),
            "op":   self._f(C["sky"]),
            "punc": self._f(C["overlay0"]),
            "note": self._f(C["yellow"]),
        }

    def highlightBlock(self, text: str) -> None:
        for pat, key in self._RULES:
            for m in pat.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), self._fmt[key])
        for m in self._RE_WORD.finditer(text):
            w = m.group()
            fmt_key = "kw" if w in KEYWORDS else ("fn" if w in FUNCTIONS else None)
            if fmt_key:
                self.setFormat(m.start(), m.end() - m.start(), self._fmt[fmt_key])

# ============================================================================= Code editor
@final
class LineNumberArea(QWidget):
    def __init__(self, editor: "CodeEditor") -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:
        self._editor.line_number_area_paint_event(event)

@final
class CodeEditor(QPlainTextEdit):
    _BLINK_MS: Final[int] = 530
    _CANDIDATE_FONTS: Final[tuple[str, ...]] = (
        "JetBrains Mono", "Fira Code", "Cascadia Code", "Consolas", "Monaco", "Menlo",
    )

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setCenterOnScroll(True)
        self.setMaximumBlockCount(0)

        fam = next((f for f in self._CANDIDATE_FONTS if f in QFont().families()), "monospace")
        self.setFont(QFont(fam, 16))
        self.setStyleSheet(self._css())

        self._cur_on: bool = True
        self._blink = QTimer(self)
        self._blink.timeout.connect(self._blink_cur)
        self._blink.start(self._BLINK_MS)

        self._line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self._update_line_number_area_width(0)

    def _css(self) -> str:
        return (
            f"QPlainTextEdit {{ background: {C['mantle']}; color: {C['text']}; "
            f"border: none; padding: 32px 48px 32px 24px; "
            f"selection-background-color: {C['surface1']}; selection-color: {C['text']}; }}"
        )

    def line_number_area_width(self) -> int:
        digits = 1
        n = max(1, self.blockCount())
        while n >= 10:
            n //= 10; digits += 1
        return 3 + self.fontMetrics().horizontalAdvance('9') * digits + 12

    def _update_line_number_area_width(self, _=None) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy) -> None:
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(), self._line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            cr.left(), cr.top(), self.line_number_area_width(), cr.height(),
        )

    def line_number_area_paint_event(self, event) -> None:
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor(C["crust"]))
        block = self.firstVisibleBlock()
        bn = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        current = self.textCursor().blockNumber()
        h = self.fontMetrics().height()
        width = self._line_number_area.width() - 8

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor(C["mauve"] if bn == current else C["overlay0"]))
                painter.drawText(0, top, width, h, Qt.AlignmentFlag.AlignRight, str(bn + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            bn += 1

    def _blink_cur(self) -> None:
        self._cur_on = not self._cur_on
        self.viewport().update()

    def append_chars(self, text: str) -> None:
        if not text: return
        cur = self.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.beginEditBlock()
        cur.insertText(text)
        cur.endEditBlock()
        self.setTextCursor(cur)
        self.ensureCursorVisible()

    def paintEvent(self, ev) -> None:
        super().paintEvent(ev)
        if not self._cur_on or not self.toPlainText(): return
        cur = self.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        r = self.cursorRect(cur)
        p = QPainter(self.viewport())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C["rosewater"]))
        p.drawRect(int(r.x()), int(r.y()), 2, int(r.height()))

# ============================================================================= Visualizer Renderers
class WaveformRenderer(Protocol):
    def render(self, painter: QPainter, bars: list[float],
               w: int, h: int, palette: dict[str, str]) -> None: ...

@final
class BarsRenderer:
    def render(self, painter: QPainter, bars: list[float],
               w: int, h: int, palette: dict[str, str]) -> None:
        n = len(bars); bar_w = w / n
        painter.setPen(Qt.PenStyle.NoPen)
        for i, v in enumerate(bars):
            bh = v * (h / 2 - 3)
            if bh < 1: bh = 1.5
            painter.setBrush(_bar_color(v))
            x = i * bar_w + 1
            painter.drawRoundedRect(QRectF(x, h - bh, max(int(bar_w - 2), 1), max(bh, 1.0)), 2, 2)

@final
class MirrorRenderer:
    def render(self, painter: QPainter, bars: list[float],
               w: int, h: int, palette: dict[str, str]) -> None:
        n = len(bars); bar_w = w / n; cy = h / 2
        painter.setPen(Qt.PenStyle.NoPen)
        for i, v in enumerate(bars):
            bh = v * (h / 2 - 3)
            if bh < 1: bh = 1.5
            painter.setBrush(_bar_color(v))
            x = i * bar_w + 1
            painter.drawRoundedRect(QRectF(x, cy - bh, max(int(bar_w - 2), 1), max(bh * 2, 1.0)), 2, 2)

@final
class WaveRenderer:
    def render(self, painter: QPainter, bars: list[float],
               w: int, h: int, palette: dict[str, str]) -> None:
        if not bars: return
        painter.setPen(QPen(QColor(palette["mauve"]), 2))
        path = QPainterPath()
        n = len(bars)
        path.moveTo(0, h - bars[0] * (h / 2 - 3))
        for i, v in enumerate(bars):
            x = i * (w / n) + (w / n) / 2
            y = h - v * (h / 2 - 3)
            path.lineTo(x, y)
        painter.drawPath(path)

@final
class CircularRenderer:
    def render(self, painter: QPainter, bars: list[float],
               w: int, h: int, palette: dict[str, str]) -> None:
        cx, cy = w / 2, h / 2
        base_r = min(cx, cy) * 0.4
        painter.setPen(Qt.PenStyle.NoPen)
        for i, v in enumerate(bars):
            angle = (i / len(bars)) * 2 * math.pi
            r = base_r + v * (min(cx, cy) * 0.5)
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            painter.setBrush(_bar_color(v))
            painter.drawEllipse(QPointF(x, y), 3 + v * 2, 3 + v * 2)

_BAR_COLOR_LUT: dict[int, QColor] = {}

def _bar_color(v: float) -> QColor:
    key = int(clamp(v, 0.0, 1.0) * 255) & 0xFF
    col = _BAR_COLOR_LUT.get(key)
    if col is None:
        hue = (270 - (key / 255.0) * 50) % 360
        col = QColor.fromHsv(int(hue), 70, 55 + int((key / 255.0) * 45))
        _BAR_COLOR_LUT[key] = col
    return col

_RENDERER_REGISTRY: Final[dict[VisualizationMode, WaveformRenderer]] = {
    VisualizationMode.BARS: BarsRenderer(),
    VisualizationMode.MIRROR: MirrorRenderer(),
    VisualizationMode.WAVE: WaveRenderer(),
    VisualizationMode.CIRCULAR: CircularRenderer(),
}

# ============================================================================= Visualizer Widget
@final
class WaveformBar(QWidget):
    N_BARS: Final[int] = 96

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(110)
        self.setMinimumWidth(200)

        self._bars: list[float] = [0.0] * self.N_BARS
        self._tgt: list[float] = [0.0] * self.N_BARS
        self._audio_levels: list[float] = [0.0] * self.N_BARS
        self._phase: float = 0.0
        self._playing: bool = False
        self._mode: VisualizationMode = VisualizationMode.BARS
        self._palette_name: str = "Mocha"
        self._glow: bool = True

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TICK_MS)

    def set_playing(self, v: bool) -> None:
        self._playing = v
        if not v:
            self._tgt = [0.0] * self.N_BARS
            self._audio_levels = [0.0] * self.N_BARS

    def set_mode(self, mode: str) -> None:
        try: self._mode = VisualizationMode(mode)
        except ValueError: self._mode = VisualizationMode.BARS
        self.update()

    def set_palette(self, name: str) -> None:
        if name in VIS_PALETTES:
            self._palette_name = name
            self.update()

    def set_glow(self, on: bool) -> None:
        self._glow = on
        self.update()

    def set_audio_levels(self, levels: list[float]) -> None:
        if levels:
            step = max(1, len(levels) // self.N_BARS)
            self._audio_levels = [
                clamp(float(levels[i * step]), 0.0, 1.0) for i in range(self.N_BARS)
            ]

    def _tick(self) -> None:
        self._phase += 0.12
        if self._playing:
            for i in range(self.N_BARS):
                if self._audio_levels[i] > 0.01:
                    self._tgt[i] = self._audio_levels[i] * (0.5 + 0.5 * math.sin(i * 0.25 + self._phase))
                else:
                    base = 0.5 + 0.5 * math.sin(i * 0.25 + self._phase)
                    self._tgt[i] = random.uniform(0.05, 1.0) * base

        changed = False
        for i in range(self.N_BARS):
            d = self._tgt[i] - self._bars[i]
            if abs(d) > 0.005:
                self._bars[i] += d * 0.35
                changed = True
            elif self._bars[i] != self._tgt[i]:
                self._bars[i] = self._tgt[i]
                changed = True
        if changed:
            self.update()

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(C["base"]))
        renderer = _RENDERER_REGISTRY.get(self._mode, _RENDERER_REGISTRY[VisualizationMode.BARS])
        renderer.render(p, self._bars, self.width(), self.height(), C)

# ============================================================================= Dialogs
@final
class ExportProgressDialog(QDialog):
    cancel_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Progress")
        self.setMinimumSize(480, 220)
        l = QVBoxLayout(self)
        l.setContentsMargins(30, 30, 30, 30)
        l.setSpacing(12)

        self._title = QLabel("Exporting MP4…")
        self._title.setFont(QFont("Inter", 16, QFont.Weight.Bold))
        l.addWidget(self._title)

        self._bar = QProgressBar()
        self._bar.setFixedHeight(40)
        l.addWidget(self._bar)

        self._lbl = QLabel("Preparing…")
        self._lbl.setWordWrap(True)
        l.addWidget(self._lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn = QPushButton("Close")
        self._btn.setEnabled(False)
        self._btn.clicked.connect(self.accept)
        self._cancel = QPushButton("Cancel")
        self._cancel.clicked.connect(self._on_cancel)
        btn_row.addWidget(self._cancel)
        btn_row.addWidget(self._btn)
        l.addLayout(btn_row)

    def _on_cancel(self) -> None:
        self._cancel.setEnabled(False)
        self._lbl.setText("Cancelling — finishing current frames…")
        self.cancel_requested.emit()

    def set_progress(self, pct: int, msg: str) -> None:
        self._bar.setValue(clamp(pct, 0, 100))
        self._lbl.setText(msg)

    def set_complete(self, msg: str) -> None:
        self._bar.setValue(100)
        self._lbl.setText(msg)
        self._title.setText("Complete!")
        self._btn.setEnabled(True)
        self._cancel.setEnabled(False)

    def set_failed(self, msg: str) -> None:
        self._lbl.setText(msg)
        self._title.setText("Failed!")
        self._btn.setEnabled(True)
        self._cancel.setEnabled(False)

@final
class BatchProgressDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Batch Export")
        self.setMinimumSize(640, 440)
        l = QVBoxLayout(self)
        l.setContentsMargins(20, 20, 20, 20)
        l.setSpacing(10)

        self._header = QLabel("Batch Export")
        self._header.setFont(QFont("Inter", 16, QFont.Weight.Bold))
        l.addWidget(self._header)

        self._overall_lbl = QLabel("Preparing…")
        l.addWidget(self._overall_lbl)

        self._overall_bar = QProgressBar()
        self._overall_bar.setFixedHeight(28)
        l.addWidget(self._overall_bar)

        self._file_bar = QProgressBar()
        self._file_bar.setFixedHeight(18)
        l.addWidget(self._file_bar)

        self._list = QListWidget()
        l.addWidget(self._list, stretch=1)

        self._close_btn = QPushButton("Close")
        self._close_btn.setEnabled(False)
        self._close_btn.clicked.connect(self.accept)
        l.addWidget(self._close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def populate_files(self, files: Iterable[str]) -> None:
        for f in files:
            self._list.addItem(QListWidgetItem(f"⏳ {Path(f).name}"))

    def on_file_started(self, idx: int, total: int, filepath: str) -> None:
        self._overall_bar.setValue(int(idx / total * 100))
        self._overall_lbl.setText(f"Processing {idx + 1} of {total}: {Path(filepath).name}")
        self._file_bar.setValue(0)

    def on_file_progress(self, msg: str) -> None:
        m = re.search(r"(\d+)%", msg)
        if m: self._file_bar.setValue(int(m.group(1)))

    def on_file_finished(self, filepath: str, success: bool, message: str) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            if filepath in item.text():
                icon = "✓" if success else "✗"
                item.setText(f"{icon} {Path(filepath).name}")
                item.setForeground(QColor(C["green"] if success else C["red"]))
                break

    def on_batch_finished(self, succ: int, fail: int) -> None:
        self._overall_bar.setValue(100)
        self._file_bar.setValue(100)
        self._overall_lbl.setText(f"Complete: {succ} succeeded, {fail} failed")
        self._close_btn.setEnabled(True)