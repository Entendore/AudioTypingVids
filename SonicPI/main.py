from __future__ import annotations
import sys, json, os, shutil, platform, subprocess
from pathlib import Path
from typing import List, Optional
import numpy as np
from PySide6.QtCore import Qt, QTimer, QUrl, QTime
from PySide6.QtGui import QPainter, QFont, QSyntaxHighlighter, QTextCharFormat, QColor
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QPushButton, QProgressBar, QStatusBar, QFileDialog, QMessageBox,
                               QPlainTextEdit, QComboBox, QToolButton, QLabel, QSlider, QSplitter,
                               QDockWidget, QDoubleSpinBox, QCheckBox)
import logging

from core import AudioEngineConfig, FrameState, SR, ThemeRegistry, PresetRegistry, tokenize_ruby_line, TOKEN_COLOR_MAP
from audio_engine import SonicPiManager, AudioPreviewWorker, ExportWorker, precompute, save_wav, TMP_AUDIO_DIR
from renderer import FrameRenderer

APP_ROOT = Path(__file__).resolve().parent
SETTINGS_DIR = APP_ROOT / ".sonic_pi_anim"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"
LOG_PATH = SETTINGS_DIR / "app.log"
INPUT_DIR = APP_ROOT / "input"

SETTINGS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH, mode='w', encoding='utf-8'),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

def _ensure_firewall_rules():
    if platform.system() != "Windows": return
    ruby = r"C:\Program Files\Sonic Pi\app\server\native\ruby\bin\ruby.exe"
    scsynth = r"C:\Program Files\Sonic Pi\app\server\native\scsynth.exe"
    for exe in (ruby, scsynth):
        if not os.path.exists(exe): continue
        try:
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "add", "rule",
                 f"name=SonicPi_{os.path.basename(exe)}",
                 "dir=in", "action=allow", f"program={exe}", "enable=yes",
                 "protocol=UDP"],
                capture_output=True, check=False
            )
        except Exception:
            pass

class RubyHighlighter(QSyntaxHighlighter):
    def __init__(self, document, theme):
        super().__init__(document)
        self.theme = theme
        self._build_formats()

    def _build_formats(self):
        self._fmts = {}
        for kind, key in TOKEN_COLOR_MAP.items():
            fmt = QTextCharFormat()
            c = getattr(self.theme, key)
            fmt.setForeground(QColor(c[0], c[1], c[2]))
            if key == "kw":
                fmt.setFontWeight(QFont.Weight.Bold)
            self._fmts[kind] = fmt

    def set_theme(self, theme):
        self.theme = theme
        self._build_formats()
        self.rehighlight()

    def highlightBlock(self, text: str):
        idx = 0
        for tok in tokenize_ruby_line(text):
            fmt = self._fmts.get(tok.kind)
            if fmt:
                self.setFormat(idx, len(tok.text), fmt)
            idx += len(tok.text)

class AnimWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.renderer = FrameRenderer()
        self.setMinimumSize(400, 250)
    def set_data(self, code: str, frames: List[FrameState], total_time: float = 0.0):
        self.renderer.set_data(code, frames, total_time); self.update()
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.renderer.draw_live(p, self.width(), self.height(), self.renderer.cf)
        p.end()

