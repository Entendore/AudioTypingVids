from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, final

try:
    import numpy as np
    HAS_NUMPY: bool = True
except ImportError:
    HAS_NUMPY = False

from PySide6.QtCore import QThread, QTimer, QSettings, Qt
from PySide6.QtGui import (
    QColor, QFont, QImage, QKeySequence, QPainter, QPixmap,
    QShortcut, QLinearGradient
)
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QSlider, QStatusBar, QVBoxLayout, QWidget
)

from core import (
    log, StrudelAudio, TypingEngine, VideoWriterWorker, BatchProcessor,
    DEFAULT_SPEED_MS, SPEED_MIN_MS, SPEED_MAX_MS, AUDIO_POLL_MS,
    REC_BLINK_MS, SAVE_DEBOUNCE_MS, FINAL_HOLD_MS,
    AspectMode, ExportConfig, clamp, decode_audio_data_url,
    HAS_FFMPEG, INPUT_DIR, OUTPUT_DIR, TEMP_DIR
)
from renderer import (
    C, VIS_PALETTES, VisualizationMode,
    StrudelHighlighter, CodeEditor, WaveformBar,
    ExportProgressDialog, BatchProgressDialog
)

RESOLUTIONS = {
    "YouTube 1080p (1920x1080)":  (1920, 1080),
    "YouTube Shorts (1080x1920)": (1080, 1920),
    "YouTube 720p (1280x720)":    (1280, 720),
    "Square (1080x1080)":         (1080, 1080),
    "Twitter/X (1200x675)":       (1200, 675),
    "4K UHD (3840x2160)":         (3840, 2160),
}
ASPECT_MODES = ("Fit (letterbox)", "Fill (crop)", "Stretch")

DEFAULT_CODE = r"""// Ambient Arpeggiator
 $: note("<c3 eb3 g3 bb3 d4 f4 ab4 c5>")
  .s("sawtooth")
  .cutoff(sine.range(300, 3000).slow(8))
  .gain(0.6)
  .slow(2)
  .room(0.4)
"""

def css(template: str, **extra: str) -> str:
    merged = {**C, **extra}
    import re
    def _sub(m: re.Match) -> str:
        key = m.group(1)
        return merged.get(key, m.group(0))
    return re.sub(r"\{([a-z][a-z0-9_]*)\}", _sub, template)

