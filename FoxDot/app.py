import sys
import os
import re
import time
import subprocess
import threading
import numpy as np
import sounddevice as sd
import soundfile as sf
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPlainTextEdit, QPushButton, QFileDialog, QSlider, QLabel,
    QSpinBox, QStatusBar, QSplitter, QFrame, QComboBox
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QRect, QSize
from PySide6.QtGui import QFont, QColor, QSyntaxHighlighter, QTextCharFormat, QPainter, QImage

# Try importing FoxDot
try:
    from FoxDot import *
    FOXDOT_AVAILABLE = True
except ImportError:
    FOXDOT_AVAILABLE = False
    print("Warning: FoxDot not installed. Running in visual-only mode.")

# --- UI Components ---

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


class CodeEditor(QPlainTextEdit):
    """A text editor with line numbers and a blinking cursor."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.update_line_number_area_width(0)
        
        self.cursor_blink_timer = QTimer(self)
        self.cursor_blink_timer.timeout.connect(self.toggle_cursor_visibility)
        self.cursor_blink_timer.start(500)
        self.cursor_visible = True

    def line_number_area_width(self):
        digits = 1
        max_num = max(1, self.blockCount())
        while max_num >= 10:
            max_num /= 10
            digits += 1
        space = 3 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area.width(), cr.height()))

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#1E222A"))
        
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor("#5C6370"))
                painter.drawText(0, top, self.line_number_area.width() - 3, self.fontMetrics().height(),
                                 Qt.AlignRight, number)
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def toggle_cursor_visibility(self):
        self.cursor_visible = not self.cursor_visible
        self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.cursor_visible and not self.isReadOnly():
            rect = self.cursorRect()
            painter = QPainter(self.viewport())
            painter.fillRect(rect, QColor("#61AFEF"))


class FoxDotHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.fmt_keyword = QTextCharFormat()
        self.fmt_keyword.setForeground(QColor("#C678DD"))
        self.fmt_keyword.setFontWeight(QFont.Bold)
        
        self.fmt_string = QTextCharFormat()
        self.fmt_string.setForeground(QColor("#98C379"))
        
        self.fmt_comment = QTextCharFormat()
        self.fmt_comment.setForeground(QColor("#5C6370"))
        self.fmt_comment.setFontItalic(True)
        
        self.fmt_foxdot = QTextCharFormat()
        self.fmt_foxdot.setForeground(QColor("#E5C07B"))
        self.fmt_foxdot.setFontWeight(QFont.Bold)

        self.rules = []
        keywords = ["def", "class", "if", "else", "elif", "for", "while", "import", "from", "as", "return", "try", "except", "with", "var", "linvar", "expvar"]
        for word in keywords:
            self.rules.append((re.compile(r'\b' + word + r'\b'), self.fmt_keyword))
            
        foxdot_words = ["Clock", "Player", "Pattern", "P", "SuperCollider", "pluck", "bass", "play", "kick", "snap", "stretch", "loop", "sine", "saw"]
        for word in foxdot_words:
            self.rules.append((re.compile(r'\b' + word + r'\b'), self.fmt_foxdot))
            
        self.rules.append((re.compile(r'"[^"]*"'), self.fmt_string))
        self.rules.append((re.compile(r"'[^']*'"), self.fmt_string))
        self.rules.append((re.compile(r'#[^\n]*'), self.fmt_comment))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


class VUMeter(QWidget):
    """Simple audio VU meter widget."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.level = 0.0
        self.setFixedHeight(25)
        
    def set_level(self, level):
        self.level = max(0.0, min(1.0, level))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111417"))
        
        w = int(self.width() * self.level)
        if self.level < 0.6:
            color = QColor("#2ecc71") # Green
        elif self.level < 0.85:
            color = QColor("#f1c40f") # Yellow
        else:
            color = QColor("#e74c3c") # Red
            
        painter.fillRect(0, 0, w, self.height(), color)


# --- Threads & Logic ---

