import sys
import os
import time
import subprocess
import numpy as np
import soundfile as sf
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                               QPushButton, QLabel, QProgressBar, QPlainTextEdit, 
                               QSpinBox, QFormLayout, QFileDialog, QSlider, QCheckBox,
                               QComboBox)
from PySide6.QtCore import Qt, QThread, Signal, QRectF, QPointF, QRegularExpression, QUrl
from PySide6.QtGui import (QPainter, QColor, QFont, QImage, QTextCharFormat, 
                           QSyntaxHighlighter, QLinearGradient, QPainterPath, QPixmap)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from pygments.lexers import PythonLexer
from pygments.token import Token
from pythonosc.udp_client import SimpleUDPClient
import imageio.v2 as imageio
import imageio_ffmpeg

# Ensure input directory exists
INPUT_DIR = "input"
if not os.path.exists(INPUT_DIR):
    os.makedirs(INPUT_DIR)

DEFAULT_CODE = """from sardine import *

@swim
def techno_loop(d=0.5, i=0):
    # Kick drum
    D('bd', speed=1, pan=0.5, i=i)
    
    # Hi-Hat on offbeats
    if i % 2 == 0:
        D('hh', speed=2, pan=-0.5, i=i)
        
    # Bassline
    D('saw', freq=110, dur=0.2, i=i)
    
    again(techno_loop, d=0.5, i=i+1)
"""