# ============================================================================= Main window
@final
class MainWindow(QMainWindow):
    def __init__(self, filepath: Optional[str] = None) -> None:
        super().__init__()
        self._settings = QSettings("StrudelAnimator", "MainApp")
        self._fp = filepath
        self._code = ""

        self._audio = StrudelAudio()
        self._audio.audio_levels.connect(self._wave_set_levels)
        self._audio.ready_changed.connect(self._on_audio_ready_changed)
        self._audio.play_failed.connect(self._on_audio_play_failed)
        self._audio.status_message.connect(self._on_audio_status_message)

        self._typing_engine = TypingEngine()
        self._typing_engine.typed.connect(self._on_typed)
        self._typing_engine.progress.connect(self._on_typing_progress)
        self._typing_engine.finished.connect(self._on_typing_finished)

        self._exporting = False
        self._audio_file: Optional[str] = None
        self._export_out_path: Optional[str] = None
        self._audio_recording = False
        self._export_cancelled = False
        self._batch_mode = False
        self._export_cfg: Optional[ExportConfig] = None

        self._batch_processor: Optional[BatchProcessor] = None
        self._batch_dialog: Optional[BatchProgressDialog] = None
        self._writer_thread: Optional[QThread] = None
        self._writer_worker: Optional[VideoWriterWorker] = None
        self._export_dialog: Optional[ExportProgressDialog] = None

        self._frame_timer = QTimer(self)
        self._frame_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._frame_timer.timeout.connect(self._capture_frame)

        self._audio_poll_timer = QTimer(self)
        self._audio_poll_timer.setInterval(AUDIO_POLL_MS)
        self._audio_poll_timer.timeout.connect(self._audio.poll_audio_levels)

        self._rec_blink_timer = QTimer(self)
        self._rec_blink_timer.setInterval(REC_BLINK_MS)
        self._rec_blink_timer.timeout.connect(self._toggle_rec_dot)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DEBOUNCE_MS)
        self._save_timer.timeout.connect(self._save_settings)

        self._build_ui()
        self._load_settings()
        self._load_code()
        self.resize(1280, 760)

        bridge_path = Path(__file__).parent.resolve() / "strudel_bridge.html"
        if self._audio.init(self, bridge_path):
            self.statusBar().showMessage("Initializing Strudel audio engine…")
            self._b_start.setEnabled(False)
        else:
            self.statusBar().showMessage("WebEngine init failed — audio disabled")

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        tb = QFrame()
        tb.setFixedHeight(46)
        tb.setStyleSheet(css("QFrame{background:{crust};border-bottom:1px solid {surface0}}"))
        tl = QHBoxLayout(tb)
        tl.setContentsMargins(16, 0, 16, 0)

        lbl = QLabel("  Strudel Typing Animator")
        lbl.setFont(QFont("Inter", 13, QFont.Weight.Bold))
        lbl.setStyleSheet(css("color:{mauve}"))
        tl.addWidget(lbl)
        tl.addStretch()

        self._rec_dot = QLabel("● REC")
        self._rec_dot.setStyleSheet(css(
            "color:{red};font-weight:bold;font-size:12px;padding:2px 8px;"
            "border:1px solid {red};border-radius:4px;"
        ))
        self._rec_dot.setVisible(False)
        tl.addWidget(self._rec_dot)
        tl.addStretch()

        tl.addWidget(QLabel("Export Res:"))
        self._export_res_cb = QComboBox()
        self._export_res_cb.addItems(RESOLUTIONS.keys())
        self._export_res_cb.setFixedWidth(220)
        tl.addWidget(self._export_res_cb)

        tl.addWidget(QLabel("Fit:"))
        self._aspect_cb = QComboBox()
        self._aspect_cb.addItems(ASPECT_MODES)
        self._aspect_cb.setFixedWidth(150)
        tl.addWidget(self._aspect_cb)
        vbox.addWidget(tb)

        central_h = QHBoxLayout()
        central_h.setContentsMargins(0, 0, 0, 0)
        central_h.setSpacing(0)

        ed_frame = QFrame()
        self._capture_widget = ed_frame
        ed_frame.setStyleSheet(css("QFrame{background:{mantle}}"))
        evl = QVBoxLayout(ed_frame)
        evl.setContentsMargins(0, 0, 0, 0)
        evl.setSpacing(0)
        self._editor = CodeEditor()
        StrudelHighlighter(self._editor.document())
        evl.addWidget(self._editor, stretch=1)
        self._wave = WaveformBar()
        evl.addWidget(self._wave)
        central_h.addWidget(ed_frame, stretch=1)

        sidebar = QFrame()
        sidebar.setFixedWidth(260)
        sidebar.setStyleSheet(css("QFrame{background:{crust};border-left:1px solid {surface0}}"))
        sbl = QVBoxLayout(sidebar)
        sbl.setContentsMargins(16, 16, 16, 16)
        sbl.setSpacing(12)
        sbl.addWidget(self._build_sidebar_content())
        central_h.addWidget(sidebar)
        vbox.addLayout(central_h, stretch=1)

        vbox.addWidget(self._build_bottom_bar())
        self.setStatusBar(QStatusBar())

        QShortcut(QKeySequence("F5"),     self, self._start)
        QShortcut(QKeySequence("Space"),  self, self._pause)
        QShortcut(QKeySequence("Ctrl+O"), self, self._open_file)
        QShortcut(QKeySequence("Ctrl+E"), self, self._export_mp4)
        QShortcut(QKeySequence("Ctrl+B"), self, self._start_batch)
        QShortcut(QKeySequence("Escape"), self, self._reset)

    def _build_sidebar_content(self) -> QWidget:
        container = QWidget()
        sbl = QVBoxLayout(container)
        sbl.setContentsMargins(0, 0, 0, 0)
        sbl.setSpacing(12)

        def section(text: str) -> QLabel:
            l = QLabel(text)
            l.setFont(QFont("Inter", 10, QFont.Weight.Bold))
            l.setStyleSheet(css("color:{overlay1};border-bottom:1px solid {surface0};padding-bottom:4px;"))
            return l

        sbl.addWidget(section("AUDIO"))
        vol_box = QVBoxLayout(); vol_box.setSpacing(2)
        vol_lbl = QLabel("Master Volume")
        vol_lbl.setStyleSheet(css("color:{overlay0};font-size:11px"))
        vol_box.addWidget(vol_lbl)
        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 100); self._vol_slider.setValue(80)
        self._vol_slider.valueChanged.connect(self._on_volume)
        vol_box.addWidget(self._vol_slider)
        sbl.addLayout(vol_box)

        sbl.addWidget(section("TYPING"))
        spd_box = QVBoxLayout(); spd_box.setSpacing(2)
        spd_lbl = QLabel("Speed (ms)")
        spd_lbl.setStyleSheet(css("color:{overlay0};font-size:11px"))
        spd_box.addWidget(spd_lbl)
        self._spd = QSlider(Qt.Orientation.Horizontal)
        self._spd.setRange(SPEED_MIN_MS, SPEED_MAX_MS); self._spd.setValue(DEFAULT_SPEED_MS)
        self._spd.valueChanged.connect(self._on_speed)
        spd_box.addWidget(self._spd)
        self._spd_lbl = QLabel(f"{DEFAULT_SPEED_MS} ms")
        spd_box.addWidget(self._spd_lbl)
        sbl.addLayout(spd_box)

        self._chk_human = QCheckBox("Human-like Typing")
        self._chk_human.toggled.connect(self._on_human_toggle)
        sbl.addWidget(self._chk_human)

        fs_box = QVBoxLayout(); fs_box.setSpacing(2)
        fs_lbl = QLabel("Font Size")
        fs_lbl.setStyleSheet(css("color:{overlay0};font-size:11px"))
        fs_box.addWidget(fs_lbl)
        self._fs_slider = QSlider(Qt.Orientation.Horizontal)
        self._fs_slider.setRange(10, 32); self._fs_slider.setValue(16)
        self._fs_slider.valueChanged.connect(self._on_font_size)
        fs_box.addWidget(self._fs_slider)
        sbl.addLayout(fs_box)

        sbl.addWidget(section("VISUALIZER"))
        vis_box = QVBoxLayout(); vis_box.setSpacing(2)
        self._vis_cb = QComboBox()
        self._vis_cb.addItems([m.value for m in VisualizationMode])
        self._vis_cb.currentTextChanged.connect(lambda t: self._wave.set_mode(t))
        vis_box.addWidget(self._vis_cb)
        self._pal_cb = QComboBox()
        self._pal_cb.addItems(VIS_PALETTES.keys())
        self._pal_cb.currentTextChanged.connect(self._on_palette_changed)
        vis_box.addWidget(self._pal_cb)
        self._chk_glow = QCheckBox("Glow / Smooth")
        self._chk_glow.setChecked(True)
        self._chk_glow.toggled.connect(self._wave.set_glow)
        vis_box.addWidget(self._chk_glow)
        sbl.addLayout(vis_box)

        sbl.addWidget(section("EXPORT"))
        for label_text, items, attr in (
            ("FPS:",      ["24", "30", "60"],                        "_fps_cb"),
            ("Quality:",  ["High (18)", "Medium (23)", "Low (28)"],  "_quality_cb"),
            ("Audio:",    ["128k", "192k", "320k"],                  "_audio_bitrate_cb"),
        ):
            row = QHBoxLayout()
            row.addWidget(QLabel(label_text))
            row.addStretch()
            cb = QComboBox()
            cb.addItems(items)
            cb.setFixedWidth(80)
            row.addWidget(cb)
            setattr(self, attr, cb)
            sbl.addLayout(row)

        self._chk_render_vis = QCheckBox("Include Visualizer in Video")
        self._chk_render_vis.setChecked(True)
        sbl.addWidget(self._chk_render_vis)

        self._chk_bg_gradient = QCheckBox("Gradient Background")
        self._chk_bg_gradient.setChecked(True)
        sbl.addWidget(self._chk_bg_gradient)

        sbl.addStretch()
        return container

    def _build_bottom_bar(self) -> QFrame:
        cb = QFrame()
        cb.setFixedHeight(60)
        cb.setStyleSheet(css("QFrame{background:{crust};border-top:1px solid {surface0}}"))
        cl = QHBoxLayout(cb)
        cl.setContentsMargins(20, 8, 20, 8)
        cl.setSpacing(10)

        bs = css(
            "QPushButton{background:{mantle};color:{text};border:1px solid {surface0};"
            "border-radius:6px;padding:8px 18px;font:500 13px 'Inter';}"
            "QPushButton:hover{background:{surface0}}"
            "QPushButton:disabled{color:{overlay0};background:{crust};}"
        )
        ba = css(
            "QPushButton{background:{mauve};color:{crust};border:1px solid {surface0};"
            "border-radius:6px;padding:8px 18px;font:500 13px 'Inter';}"
            "QPushButton:hover{background:{lavender}}"
            "QPushButton:disabled{color:{overlay0};background:{crust};}"
        )

        self._b_load = QPushButton("Load File");     self._b_load.setStyleSheet(bs)
        self._b_load.clicked.connect(self._open_file);   cl.addWidget(self._b_load)

        self._b_start = QPushButton("Start");         self._b_start.setStyleSheet(ba)
        self._b_start.clicked.connect(self._start);       cl.addWidget(self._b_start)

        self._b_pause = QPushButton("Pause");         self._b_pause.setStyleSheet(bs)
        self._b_pause.clicked.connect(self._pause);       cl.addWidget(self._b_pause)

        self._b_stop = QPushButton("Reset");          self._b_stop.setStyleSheet(bs)
        self._b_stop.clicked.connect(self._reset);        cl.addWidget(self._b_stop)

        self._b_export = QPushButton("Export MP4");   self._b_export.setStyleSheet(ba)
        self._b_export.clicked.connect(self._export_mp4); cl.addWidget(self._b_export)

        self._b_batch = QPushButton("Batch Export");  self._b_batch.setStyleSheet(ba)
        self._b_batch.clicked.connect(self._start_batch); cl.addWidget(self._b_batch)

        cl.addStretch()
        self._prog = QLabel("Ready")
        self._prog.setStyleSheet(css("color:{overlay0}"))
        cl.addWidget(self._prog)
        return cb

    def _load_settings(self) -> None:
        s = self._settings
        speed = int(s.value("speed", DEFAULT_SPEED_MS))
        self._spd.setValue(speed)
        self._typing_engine.set_speed(speed)
        self._vol_slider.setValue(int(s.value("volume", 80)))
        self._chk_human.setChecked(s.value("human_typing", True, type=bool))
        self._typing_engine.set_human(self._chk_human.isChecked())
        self._fs_slider.setValue(int(s.value("font_size", 16)))
        self._vis_cb.setCurrentText(s.value("vis_mode", "Bars"))
        self._pal_cb.setCurrentText(s.value("vis_palette", "Mocha"))
        self._chk_glow.setChecked(s.value("vis_glow", True, type=bool))
        self._fps_cb.setCurrentText(s.value("fps", "30"))
        self._quality_cb.setCurrentText(s.value("quality", "High (18)"))
        self._audio_bitrate_cb.setCurrentText(s.value("audio_bitrate", "192k"))
        self._export_res_cb.setCurrentText(s.value("res", "YouTube 1080p (1920x1080)"))
        self._aspect_cb.setCurrentText(s.value("aspect", ASPECT_MODES[0]))
        self._chk_render_vis.setChecked(s.value("render_vis", True, type=bool))
        self._chk_bg_gradient.setChecked(s.value("bg_gradient", True, type=bool))

    def _schedule_save(self) -> None: self._save_timer.start()

    def _save_settings(self) -> None:
        s = self._settings
        s.setValue("speed", self._spd.value())
        s.setValue("volume", self._vol_slider.value())
        s.setValue("human_typing", self._chk_human.isChecked())
        s.setValue("font_size", self._fs_slider.value())
        s.setValue("vis_mode", self._vis_cb.currentText())
        s.setValue("vis_palette", self._pal_cb.currentText())
        s.setValue("vis_glow", self._chk_glow.isChecked())
        s.setValue("fps", self._fps_cb.currentText())
        s.setValue("quality", self._quality_cb.currentText())
        s.setValue("audio_bitrate", self._audio_bitrate_cb.currentText())
        s.setValue("res", self._export_res_cb.currentText())
        s.setValue("aspect", self._aspect_cb.currentText())
        s.setValue("render_vis", self._chk_render_vis.isChecked())
        s.setValue("bg_gradient", self._chk_bg_gradient.isChecked())

    def _load_code(self) -> None:
        if self._fp and Path(self._fp).is_file():
            try: self._code = Path(self._fp).read_text(encoding="utf-8")
            except Exception: self._code = DEFAULT_CODE
        else:
            self._code = DEFAULT_CODE

    def _wave_set_levels(self, levels: list) -> None: self._wave.set_audio_levels(levels)

    def _on_audio_ready_changed(self, ready: bool) -> None:
        if ready:
            self._b_start.setEnabled(True)
            self.statusBar().showMessage("Ready | F5 = start | Ctrl+E = export | Esc = reset")
        else:
            self._b_start.setEnabled(False)
            self.statusBar().showMessage("Audio engine not ready…")

    def _on_audio_play_failed(self, message: str) -> None:
        log.error("Play failed (user-visible): %s", message)
        self._b_start.setEnabled(self._audio.is_ready())
        QMessageBox.critical(self, "Audio Error", message)

    def _on_audio_status_message(self, msg: str) -> None: self.statusBar().showMessage(msg)

    def _on_volume(self, v: int) -> None: self._audio.set_volume(v); self._schedule_save()

    def _on_font_size(self, v: int) -> None:
        f = self._editor.font(); f.setPointSize(v)
        self._editor.setFont(f)
        self._editor._update_line_number_area_width(0)
        self._schedule_save()

    def _on_speed(self, v: int) -> None:
        self._spd_lbl.setText(f"{v} ms")
        self._typing_engine.set_speed(v)
        self._schedule_save()

    def _on_human_toggle(self, on: bool) -> None: self._typing_engine.set_human(on); self._schedule_save()

    def _on_palette_changed(self, name: str) -> None: self._wave.set_palette(name); self._schedule_save()

    def _toggle_rec_dot(self) -> None: self._rec_dot.setVisible(not self._rec_dot.isVisible())

    def _open_file(self) -> None:
        last_dir = self._settings.value("last_dir", str(INPUT_DIR))
        p, _ = QFileDialog.getOpenFileName(
            self, "Open Strudel File", last_dir, "Strudel (*.strudel *.js);;All (*)",
        )
        if not p: return
        self._settings.setValue("last_dir", str(Path(p).parent))
        try: self._code = Path(p).read_text(encoding="utf-8")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read file:\n{e}")
            return
        self._fp = p
        self._reset()

    def _start(self) -> None:
        if self._typing_engine.running: return
        if not self._code.strip(): return QMessageBox.warning(self, "Empty", "No code loaded to type.")

        self._audio.notify_user_gesture()
        self._editor.setPlainText("")
        self._typing_engine.set_code(self._code)
        self._b_start.setEnabled(False)
        self._b_export.setEnabled(False)
        self._audio.set_volume(self._vol_slider.value())
        self._audio.play(self._code)
        self._typing_engine.start()
        self._wave.set_playing(True)
        self._audio_poll_timer.start()

    def _on_typed(self, chunk: str) -> None: self._editor.append_chars(chunk)

    def _on_typing_progress(self, pct: int) -> None: self._prog.setText(f"Typing… {pct}%")

    def _on_typing_finished(self) -> None:
        self._audio_poll_timer.stop()
        if not self._exporting:
            self._b_start.setEnabled(self._audio.is_ready())
            self._b_export.setEnabled(True)
            self._prog.setText("Complete")
        else:
            if self._export_dialog:
                self._export_dialog.set_progress(100, "Holding final frame…")
            QTimer.singleShot(FINAL_HOLD_MS, self._finish_export)

    def _pause(self) -> None:
        if not self._typing_engine.running: return
        self._typing_engine.pause()
        if self._typing_engine.paused:
            self._b_pause.setText("Resume")
            self._wave.set_playing(False)
            self._audio_poll_timer.stop()
        else:
            self._b_pause.setText("Pause")
            self._wave.set_playing(True)
            self._audio_poll_timer.start()

    def _reset(self) -> None:
        self._typing_engine.stop()
        self._frame_timer.stop()
        self._audio_poll_timer.stop()
        self._audio.stop()
        self._exporting = False
        self._rec_dot.setVisible(False)
        self._rec_blink_timer.stop()
        self._editor.setPlainText("")
        self._wave.set_playing(False)
        self._b_pause.setText("Pause")
        self._b_start.setEnabled(self._audio.is_ready())
        self._b_export.setEnabled(True)
        self._prog.setText("Ready")

    def _export_mp4(self) -> None:
        if not HAS_FFMPEG:
            return QMessageBox.critical(self, "Error", "FFmpeg is not installed or not in PATH.")
        last_dir = self._settings.value("last_dir", str(OUTPUT_DIR))
        if self._fp: default_name = f"{Path(self._fp).stem}.mp4"
        else: default_name = f"strudel_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Export MP4", str(Path(last_dir) / default_name), "MP4 Video (*.mp4)",
        )
        if not out_path: return
        self._settings.setValue("last_dir", str(Path(out_path).parent))
        self._batch_mode = False
        self._begin_export_for_code(self._code, out_path)

    def _start_batch(self) -> None:
        if not HAS_FFMPEG:
            return QMessageBox.critical(self, "Error", "FFmpeg is not installed or not in PATH.")
        last_dir = self._settings.value("last_dir", str(INPUT_DIR))
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Strudel Files", last_dir, "Strudel (*.strudel *.js);;All (*)",
        )
        if not files: return
        self._settings.setValue("last_dir", str(Path(files[0]).parent))
        out_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory", str(OUTPUT_DIR))
        if not out_dir: return
        skip_audio = (
            QMessageBox.question(
                self, "Audio", "Include audio in batch exports? (Slower)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            ) == QMessageBox.StandardButton.No
        )

        self._batch_processor = BatchProcessor(files, out_dir, skip_audio=skip_audio)
        self._batch_dialog = BatchProgressDialog(self)
        self._batch_dialog.populate_files(files)
        self._batch_processor.file_started.connect(self._on_batch_file_started)
        self._batch_processor.file_progress.connect(self._batch_dialog.on_file_progress)
        self._batch_processor.file_finished.connect(self._on_batch_file_finished)
        self._batch_processor.batch_finished.connect(self._on_batch_finished)
        self._batch_mode = True
        self._batch_dialog.show()
        self._b_export.setEnabled(False)
        self._b_batch.setEnabled(False)
        self._b_load.setEnabled(False)
        self._batch_processor.start()

    def _on_batch_file_started(self, idx: int, total: int, filepath: str) -> None:
        if self._batch_dialog: self._batch_dialog.on_file_started(idx, total, filepath)
        try: code = Path(filepath).read_text(encoding="utf-8")
        except Exception as e:
            self._batch_processor.notify_file_done(False, str(e)); return
        out_path = self._batch_processor.output_path_for(filepath)
        self._begin_export_for_code(code, out_path)

    def _on_batch_file_finished(self, filepath: str, success: bool, message: str) -> None:
        if self._batch_dialog: self._batch_dialog.on_file_finished(filepath, success, message)
        if self._batch_processor: self._batch_processor.notify_file_done(success, message)

    def _on_batch_finished(self, succeeded: int, failed: int) -> None:
        if self._batch_dialog: self._batch_dialog.on_batch_finished(succeeded, failed)
        self._b_export.setEnabled(True)
        self._b_batch.setEnabled(True)
        self._b_load.setEnabled(True)
        self._batch_mode = False

    def _build_export_config(self) -> ExportConfig:
        w, h = RESOLUTIONS.get(self._export_res_cb.currentText(), (1920, 1080))
        return ExportConfig(
            width=w, height=h,
            fps=int(self._fps_cb.currentText()),
            crf=int(self._quality_cb.currentText().split("(")[1].split(")")[0]),
            audio_bitrate=self._audio_bitrate_cb.currentText(),
            aspect=AspectMode(self._aspect_cb.currentText()),
            include_visualizer=self._chk_render_vis.isChecked(),
            gradient_background=self._chk_bg_gradient.isChecked(),
        )

    def _begin_export_for_code(self, code: str, output_path: str) -> None:
        if self._writer_thread is not None:
            log.warning("Export already in progress — ignoring request"); return

        self._audio.notify_user_gesture()
        self._code = code
        self._audio_file = str(TEMP_DIR / f"audio_{datetime.now().strftime('%H%M%S%f')}.webm")
        self._export_out_path = output_path
        self._export_cancelled = False
        self._editor.setPlainText("")
        self._typing_engine.set_code(self._code)
        self._exporting = True

        cfg = self._build_export_config()
        self._export_cfg = cfg

        self._writer_thread = QThread(self)
        self._writer_worker = VideoWriterWorker(cfg, output_path)
        self._writer_worker.moveToThread(self._writer_thread)
        self._writer_thread.started.connect(self._writer_worker.run)
        self._writer_worker.finished_ok.connect(self._on_export_finished_ok)
        self._writer_worker.failed.connect(self._on_export_failed)
        self._writer_worker.progress.connect(self._on_export_progress)
        self._writer_worker.frame_dropped.connect(self._on_frame_dropped)
        self._writer_thread.start()

        if not self._batch_mode:
            self._export_dialog = ExportProgressDialog(self)
            self._export_dialog.cancel_requested.connect(self._on_export_cancel)
            self._export_dialog.show()
            self._export_dialog.set_progress(0, "Recording frames…")

        self._rec_dot.setVisible(True)
        self._rec_blink_timer.start(REC_BLINK_MS)

        if self._batch_processor and self._batch_processor.skip_audio:
            self._audio_recording = False
        else:
            self._start_web_audio_recording()

        self._audio.set_volume(self._vol_slider.value())
        self._audio.play(self._code)

        QTimer.singleShot(200, self._typing_engine.start)
        self._wave.set_playing(True)
        self._audio_poll_timer.start()
        self._frame_timer.start(cfg.frame_interval_ms)

    def _on_export_cancel(self) -> None:
        self._export_cancelled = True
        self._typing_engine.stop()
        self._audio.stop()
        self._audio_poll_timer.stop()
        self._finish_export()

    def _start_web_audio_recording(self) -> None:
        self._audio_recording = True
        self._audio.start_recording(lambda s: log.info("Recording started: %s", s))

    def _capture_frame(self) -> None:
        if not self._exporting or not self._writer_worker or not self._export_cfg: return
        try:
            cfg = self._export_cfg
            pixmap = QPixmap(cfg.width, cfg.height)
            pixmap.fill(QColor(C["mantle"]))

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

            if cfg.gradient_background:
                grad = QLinearGradient(0, 0, 0, cfg.height)
                grad.setColorAt(0.0, QColor(C["crust"]))
                grad.setColorAt(1.0, QColor(C["mantle"]))
                painter.fillRect(0, 0, cfg.width, cfg.height, grad)

            widget = self._capture_widget
            src_w, src_h = widget.width(), widget.height()
            mode = cfg.aspect

            if mode is AspectMode.STRETCH:
                scale_w = cfg.width / src_w; scale_h = cfg.height / src_h
                painter.scale(scale_w, scale_h)
            else:
                if mode is AspectMode.FILL:
                    scale = max(cfg.width / src_w, cfg.height / src_h)
                else:
                    scale = min(cfg.width / src_w, cfg.height / src_h)
                tx = (cfg.width - src_w * scale) / 2
                ty = (cfg.height - src_h * scale) / 2
                painter.translate(tx, ty)
                painter.scale(scale, scale)

            widget.render(painter, flags=QWidget.RenderFlag.DrawChildren)
            painter.end()

            image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGB888)
            ptr = image.constBits()
            ptr.setsize(image.sizeInBytes())

            bpl = image.bytesPerLine()
            needed = cfg.width * 3
            if bpl == needed:
                frame_bytes = bytes(ptr)
            elif HAS_NUMPY:
                arr = np.frombuffer(ptr, dtype=np.uint8, count=image.sizeInBytes())
                frame_bytes = arr.reshape(cfg.height, bpl)[:, :needed].tobytes()
            else:
                buf = bytearray(cfg.height * needed)
                for y in range(cfg.height):
                    start = y * bpl
                    buf[y * needed:(y + 1) * needed] = ptr[start:start + needed]
                frame_bytes = bytes(buf)

            self._writer_worker.add_frame(frame_bytes)

            pct = self._typing_engine.progress_pct
            msg = f"Recording… {pct}%"
            if self._export_dialog: self._export_dialog.set_progress(pct, msg)
            if self._batch_mode and self._batch_processor: self._batch_processor.file_progress.emit(msg)
        except Exception as e:
            log.error("Capture failed: %s", e)

    def _on_frame_dropped(self, count: int) -> None:
        if self._export_dialog and count % 10 == 0:
            self._export_dialog.set_progress(
                self._typing_engine.progress_pct, f"Recording… (dropped {count} frames)",
            )

    def _finish_export(self) -> None:
        self._frame_timer.stop()
        self._typing_engine.stop()
        self._audio_poll_timer.stop()
        self._audio.stop()
        self._exporting = False
        self._rec_dot.setVisible(False)
        self._rec_blink_timer.stop()

        def on_audio_data(data_url: Optional[str]) -> None:
            size = decode_audio_data_url(data_url, self._audio_file) if data_url else 0
            if size == 0: self._audio_file = None
            if self._writer_worker:
                if self._export_cancelled: self._writer_worker.cancel()
                else: self._writer_worker.finish_and_mux(self._audio_file)

        if self._audio_recording:
            self._audio_recording = False
            self._audio.stop_recording(on_audio_data)
        elif self._writer_worker:
            if self._export_cancelled: self._writer_worker.cancel()
            else: self._writer_worker.finish_and_mux(None)

    def _on_export_progress(self, msg: str) -> None:
        if self._export_dialog: self._export_dialog.set_progress(100, msg)
        if self._batch_mode and self._batch_processor: self._batch_processor.file_progress.emit(msg)

    def _teardown_writer(self) -> None:
        thread, worker = self._writer_thread, self._writer_worker
        self._writer_thread = None
        self._writer_worker = None
        self._export_cfg = None
        if thread:
            thread.quit()
            if not thread.wait(2000):
                log.warning("Writer thread did not quit cleanly — terminating")
                thread.terminate(); thread.wait(1000)
            if worker: worker.deleteLater()
            thread.deleteLater()

    def _on_export_finished_ok(self, out_path: str) -> None:
        self._teardown_writer()
        if self._export_dialog: self._export_dialog.set_complete(f"Saved to {out_path}")
        if self._batch_mode and self._batch_processor:
            self._batch_processor.notify_file_done(True, f"Saved to {out_path}")
        else:
            self._b_start.setEnabled(self._audio.is_ready())
            self._b_export.setEnabled(True)
            self._b_batch.setEnabled(True)

    def _on_export_failed(self, err: str) -> None:
        log.error("Export failed: %s", err)
        self._teardown_writer()
        if self._export_dialog: self._export_dialog.set_failed(err)
        if self._batch_mode and self._batch_processor:
            self._batch_processor.notify_file_done(False, err)
        else:
            self._b_start.setEnabled(self._audio.is_ready())
            self._b_export.setEnabled(True)
            self._b_batch.setEnabled(True)

    def closeEvent(self, ev) -> None:
        self._save_settings()
        self._teardown_writer()
        self._audio.cleanup()
        super().closeEvent(ev)