class TypingThread(QThread):
    char_typed = Signal(str)
    line_ready = Signal(str)
    typing_finished = Signal()

    def __init__(self, code_text, speed_ms=30):
        super().__init__()
        self.code_text = code_text
        self.speed_ms = speed_ms
        self._is_running = True
        self._is_paused = False

    def run(self):
        current_line = ""
        for char in self.code_text:
            if not self._is_running:
                break
            
            # Handle Pause/Resume
            while self._is_paused and self._is_running:
                self.msleep(100)
            
            self.char_typed.emit(char)
            current_line += char
            
            if char == '\n':
                self.line_ready.emit(current_line.strip())
                current_line = ""
                
            self.msleep(self.speed_ms)
            
        if current_line.strip():
            self.line_ready.emit(current_line.strip())
            
        self.typing_finished.emit()

    def stop(self):
        self._is_running = False

    def pause(self):
        self._is_paused = True

    def resume(self):
        self._is_paused = False


class VideoExporter:
    """Handles exporting to MP4 via FFmpeg."""
    def __init__(self, widget_to_record):
        self.widget = widget_to_record
        self.ffmpeg_proc = None
        self.is_exporting = False
        self.video_path = "temp_video.mp4"
        self.audio_path = "temp_audio.wav"
        self.final_path = ""
        self.audio_data = None
        
    def start(self, output_path, fps=30):
        self.final_path = output_path
        w = self.widget.width()
        h = self.widget.height()
        
        command = [
            'ffmpeg', '-y',
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{w}x{h}',
            '-pix_fmt', 'rgb24',
            '-r', str(fps),
            '-i', '-',
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-preset', 'ultrafast',
            self.video_path
        ]
        self.ffmpeg_proc = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        
        try:
            self.audio_data = sd.rec(int(44100 * 300), samplerate=44100, channels=2, dtype='float32')
        except Exception as e:
            print(f"Audio recording failed: {e}")
            self.audio_data = None
            
        self.is_exporting = True
        
    def capture_frame(self):
        if not self.is_exporting or not self.ffmpeg_proc:
            return
        pixmap = self.widget.grab()
        image = pixmap.toImage().convertToFormat(QImage.Format_RGB888)
        ptr = image.bits()
        ptr.setsize(image.sizeInBytes())
        self.ffmpeg_proc.stdin.write(ptr)
        
    def stop(self):
        if not self.is_exporting:
            return
        self.is_exporting = False
        
        if self.ffmpeg_proc:
            self.ffmpeg_proc.stdin.close()
            self.ffmpeg_proc.wait()
            
        valid_audio = False
        if self.audio_data is not None:
            try:
                sd.stop()
                valid_frames = np.where(np.any(self.audio_data != 0, axis=1))[0]
                if len(valid_frames) > 0:
                    trimmed = self.audio_data[:valid_frames[-1]+1]
                    sf.write(self.audio_path, trimmed, 44100)
                    valid_audio = True
            except Exception:
                pass
                    
        if os.path.exists(self.video_path):
            if valid_audio:
                mux_cmd = [
                    'ffmpeg', '-y',
                    '-i', self.video_path,
                    '-i', self.audio_path,
                    '-c:v', 'copy',
                    '-c:a', 'aac',
                    '-shortest',
                    self.final_path
                ]
            else:
                mux_cmd = ['ffmpeg', '-y', '-i', self.video_path, '-c:v', 'copy', self.final_path]
                
            subprocess.run(mux_cmd, stderr=subprocess.DEVNULL)
            
            if os.path.exists(self.video_path): os.remove(self.video_path)
            if os.path.exists(self.audio_path): os.remove(self.audio_path)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FoxDot Studio - Live Coder")
        self.resize(1400, 900) # Slightly larger to fit new UI
        
        self.typing_thread = None
        self.exporter = None
        self.frame_timer = QTimer()
        self.frame_timer.timeout.connect(self.capture_frame)
        self.code_buffer = ""
        self.current_file = None
        
        # VU Meter Audio Listener
        self.vu_timer = QTimer(self)
        self.vu_timer.timeout.connect(self.update_vu_meter)
        self.vu_timer.start(50)
        self.audio_stream = None
        
        self.init_ui()
        self.apply_dark_theme()
        self.init_audio_stream()
        self.update_status()
        
    def init_ui(self):
        # Central Widget that will be recorded for MP4
        self.central_recordable_widget = QWidget()
        self.setCentralWidget(self.central_recordable_widget)
        main_layout = QVBoxLayout(self.central_recordable_widget)
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Splitter for Code Editors
        splitter = QSplitter(Qt.Horizontal)
        
        self.source_editor = CodeEditor()
        self.source_editor.setPlaceholderText("Load or paste FoxDot code here...")
        self.highlighter_src = FoxDotHighlighter(self.source_editor.document())
        
        self.display_editor = CodeEditor()
        self.display_editor.setReadOnly(True)
        self.display_editor.setPlaceholderText("Typing animation will appear here...")
        self.highlighter_disp = FoxDotHighlighter(self.display_editor.document())
        
        splitter.addWidget(self.source_editor)
        splitter.addWidget(self.display_editor)
        main_layout.addWidget(splitter, stretch=1)
        
        # VU Meter
        self.vu_meter = VUMeter()
        main_layout.addWidget(self.vu_meter)
        
        # Controls
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)
        
        self.btn_load = QPushButton("Load Code")
        self.btn_load.clicked.connect(self.load_code)
        controls_layout.addWidget(self.btn_load)
        
        self.btn_save = QPushButton("Save Code")
        self.btn_save.clicked.connect(self.save_code)
        controls_layout.addWidget(self.btn_save)
        
        self.btn_example = QPushButton("Load Example")
        self.btn_example.clicked.connect(self.load_example)
        controls_layout.addWidget(self.btn_example)
        
        self.btn_start = QPushButton("Start Typing")
        self.btn_start.clicked.connect(self.start_typing)
        controls_layout.addWidget(self.btn_start)
        
        self.btn_pause = QPushButton("Pause")
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_pause.setEnabled(False)
        controls_layout.addWidget(self.btn_pause)
        
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.clicked.connect(self.stop_typing)
        controls_layout.addWidget(self.btn_stop)
        
        controls_layout.addStretch()
        
        # Speed Control
        controls_layout.addWidget(QLabel("Speed (ms):"))
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(5, 200)
        self.speed_slider.setValue(40)
        controls_layout.addWidget(self.speed_slider)
        
        # BPM Control
        controls_layout.addWidget(QLabel("BPM:"))
        self.bpm_spin = QSpinBox()
        self.bpm_spin.setRange(20, 300)
        self.bpm_spin.setValue(120)
        self.bpm_spin.valueChanged.connect(self.change_bpm)
        controls_layout.addWidget(self.bpm_spin)
        
        # Volume Control
        controls_layout.addWidget(QLabel("Vol:"))
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(75)
        self.vol_slider.valueChanged.connect(self.change_vol)
        controls_layout.addWidget(self.vol_slider)
        
        main_layout.addLayout(controls_layout)
        
        # Export Controls
        export_layout = QHBoxLayout()
        export_layout.addStretch()
        
        export_layout.addWidget(QLabel("Export FPS:"))
        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["30", "60"])
        export_layout.addWidget(self.fps_combo)
        
        self.btn_export = QPushButton("Export to MP4")
        self.btn_export.clicked.connect(self.export_mp4)
        self.btn_export.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; padding: 10px 20px;")
        export_layout.addWidget(self.btn_export)
        
        export_layout.addStretch()
        main_layout.addLayout(export_layout)
        
        # Console Log (Dock Widget, NOT recorded in video)
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumHeight(150)
        self.console.setStyleSheet("background-color: #111417; color: #AAAAAA; font-family: Consolas;")
        dock_layout = QVBoxLayout()
        dock_layout.addWidget(QLabel("Execution Console:"))
        dock_layout.addWidget(self.console)
        
        dock_widget = QWidget()
        dock_widget.setLayout(dock_layout)
        self.addDockWidget(Qt.BottomDockWidgetArea, self._wrap_dock(dock_widget))
        
    def _wrap_dock(self, widget):
        # Helper to wrap custom widget into a dock area cleanly
        from PySide6.QtWidgets import QDockWidget
        dock = QDockWidget("", self)
        dock.setWidget(widget)
        dock.setTitleBarWidget(QWidget()) # Hide title bar
        return dock

    def init_audio_stream(self):
        try:
            # Open a stream just for reading VU levels
            self.audio_stream = sd.InputStream(callback=self.audio_callback)
            self.audio_stream.start()
        except Exception:
            self.log("Could not open audio input for VU meter. Check system audio settings.")

    def audio_callback(self, indata, frames, time, status):
        if status:
            pass
        volume_norm = np.linalg.norm(indata) / 10
        self.current_vu_level = min(1.0, volume_norm)

    def update_vu_meter(self):
        if hasattr(self, 'current_vu_level'):
            self.vu_meter.set_level(self.current_vu_level)

    def apply_dark_theme(self):
        dark_stylesheet = """
            QMainWindow { background-color: #282C34; }
            QWidget { color: #ABB2BF; }
            QPlainTextEdit { 
                background-color: #1E222A; 
                color: #ABB2BF; 
                font-family: Consolas, Menlo, monospace; 
                font-size: 15px;
                border: none;
            }
            QPushButton {
                background-color: #3A3F4B;
                color: white;
                border: 1px solid #4B5263;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #4B5263; }
            QPushButton:disabled { background-color: #2D2D33; color: #555555; }
            QLabel { color: #ABB2BF; }
            QSlider::groove:horizontal { border: none; height: 4px; background: #3A3F4B; border-radius: 2px; }
            QSlider::handle:horizontal { background: #61AFEF; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }
            QSpinBox, QComboBox { background-color: #3A3F4B; color: white; border: 1px solid #4B5263; padding: 2px; }
            QStatusBar { background-color: #21252B; color: #ABB2BF; }
            QDockWidget { border-top: 1px solid #111417; }
        """
        self.setStyleSheet(dark_stylesheet)

    def log(self, message):
        self.console.appendPlainText(f"> {message}")
        self.console.verticalScrollBar().setValue(self.console.verticalScrollBar().maximum())

    def update_status(self, msg=None):
        sc_status = "Connected" if FOXDOT_AVAILABLE else "FoxDot Missing"
        rec_status = "Exporting..." if (self.exporter and self.exporter.is_exporting) else "Idle"
        if msg: rec_status = msg
        self.statusBar().showMessage(f"SuperCollider: {sc_status} | BPM: {Clock.bpm if FOXDOT_AVAILABLE else 'N/A'} | Status: {rec_status}")

    def load_code(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open FoxDot File", "", "Python/FoxDot Files (*.py *.foxdot)")
        if file_path:
            with open(file_path, 'r') as f:
                self.source_editor.setPlainText(f.read())
            self.current_file = file_path
            self.log(f"Loaded: {file_path}")

    def save_code(self):
        if not self.current_file:
            file_path, _ = QFileDialog.getSaveFileName(self, "Save FoxDot File", "untitled.py", "Python Files (*.py)")
            if file_path: self.current_file = file_path
            else: return
            
        with open(self.current_file, 'w') as f:
            f.write(self.source_editor.toPlainText())
        self.log(f"Saved to: {self.current_file}")

    def load_example(self):
        example = """# FoxDot Example: Ambient Groove
Clock.bpm = 90

# Set a soundfont piano
p1 >> pluck([0, 2, 4, 6, 4, 2], dur=[1, 0.5, 0.5, 1, 0.5, 0.5], amp=0.6, sus=2, oct=5)

# Add some bass
p2 >> bass([0, 0, 5, 5], dur=4, amp=0.8, oct=3)

# Add some percussive elements
p3 >> play("x-------o-------", amp=0.5)

# Change parameters live
p1.amp = var([0.6, 0.8, 0.4], 4)

# Stop everything
Clock.clear()
"""
        self.source_editor.setPlainText(example)
        self.current_file = None
        self.log("Loaded example code.")

    def change_bpm(self, bpm):
        if FOXDOT_AVAILABLE:
            Clock.bpm = bpm
        self.update_status()

    def change_vol(self, vol):
        if FOXDOT_AVAILABLE:
            v = vol / 100.0
            Clock.volume = v
        self.update_status()

    def start_typing(self):
        code = self.source_editor.toPlainText()
        if not code: return
            
        self.display_editor.clear()
        self.code_buffer = ""
        
        if FOXDOT_AVAILABLE:
            Clock.clear()
            
        speed = self.speed_slider.value()
        self.typing_thread = TypingThread(code, speed)
        self.typing_thread.char_typed.connect(self.on_char_typed)
        self.typing_thread.line_ready.connect(self.execute_foxdot_line)
        self.typing_thread.typing_finished.connect(self.on_typing_finished)
        self.typing_thread.start()
        
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_pause.setText("Pause")
        self.btn_export.setEnabled(False)

    def toggle_pause(self):
        if not self.typing_thread: return
        if self.typing_thread._is_paused:
            self.typing_thread.resume()
            self.btn_pause.setText("Pause")
            self.log("Typing resumed.")
        else:
            self.typing_thread.pause()
            self.btn_pause.setText("Resume")
            self.log("Typing paused.")

    def stop_typing(self):
        if self.typing_thread and self.typing_thread.isRunning():
            self.typing_thread.stop()
            self.typing_thread.wait()
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_export.setEnabled(True)
        if self.exporter and self.exporter.is_exporting:
            self.finalize_export()

    def on_char_typed(self, char):
        cursor = self.display_editor.textCursor()
        cursor.insertText(char)
        self.display_editor.setTextCursor(cursor)
        self.display_editor.ensureCursorVisible()

    def execute_foxdot_line(self, line):
        if not FOXDOT_AVAILABLE or not line: return
            
        self.code_buffer += line + "\n"
        try:
            compile(self.code_buffer, '<string>', 'exec')
            exec(self.code_buffer, globals())
            self.log(f"Executed: {line}")
            self.code_buffer = ""
        except SyntaxError:
            pass
        except Exception as e:
            self.log(f"Error: {e}")
            self.code_buffer = ""

    def on_typing_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_export.setEnabled(True)
        self.update_status("Typing complete.")
        if self.exporter and self.exporter.is_exporting:
            self.finalize_export()

    def export_mp4(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save MP4 Video", "foxdot_export.mp4", "MP4 Files (*.mp4)")
        if not file_path: return
        
        fps = int(self.fps_combo.currentText())
        # Record the entire main central widget (Code + Controls + VU Meter)
        self.exporter = VideoExporter(self.central_recordable_widget)
        self.exporter.start(file_path, fps=fps)
        self.frame_timer.start(1000 // fps)
        
        self.update_status("Starting export...")
        self.btn_export.setEnabled(False)
        self.btn_start.setEnabled(False)
        
        self.start_typing()

    def capture_frame(self):
        if self.exporter and self.exporter.is_exporting:
            self.exporter.capture_frame()

    def finalize_export(self):
        self.frame_timer.stop()
        self.update_status("Muxing video and audio. Please wait...")
        QApplication.processEvents()
        
        if self.exporter:
            self.exporter.stop()
            self.exporter = None
            
        self.btn_export.setEnabled(True)
        self.btn_start.setEnabled(True)
        self.update_status("Export complete!")
        self.log("MP4 Export complete.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())