class MainWindow(QMainWindow):
    def __init__(self, cfg: AudioEngineConfig, sp: SonicPiManager):
        super().__init__()
        self.cfg = cfg; self.sonic_pi = sp
        self.setWindowTitle("Sonic Pi Animation Studio")
        self.resize(1280, 720)
        
        self._playing = False; self._frame_idx = 0; self._frames = []; self._total_dur = 0.0
        self._current_code = ""; self._current_audio: Optional[np.ndarray] = None; self._export_audio: Optional[np.ndarray] = None
        self._current_audio_path = ""; self._is_exporting = False
        
        self._preview_worker: Optional[AudioPreviewWorker] = None
        self._export_worker: Optional[ExportWorker] = None
        
        self.player = QMediaPlayer(); self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output); self.audio_output.setVolume(self.cfg.master_volume)
        
        # FIX: Connect signals only once to prevent memory leaks and duplicate UI updates
        self.player.positionChanged.connect(self._on_pos_changed)
        self.player.durationChanged.connect(self._on_dur_changed)
        
        self.timer = QTimer(); self.timer.setInterval(int(1000 / 30))
        self.timer.timeout.connect(self._tick)
        
        self._build_ui()
        self._load_settings()
        self._load_input_scripts()
        self.anim.renderer.apply_config(self.cfg)
        self.highlighter.set_theme(ThemeRegistry.get(self.cfg.theme_name))

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QVBoxLayout(central)
        
        toolbar = QHBoxLayout()
        self.file_combo = QComboBox()
        self.file_combo.addItem("— select script —")
        self.file_combo.currentIndexChanged.connect(self._load_script_file)
        toolbar.addWidget(QLabel("Script:"))
        toolbar.addWidget(self.file_combo, 1)
        
        self.browse_btn = QToolButton(); self.browse_btn.setText("📂 Browse")
        self.browse_btn.clicked.connect(self._browse_scripts)
        toolbar.addWidget(self.browse_btn)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(ThemeRegistry.names())
        self.theme_combo.setCurrentText(self.cfg.theme_name)
        self.theme_combo.currentTextChanged.connect(self._change_theme)
        toolbar.addWidget(QLabel("Theme:"))
        toolbar.addWidget(self.theme_combo)
        
        self.settings_btn = QPushButton("⚙ Settings")
        self.settings_btn.clicked.connect(self._toggle_settings)
        toolbar.addWidget(self.settings_btn)
        root.addLayout(toolbar)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.code_edit = QPlainTextEdit()
        self.code_edit.setFont(QFont("Consolas", 11))
        self.code_edit.setPlainText("use_bpm 60\nlive_loop :test do\n  play :C4\n  sleep 1\nend")
        self.highlighter = RubyHighlighter(self.code_edit.document(), ThemeRegistry.default())
        splitter.addWidget(self.code_edit)
        
        self.anim = AnimWidget()
        splitter.addWidget(self.anim)
        splitter.setSizes([400, 800])
        root.addWidget(splitter, 1)
        
        audio_ctrl = QHBoxLayout()
        self.play_btn = QPushButton("▶ Play"); self.play_btn.clicked.connect(self._play); audio_ctrl.addWidget(self.play_btn)
        self.stop_btn = QPushButton("⬛ Stop"); self.stop_btn.clicked.connect(self._stop); audio_ctrl.addWidget(self.stop_btn)
        self.preview_btn = QPushButton("🎬 Generate Audio"); self.preview_btn.clicked.connect(self._generate_audio); audio_ctrl.addWidget(self.preview_btn)
        self.export_btn = QPushButton("📹 Export MP4"); self.export_btn.clicked.connect(self._export); audio_ctrl.addWidget(self.export_btn)
        
        self.audio_slider = QSlider(Qt.Orientation.Horizontal)
        self.audio_slider.setRange(0, 1000)
        self.audio_slider.sliderMoved.connect(self._seek_audio)
        audio_ctrl.addWidget(self.audio_slider, 1)
        
        self.time_label = QLabel("00:00 / 00:00")
        audio_ctrl.addWidget(self.time_label)
        
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(int(self.cfg.master_volume * 100))
        self.vol_slider.valueChanged.connect(self._change_vol)
        audio_ctrl.addWidget(QLabel("Vol:"))
        audio_ctrl.addWidget(self.vol_slider)
        root.addLayout(audio_ctrl)
        
        self.progress = QProgressBar(); self.progress.setVisible(False); root.addWidget(self.progress)
        self.status_bar = QStatusBar(); self.setStatusBar(self.status_bar)
        
        self.settings_dock = QDockWidget("Settings", self)
        self.settings_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        settings_widget = self._build_settings_widget()
        self.settings_dock.setWidget(settings_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.settings_dock)
        self.settings_dock.hide()

    def _build_settings_widget(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("Preset:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(PresetRegistry.names())
        self.preset_combo.setCurrentText(self.cfg.preset_name)
        self.preset_combo.currentTextChanged.connect(self._update_cfg)
        layout.addWidget(self.preset_combo)
        layout.addWidget(QLabel("Typing Speed:"))
        self.ts_spin = QDoubleSpinBox()
        self.ts_spin.setRange(1.0, 100.0)
        self.ts_spin.setValue(self.cfg.typing_speed)
        self.ts_spin.valueChanged.connect(self._update_cfg)
        layout.addWidget(self.ts_spin)
        for attr, text in [
            ("match_typing_to_music", "Match typing to music"),
            ("particles_enabled", "Particles Enabled"),
            ("mirror_waveform", "Mirror Waveform"),
            ("fill_waveform", "Fill Waveform"),
            ("vu_meter", "VU Meter"),
            ("show_spectrum", "Show Spectrum"),
            ("show_code_glow", "Code Glow"),
            ("beat_flash", "Beat Flash"),
            ("show_progress_bar", "Progress Bar")
        ]:
            cb = QCheckBox(text)
            cb.setChecked(getattr(self.cfg, attr))
            cb.toggled.connect(lambda checked, a=attr: self._update_cfg_attr(a, checked))
            layout.addWidget(cb)
        layout.addStretch(1)
        return w

    def _update_cfg_attr(self, attr, value):
        setattr(self.cfg, attr, value)
        self.anim.renderer.apply_config(self.cfg)
        self.anim.update()
        self._save_settings()

    def _update_cfg(self):
        self.cfg.preset_name = self.preset_combo.currentText()
        self.cfg.typing_speed = self.ts_spin.value()
        self.anim.renderer.apply_config(self.cfg)
        self.anim.update()
        self._save_settings()

    def _toggle_settings(self):
        self.settings_dock.setVisible(not self.settings_dock.isVisible())

    def _change_theme(self, name):
        self.cfg.theme_name = name
        self.highlighter.set_theme(ThemeRegistry.get(name))
        self.anim.renderer.apply_config(self.cfg)
        self.anim.update()
        self._save_settings()

    def _change_vol(self, v):
        self.cfg.master_volume = v / 100.0
        self.audio_output.setVolume(self.cfg.master_volume)
        self._save_settings()

    def _seek_audio(self, v):
        if self.player.duration() > 0:
            self.player.setPosition(int(v / 1000 * self.player.duration()))

    def _load_input_scripts(self):
        self.file_combo.clear()
        self.file_combo.addItem("— select script —")
        if INPUT_DIR.exists():
            for f in sorted(INPUT_DIR.glob("*.rb")):
                self.file_combo.addItem(str(f))

    def _browse_scripts(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Sonic Pi script", "", "Ruby (*.rb);;All files (*)")
        if path:
            try:
                INPUT_DIR.mkdir(parents=True, exist_ok=True)
                dest_path = INPUT_DIR / Path(path).name
                shutil.copy2(path, dest_path)
                self._load_input_scripts()
                self.file_combo.setCurrentText(str(dest_path))
            except Exception as e:
                logger.error(f"Failed to copy script: {e}")
                QMessageBox.warning(self, "File Error", f"Could not copy file to input folder:\n{e}")

    def _load_script_file(self, idx):
        if idx > 0:
            path = self.file_combo.itemText(idx)
            if Path(path).exists():
                self.code_edit.setPlainText(Path(path).read_text())

    def _generate_audio(self):
        self._current_code = self.code_edit.toPlainText()
        logger.info("Generating audio for code (%d chars)", len(self._current_code))
        self.status_bar.showMessage("Booting Sonic Pi and generating audio...")
        self.progress.setVisible(True); self.progress.setValue(0)
        
        self._preview_worker = AudioPreviewWorker(self._current_code, self.sonic_pi, self.cfg.base_duration)
        self._preview_worker.progress.connect(lambda c,t,m: self.progress.setValue(c))
        self._preview_worker.finished.connect(self._on_audio_ready)
        self._preview_worker.error.connect(self._on_error)
        self._preview_worker.start()

    def _on_audio_ready(self, audio: np.ndarray, duration: float, code: str):
        logger.info("Audio ready: duration=%.2fs, samples=%d", duration, len(audio))
        self.progress.setVisible(False)
        self._export_audio = audio
        self._current_audio = audio[:int(self.cfg.base_duration * SR)].copy() 
        
        wav_path = TMP_AUDIO_DIR / "preview.wav"
        wav_path.parent.mkdir(exist_ok=True, parents=True)
        save_wav(self._current_audio, wav_path)
        self._current_audio_path = str(wav_path)
        self.player.setSource(QUrl.fromLocalFile(str(wav_path)))
        self.player.setLoops(QMediaPlayer.Loops.Infinite)
        
        self._frames, self._total_dur = precompute(self._current_code, self._current_audio, duration, self.cfg)
        self.anim.set_data(self._current_code, self._frames, self._total_dur)
        self.status_bar.showMessage("Audio ready. Press Play.")
        self._play()

    def _on_pos_changed(self, pos):
        if self.player.duration() > 0:
            self.audio_slider.setValue(int(pos / self.player.duration() * 1000))
        cur = QTime(0, 0).addMSecs(pos)
        total = QTime(0, 0).addMSecs(self.player.duration())
        self.time_label.setText(f"{cur.toString('mm:ss')} / {total.toString('mm:ss')}")

    def _on_dur_changed(self, dur):
        total = QTime(0, 0).addMSecs(dur)
        self.time_label.setText(f"00:00 / {total.toString('mm:ss')}")

    def _play(self):
        if not self._frames: return
        if self._playing:
            self.timer.stop(); self._playing = False; self.play_btn.setText("▶ Play"); self.player.pause()
        else:
            self.timer.start(); self._playing = True; self.play_btn.setText("⏸ Pause"); self.player.play()

    def _stop(self):
        self.timer.stop(); self._playing = False; self._frame_idx = 0
        self.play_btn.setText("▶ Play"); self.player.stop()

    def _tick(self):
        if not self._frames: self.timer.stop(); return
        self.anim.renderer.cf = self._frame_idx; self.anim.update()
        self._frame_idx = (self._frame_idx + 1) % len(self._frames)

    def _export(self):
        if self._export_audio is None: QMessageBox.warning(self, "Error", "Generate audio first."); return
        path, _ = QFileDialog.getSaveFileName(self, "Export MP4", "output.mp4", "MP4 (*.mp4)")
        if not path: return
        
        self._is_exporting = True; self.progress.setVisible(True); self.progress.setValue(0)
        renderer = self.anim.renderer.clone()
        self._export_worker = ExportWorker(path, renderer, self._current_code, self._export_audio, self.cfg)
        self._export_worker.progress.connect(lambda c,t,m: self.progress.setValue(c))
        self._export_worker.finished.connect(self._on_export_done)
        self._export_worker.start()

    def _on_export_done(self, path: str, success: bool, msg: str):
        self._is_exporting = False; self.progress.setVisible(False)
        if success: 
            logger.info("Export success: %s", path)
            QMessageBox.information(self, "Success", f"Saved to {path}")
        else: 
            logger.error("Export failed: %s", msg)
            QMessageBox.critical(self, "Error", msg)

    def _on_error(self, msg: str):
        logger.error("Worker error: %s", msg)
        self.progress.setVisible(False)
        QMessageBox.critical(self, "Error", msg)

    def _load_settings(self):
        if SETTINGS_PATH.exists():
            try:
                data = json.loads(SETTINGS_PATH.read_text())
                self.cfg = AudioEngineConfig.from_dict(data)
                self.theme_combo.setCurrentText(self.cfg.theme_name)
                self.vol_slider.setValue(int(self.cfg.master_volume * 100))
            except Exception as e:
                logger.error(f"Failed to load settings: {e}")

    def _save_settings(self):
        try:
            SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
            SETTINGS_PATH.write_text(json.dumps(self.cfg.to_dict(), indent=2))
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")

    def closeEvent(self, event):
        logger.info("Application shutting down")
        self._save_settings()
        if self.sonic_pi.process:
            try:
                self.sonic_pi.process.terminate()
                self.sonic_pi.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.sonic_pi.process.kill()
            except Exception:
                pass
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    
    _ensure_firewall_rules()
    
    logger.info("=" * 60)
    logger.info("Sonic Pi Animation Studio starting up")
    logger.info("Log file: %s", LOG_PATH)
    logger.info("Settings: %s", SETTINGS_PATH)
    logger.info("Input dir: %s", INPUT_DIR)
    logger.info("Temp Audio dir: %s", TMP_AUDIO_DIR)
    logger.info("=" * 60)
    
    cfg = AudioEngineConfig()
    sp = SonicPiManager()
    
    win = MainWindow(cfg, sp)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()