# --- UI Syntax Highlighter ---
class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.rules = []
        
        # Keywords
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(255, 100, 150))
        fmt.setFontWeight(QFont.Weight.Bold)
        self.rules.append((QRegularExpression(r'\b(from|import|def|if|else|elif|for|while|return|class|with|as|try|except)\b'), fmt))
        
        # Functions
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(100, 200, 255))
        self.rules.append((QRegularExpression(r'\b[A-Za-z0-9_]+(?=\()'), fmt))
        
        # Strings
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(150, 255, 150))
        self.rules.append((QRegularExpression(r'".*?"'), fmt))
        self.rules.append((QRegularExpression(r"'.*?'"), fmt))
        
        # Comments
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(120, 120, 120))
        fmt.setFontItalic(True)
        self.rules.append((QRegularExpression(r'#[^\n]*'), fmt))
        
        # Numbers
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(180, 150, 255))
        self.rules.append((QRegularExpression(r'\b[0-9]+\b'), fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            matchIterator = pattern.globalMatch(text)
            while matchIterator.hasNext():
                match = matchIterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)

# --- Render Theme ---
THEME = {
    'bg': QColor(30, 30, 35),
    'line_number_bg': QColor(25, 25, 30),
    'text': QColor(220, 220, 220),
    'comment': QColor(100, 100, 120),
    'keyword': QColor(255, 100, 150),
    'string': QColor(150, 255, 150),
    'number': QColor(180, 150, 255),
    'func': QColor(100, 200, 255),
    'terminal_bar': QColor(45, 45, 50),
    'cursor': QColor(0, 255, 150)
}

class RenderWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    preview = Signal(QImage)
    audio_ready = Signal(str)  # Emits path to temp audio for playback
    finished = Signal(bool, str)

    def __init__(self, code, duration, fps, output_file, typing_speed, keystroke_sounds, viz_mode, viz_size, viz_decay):
        super().__init__()
        self.code = code
        self.duration = duration
        self.fps = fps
        self.output_file = output_file
        self.typing_speed = typing_speed
        self.keystroke_sounds = keystroke_sounds
        
        # Viz Settings
        self.viz_mode = viz_mode
        self.viz_size = viz_size / 100.0
        self.viz_decay = viz_decay / 100.0
        
        self.temp_video = "_temp_video.mp4"
        self.temp_audio = "_temp_audio.wav"
        self.osc_client = SimpleUDPClient("127.0.0.1", 57110)
        
        self.tokens = list(PythonLexer().get_tokens(self.code))
        self.font_code = QFont("Consolas", 14)
        self.font_code.setStyleHint(QFont.StyleHint.Monospace)
        self.font_ui = QFont("Arial", 10)
        
        self.typing_timeline = self._build_typing_timeline()
        
        # Animation State
        self.current_cursor_x = 60.0
        self.current_cursor_y = 74.0
        self.spectrum_peaks = np.zeros(64)

    def _build_typing_timeline(self):
        timeline = []
        current_time = 0.0
        typing_duration = (self.duration * 0.7) / self.typing_speed 
        
        for char in self.code:
            timeline.append(current_time)
            if char in (' ', '\t'): current_time += 0.05
            elif char == '\n': current_time += 0.15
            elif char in ('(', ')', ','): current_time += 0.08
            else: current_time += 0.045
            
        if current_time > 0:
            scale = typing_duration / current_time
            timeline = [t * scale for t in timeline]
        return timeline

    def run(self):
        # PASS 1: Record Sardine Audio
        self.status.emit("Pass 1: Recording Sardine Audio...")
        audio_success = self._record_audio()
        
        # Load Audio
        if os.path.exists(self.temp_audio):
            audio_data, sr = sf.read(self.temp_audio)
            if audio_data.ndim > 1: audio_data = audio_data[:, 0]
        else:
            self.status.emit("Sardine failed. Using silent track...")
            sr = 44100
            audio_data = np.zeros(int(self.duration * sr))

        # Mix Keystroke Sounds
        if self.keystroke_sounds:
            self.status.emit("Mixing keystroke sounds...")
            audio_data = self._mix_keystrokes(audio_data, sr)

        sf.write(self.temp_audio, audio_data, sr)
        self.audio_data = audio_data
        self.audio_samplerate = sr

        # Emit signal to start audio playback in the main UI thread
        self.audio_ready.emit(self.temp_audio)

        # PASS 2: Render Video Frames
        self.status.emit("Pass 2: Rendering Video Frames...")
        width, height = 1280, 720
        
        try:
            writer = imageio.get_writer(self.temp_video, fps=self.fps, codec='libx264', quality=9, macro_block_size=1)
            total_frames = int(self.duration * self.fps)
            
            for frame_num in range(total_frames):
                t = frame_num / self.fps
                img = QImage(width, height, QImage.Format.Format_RGB32)
                img.fill(Qt.GlobalColor.black)
                
                painter = QPainter(img)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                self._draw_frame(painter, t, width, height)
                painter.end()
                
                ptr = img.bits()
                ptr.setsize(img.sizeInBytes())
                arr = np.array(ptr).reshape(height, width, 4)[:, :, :3].copy()
                writer.append_data(arr)
                
                progress_percent = int((frame_num / total_frames) * 100)
                self.progress.emit(progress_percent)
                if frame_num % 5 == 0:
                    self.preview.emit(img.scaled(640, 360, Qt.AspectRatioMode.KeepAspectRatio))
                    
            writer.close()
            
            # PASS 3: Mux Video and Audio via FFmpeg
            self.status.emit("Pass 3: Muxing Audio and Video (FFmpeg)...")
            self._mux_audio_video()
            
            # Cleanup
            if os.path.exists(self.temp_video): os.remove(self.temp_video)
            if os.path.exists(self.temp_audio): os.remove(self.temp_audio)
                
            self.finished.emit(True, self.output_file)
            
        except Exception as e:
            self.finished.emit(False, str(e))

    def _record_audio(self):
        try:
            self.osc_client.send_message("/server/prepareForRecord", [self.temp_audio, "wav", "int16", 0])
            time.sleep(0.5)
            self.osc_client.send_message("/server/record", [])
            exec(self.code, globals())
            time.sleep(self.duration)
            if 'stop_all' in globals(): stop_all()
            time.sleep(0.5)
            self.osc_client.send_message("/server/stopRecording", [])
            time.sleep(1.5)
            return True
        except Exception as e:
            print(f"Audio recording failed: {e}")
            return False

    def _mix_keystrokes(self, audio_data, sr):
        dur = 0.03
        t_click = np.linspace(0, dur, int(sr * dur))
        click = np.sin(2 * np.pi * 1500 * t_click) * np.exp(-t_click * 80) * 0.15
        
        for t in self.typing_timeline:
            idx = int(t * sr)
            end_idx = idx + len(click)
            if end_idx < len(audio_data):
                audio_data[idx:end_idx] += click
        return np.clip(audio_data, -1, 1)

    def _mux_audio_video(self):
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg_exe,
            '-y', '-i', self.temp_video, '-i', self.temp_audio,
            '-c:v', 'copy', '-c:a', 'aac',
            '-shortest', self.output_file
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _draw_frame(self, painter, t, width, height):
        # Backgrounds
        painter.fillRect(0, 0, width, height, THEME['bg'])
        painter.fillRect(0, 35, 50, height-60, THEME['line_number_bg'])
        
        # Terminal Title Bar
        painter.fillRect(0, 0, width, 35, THEME['terminal_bar'])
        painter.setBrush(QColor(255, 95, 86)); painter.drawEllipse(15, 12, 11, 11)
        painter.setBrush(QColor(255, 189, 46)); painter.drawEllipse(35, 12, 11, 11)
        painter.setBrush(QColor(39, 201, 63)); painter.drawEllipse(55, 12, 11, 11)
        
        painter.setPen(QColor(180, 180, 180))
        painter.setFont(self.font_ui)
        painter.drawText(QRectF(0, 0, width, 35), Qt.AlignmentFlag.AlignCenter, "sardine_session.py - Sardine Viz Studio")
        
        # Code Animation State
        painter.setFont(self.font_code)
        x, y = 60, 70
        line_height = 24
        current_len = 0
        current_line_num = 1
        
        target_cursor_x = x
        target_cursor_y = y + 4
        
        # Draw initial line number
        painter.setPen(QColor(100, 100, 100))
        painter.drawText(QRectF(10, y, 40, line_height), Qt.AlignmentFlag.AlignRight, str(current_line_num))
        
        for token_type, value in self.tokens:
            token_color = self._get_token_color(token_type)
            
            for char in value:
                is_typed = current_len < len(self.typing_timeline) and self.typing_timeline[current_len] <= t
                
                if char == '\n':
                    if is_typed:
                        target_cursor_x = 60
                        target_cursor_y = y + line_height + 4
                        y += line_height
                        current_line_num += 1
                        painter.setPen(QColor(100, 100, 100))
                        painter.drawText(QRectF(10, y, 40, line_height), Qt.AlignmentFlag.AlignRight, str(current_line_num))
                    current_len += 1
                    continue
                elif char == '\t':
                    if is_typed:
                        x += 40
                        target_cursor_x = x
                        target_cursor_y = y + 4
                    current_len += 1
                    continue
                
                if is_typed:
                    typed_time = self.typing_timeline[current_len]
                    age = t - typed_time
                    alpha = min(1.0, age / 0.08)
                    
                    c = QColor(token_color)
                    c.setAlpha(int(alpha * 255))
                    painter.setPen(c)
                    
                    painter.drawText(QRectF(x, y, 20, line_height), Qt.AlignmentFlag.AlignLeft, char)
                    char_width = painter.fontMetrics().horizontalAdvance(char)
                    x += char_width + 1
                    
                    target_cursor_x = x
                    target_cursor_y = y + 4
                    
                current_len += 1
                
        # Smooth Cursor Interpolation
        self.current_cursor_x += (target_cursor_x - self.current_cursor_x) * 0.35
        self.current_cursor_y += (target_cursor_y - self.current_cursor_y) * 0.35
        
        cursor_moving = abs(target_cursor_x - self.current_cursor_x) > 0.5
        if cursor_moving or int(t * 3) % 2 == 0:
            painter.fillRect(QRectF(self.current_cursor_x, self.current_cursor_y, 3, 20), THEME['cursor'])
            
        # --- Audio Visualizer Dispatch ---
        if self.viz_mode == "Spectrum Bars":
            self._draw_spectrum_bars(painter, t, width, height)
        elif self.viz_mode == "Oscilloscope Wave":
            self._draw_oscilloscope(painter, t, width, height)
        elif self.viz_mode == "Circular Spectrum":
            self._draw_circular_spectrum(painter, t, width, height)
            
        # Status Bar
        painter.fillRect(0, height - 25, width, 25, THEME['terminal_bar'])
        painter.setPen(QColor(255, 100, 100))
        status_text = f"REC ● | Time: {t:.2f}s / {self.duration}s | Sardine + SuperCollider"
        painter.drawText(QRectF(15, height - 23, 500, 20), Qt.AlignmentFlag.AlignLeft, status_text)

    def _update_spectrum_peaks(self, t):
        start_idx = int(t * self.audio_samplerate)
        end_idx = int((t + (1.0/self.fps)) * self.audio_samplerate)
        chunk = self.audio_data[start_idx:end_idx]
        
        if len(chunk) == 0: return
        
        window = np.hanning(len(chunk))
        fft_data = np.fft.rfft(chunk * window)
        magnitudes = np.abs(fft_data)[:64]
        magnitudes = np.log10(magnitudes + 1)
        max_mag = np.max(magnitudes) + 0.001
        target_mags = magnitudes / max_mag
        
        for i in range(64):
            if target_mags[i] > self.spectrum_peaks[i]:
                self.spectrum_peaks[i] = target_mags[i]
            else:
                self.spectrum_peaks[i] *= self.viz_decay

    def _draw_spectrum_bars(self, painter, t, width, height):
        if self.audio_data is None: return
        self._update_spectrum_peaks(t)
        
        bar_width = (width - 80) / 64
        base_y = height - 35
        max_bar_height = 80 * self.viz_size
        
        gradient = QLinearGradient(0, base_y, 0, base_y - max_bar_height)
        gradient.setColorAt(0.0, QColor(0, 255, 150, 220))
        gradient.setColorAt(0.6, QColor(255, 200, 0, 220))
        gradient.setColorAt(1.0, QColor(255, 50, 50, 220))
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        
        for i, mag in enumerate(self.spectrum_peaks):
            bar_height = mag * max_bar_height
            x_pos = 40 + (i * bar_width)
            painter.drawRoundedRect(QRectF(x_pos, base_y - bar_height, bar_width - 2, bar_height), 2, 2)
            
            # Reflection
            painter.setBrush(QColor(0, 255, 150, 40))
            refl_height = min(bar_height * 0.4, 15)
            painter.drawRoundedRect(QRectF(x_pos, base_y + 2, bar_width - 2, refl_height), 2, 2)
            painter.setBrush(gradient)

    def _draw_oscilloscope(self, painter, t, width, height):
        if self.audio_data is None: return
        
        start_idx = int(t * self.audio_samplerate)
        end_idx = int((t + (1.0/self.fps)) * self.audio_samplerate)
        chunk = self.audio_data[start_idx:end_idx]
        if len(chunk) == 0: return
        
        target_width = width - 80
        chunk_idx = np.linspace(0, len(chunk)-1, target_width).astype(int)
        wave = chunk[chunk_idx]
        
        base_y = height - 60
        max_h = 40 * self.viz_size
        
        path = QPainterPath()
        path.moveTo(40, base_y - (wave[0] * max_h))
        
        for i, sample in enumerate(wave):
            y = base_y - (sample * max_h)
            path.lineTo(40 + i, y)
            
        # Glow effect
        painter.setPen(QColor(0, 255, 150, 60))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path_stroked = QPainterPath()
        path_stroked.addPath(path)
        painter.drawPath(path_stroked)
        
        painter.setPen(QColor(0, 255, 150, 255))
        painter.drawPath(path)

    def _draw_circular_spectrum(self, painter, t, width, height):
        if self.audio_data is None: return
        self._update_spectrum_peaks(t)
        
        center_x = width / 2
        center_y = height + 50 # Half circle rising from bottom
        base_radius = 150 * self.viz_size
        max_bar_len = 80 * self.viz_size
        
        painter.setPen(Qt.PenStyle.NoPen)
        
        for i, mag in enumerate(self.spectrum_peaks):
            # Spread 64 bars across 180 degrees (PI)
            angle = np.pi + (i / 64) * np.pi
            bar_len = mag * max_bar_len
            
            x1 = center_x + np.cos(angle) * base_radius
            y1 = center_y + np.sin(angle) * base_radius
            x2 = center_x + np.cos(angle) * (base_radius + bar_len)
            y2 = center_y + np.sin(angle) * (base_radius + bar_len)
            
            # Color gradient based on bar length
            color_val = int(200 - (mag * 150))
            painter.setPen(QColor(0, 255, color_val, 220))
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _get_token_color(self, token_type):
        if token_type in Token.Comment: return THEME['comment']
        elif token_type in Token.Keyword or token_type in Token.Name.Decorator: return THEME['keyword']
        elif token_type in Token.String: return THEME['string']
        elif token_type in Token.Number: return THEME['number']
        elif token_type in Token.Name.Function: return THEME['func']
        return THEME['text']

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sardine Viz Studio - PySide6")
        self.setMinimumSize(1000, 750)
        
        # Audio Preview Setup
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.8)
        
        layout = QVBoxLayout(self)
        control_layout = QHBoxLayout()
        
        self.code_editor = QPlainTextEdit()
        self.code_editor.setPlainText(DEFAULT_CODE)
        self.code_editor.setFont(QFont("Consolas", 11))
        self.highlighter = PythonHighlighter(self.code_editor.document())
        
        settings_widget = QWidget()
        settings_layout = QVBoxLayout(settings_widget)
        
        form_layout = QFormLayout()
        
        # Script Dropdown
        self.file_combo = QComboBox()
        self.file_combo.addItem("Default Script")
        self.load_files_to_combo()
        self.file_combo.currentIndexChanged.connect(self.load_selected_file)
        form_layout.addRow("Load Script:", self.file_combo)
        
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(3, 60)
        self.duration_spin.setValue(10)
        form_layout.addRow("Duration (s):", self.duration_spin)
        
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(15, 60)
        self.fps_spin.setValue(30)
        form_layout.addRow("FPS:", self.fps_spin)
        
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(5, 20)
        self.speed_slider.setValue(10)
        self.speed_slider.valueChanged.connect(self.update_speed_label)
        self.speed_label = QLabel("1.0x")
        form_layout.addRow("Typing Speed:", self.speed_slider)
        form_layout.addRow("", self.speed_label)
        
        self.chk_keystrokes = QCheckBox("Add Keystroke Sounds")
        self.chk_keystrokes.setChecked(True)
        form_layout.addRow("", self.chk_keystrokes)
        
        # --- Visualizer Settings ---
        viz_group_label = QLabel("<b>Audio Visualizer</b>")
        viz_group_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        form_layout.addRow(viz_group_label)
        
        self.viz_combo = QComboBox()
        self.viz_combo.addItems(["Spectrum Bars", "Oscilloscope Wave", "Circular Spectrum", "None"])
        form_layout.addRow("Mode:", self.viz_combo)
        
        self.viz_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.viz_size_slider.setRange(20, 100)
        self.viz_size_slider.setValue(60)
        self.viz_size_slider.valueChanged.connect(self.update_viz_size_label)
        self.viz_size_label = QLabel("60%")
        form_layout.addRow("Size:", self.viz_size_slider)
        form_layout.addRow("", self.viz_size_label)
        
        self.viz_decay_slider = QSlider(Qt.Orientation.Horizontal)
        self.viz_decay_slider.setRange(50, 99) # 0.50 to 0.99
        self.viz_decay_slider.setValue(92)
        self.viz_decay_slider.valueChanged.connect(self.update_viz_decay_label)
        self.viz_decay_label = QLabel("0.92")
        form_layout.addRow("Decay:", self.viz_decay_slider)
        form_layout.addRow("", self.viz_decay_label)
        
        settings_layout.addLayout(form_layout)
        
        # Buttons Layout
        btn_layout = QHBoxLayout()
        self.btn_preview = QPushButton("Quick Preview (3s)")
        self.btn_preview.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.btn_preview.clicked.connect(self.start_preview_render)
        btn_layout.addWidget(self.btn_preview)
        
        self.btn_generate = QPushButton("Generate MP4")
        self.btn_generate.setMinimumHeight(50)
        self.btn_generate.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.btn_generate.clicked.connect(self.start_render)
        btn_layout.addWidget(self.btn_generate)
        
        settings_layout.addLayout(btn_layout)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        settings_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Ready.")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        settings_layout.addWidget(self.status_label)
        
        settings_layout.addStretch()
        
        control_layout.addWidget(self.code_editor, 2)
        control_layout.addWidget(settings_widget, 1)
        layout.addLayout(control_layout, 2)
        
        self.preview_label = QLabel("Preview will appear here during rendering.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("background-color: black; color: white;")
        self.preview_label.setMinimumHeight(350)
        layout.addWidget(self.preview_label, 3)

    def load_files_to_combo(self):
        """Scans the input folder and populates the dropdown."""
        files = [f for f in os.listdir(INPUT_DIR) if f.endswith('.py')]
        if files:
            self.file_combo.addItems(files)

    def load_selected_file(self, index):
        """Loads the selected file from the dropdown into the code editor."""
        if index == 0:
            self.code_editor.setPlainText(DEFAULT_CODE)
            return
            
        filename = self.file_combo.currentText()
        filepath = os.path.join(INPUT_DIR, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.code_editor.setPlainText(f.read())
            self.status_label.setText(f"Loaded {filename}")
        except Exception as e:
            self.status_label.setText(f"Error loading file: {e}")

    def update_speed_label(self, val):
        speed = val / 10.0
        self.speed_label.setText(f"{speed:.1f}x")

    def update_viz_size_label(self, val):
        self.viz_size_label.setText(f"{val}%")

    def update_viz_decay_label(self, val):
        self.viz_decay_label.setText(f"{val / 100.0:.2f}")

    def start_preview_render(self):
        """Starts a short 3-second render for quick audio/visual testing."""
        self._init_render(duration=3, is_preview=True)

    def start_render(self):
        """Starts the full render process."""
        self._init_render(duration=self.duration_spin.value(), is_preview=False)

    def _init_render(self, duration, is_preview):
        code = self.code_editor.toPlainText()
        fps = self.fps_spin.value()
        speed = self.speed_slider.value() / 10.0
        keystrokes = self.chk_keystrokes.isChecked()
        
        viz_mode = self.viz_combo.currentText()
        viz_size = self.viz_size_slider.value()
        viz_decay = self.viz_decay_slider.value()
        
        if is_preview:
            output_file = "_temp_preview.mp4"  # Dummy path for preview
        else:
            file_path, _ = QFileDialog.getSaveFileName(self, "Save Video", "sardine_viz_output.mp4", "Video Files (*.mp4)")
            if not file_path: return
            output_file = file_path
            
        self.btn_generate.setEnabled(False)
        self.btn_preview.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("Initializing...")
        
        self.worker = RenderWorker(code, duration, fps, output_file, speed, keystrokes, viz_mode, viz_size, viz_decay)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.status.connect(self.status_label.setText)
        self.worker.preview.connect(self.update_preview)
        self.worker.audio_ready.connect(self.start_audio_preview)
        self.worker.finished.connect(lambda s, m: self.on_render_finished(s, m, is_preview))
        self.worker.start()

    def start_audio_preview(self, audio_path):
        """Plays the recorded audio track while the visual preview runs."""
        self.media_player.setSource(QUrl.fromLocalFile(audio_path))
        self.media_player.play()

    def update_preview(self, qimage):
        self.preview_label.setPixmap(QPixmap.fromImage(qimage))

    def on_render_finished(self, success, message, is_preview):
        self.btn_generate.setEnabled(True)
        self.btn_preview.setEnabled(True)
        self.media_player.stop()
        
        if success:
            if not is_preview:
                self.status_label.setText(f"Success! Saved to {message}")
                self.progress_bar.setValue(100)
            else:
                self.status_label.setText("Preview finished.")
                if os.path.exists(message): os.remove(message)
        else:
            self.status_label.setText(f"Error: {message}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())