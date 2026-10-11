"""
SuperCollider NRT Visualizer (Enhanced UI, Layouts & Concurrent Pipeline)
================================================================
- Layout presets for YouTube Videos (16:9) and YouTube Shorts (9:16).
- Customizable typing animation styles and audio visualizers.
- Typing animation duration matches the exact duration of the generated audio.
- Audio visuals render concurrently with the code typing animation.
- Audio Preview button to listen to the generated WAV.
- All logs and errors are routed exclusively to 'nrt_visualizer.log'.
"""

import sys
import os
import subprocess
import tempfile
import shutil
import logging
import time
import wave
import math
import threading
import traceback
from enum import Enum, auto
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QMessageBox, QProgressBar, QComboBox,
    QFileDialog, QSpinBox, QGroupBox, QLineEdit, QListWidget, QListWidgetItem,
    QTextEdit
)
from PySide6.QtCore import (
    QThread, QObject, Signal, Slot, Qt, QRect, QRectF, QPointF, QSize, QSettings, QUrl
)
from PySide6.QtGui import (
    QImage, QPainter, QColor, QFont, QPen, QBrush, QLinearGradient,
    QFontMetrics, QPixmap, QRadialGradient
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
import numpy as np

# ============================================================================
# Configuration & Logging
# ============================================================================
INPUT_FOLDER = os.path.join(os.getcwd(), "sc_input")
OUTPUT_FOLDER = os.path.join(os.getcwd(), "sc_output")
LOG_FILE = os.path.join(os.getcwd(), "nrt_visualizer.log")

def setup_logging():
    logger = logging.getLogger("NRTVisualizer")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        try:
            fh = logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
            fh.setLevel(logging.DEBUG)
            fmt = logging.Formatter(
                '%(asctime)s [%(levelname)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S')
            fh.setFormatter(fmt)
            logger.addHandler(fh)
            logger.propagate = False
        except Exception as e:
            print(f"Failed to set up logfile: {e}", file=sys.stderr)
    return logger

log = setup_logging()

# ============================================================================
# Pipeline State Machine
# ============================================================================
class PipelineState(Enum):
    IDLE = auto()
    CHECKING_DEPS = auto()
    PREPARING_SCRIPT = auto()
    COMPILING_OSC_SCORE = auto()
    RENDERING_AUDIO_WAV = auto()
    READING_WAV_FILE = auto()
    INITIALIZING_RENDERER = auto()
    STARTING_ENCODER = auto()
    STREAMING_FRAMES = auto()
    FINALIZING_MP4 = auto()
    CLEANUP = auto()
    COMPLETE = auto()
    ERROR = auto()
    FINISHED = auto()

# ============================================================================
# Audio Generation (SuperCollider NRT)
# ============================================================================
class AudioGenerator:
    @staticmethod
    def generate(sc_code, score_path, wav_path, temp_dir, log_fn, state_cb=None):
        def _cb(state, msg, pct):
            if state_cb: state_cb(state, msg, pct)

        _cb(PipelineState.PREPARING_SCRIPT, "Preparing SC script...", 5)
        
        if "__SCORE_PATH__" not in sc_code:
            log_fn("  [WARNING] '__SCORE_PATH__' placeholder missing in SC code.")

        score_path_sc = score_path.replace('\\', '/')
        final_sc_code = sc_code.replace("__SCORE_PATH__", score_path_sc)
        
        script_path = os.path.join(temp_dir, "gen_score.scd")
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(final_sc_code)

        _cb(PipelineState.COMPILING_OSC_SCORE, "Running sclang to compile OSC score...", 10)
        sclang = shutil.which('sclang')
        if not sclang: raise Exception("sclang not found on PATH")
        
        process = subprocess.Popen(
            [sclang, '-D', script_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            text=True, encoding='utf-8', errors='replace'
        )
        output_lines, success, start_time = [], False, time.time()
        while True:
            if time.time() - start_time > 60:
                process.kill(); process.wait()
                raise Exception("sclang timed out (>60s).")
            line = process.stdout.readline()
            if not line:
                if process.poll() is not None: break
                time.sleep(0.1); continue
            output_lines.append(line)
            log_fn(f"  sclang: {line.strip()}")
            
            if "SCORE_WRITTEN" in line:
                success = True
                time.sleep(0.5)
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
                break

        if not success:
            raise Exception("sclang failed to write score file.\nOutput:\n" + "".join(output_lines))

        _cb(PipelineState.RENDERING_AUDIO_WAV, "Running scsynth -N to render audio...", 15)
        scsynth = shutil.which('scsynth')
        if not scsynth: raise Exception("scsynth not found on PATH")
        
        cmd = [scsynth, '-o', '2', '-N', score_path, '_', wav_path, '44100', 'WAV', 'int16']
        try:
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                text=True, encoding='utf-8', errors='replace', timeout=60
            )
        except subprocess.TimeoutExpired:
            raise Exception("scsynth timed out (>60s) while rendering WAV.")
            
        if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 1024:
            err_detail = result.stderr.strip() or result.stdout.strip()
            raise Exception(f"scsynth failed to render WAV file.\nscsynth Output:\n{err_detail}")

# ============================================================================
# Audio Data Analyzer
# ============================================================================
class AudioData:
    def __init__(self, wav_path):
        with wave.open(wav_path, 'rb') as wf:
            self.n_channels = wf.getnchannels()
            self.sample_width = wf.getsampwidth()
            self.sample_rate = wf.getframerate()
            self.n_frames = wf.getnframes()
            raw = wf.readframes(self.n_frames)

        if self.sample_width == 2:
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif self.sample_width == 1:
            samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128.0
        else:
            raise Exception(f"Unsupported sample width: {self.sample_width}")

        if self.n_channels > 1:
            samples = samples.reshape(-1, self.n_channels).mean(axis=1)

        self.samples = samples
        self.duration = self.n_frames / self.sample_rate

    def get_envelope(self, n_bins):
        abs_samples = np.abs(self.samples)
        if len(abs_samples) == 0: return np.zeros(n_bins)
        chunk_size = max(1, len(abs_samples) // n_bins)
        n_use = chunk_size * n_bins
        trimmed = abs_samples[:n_use]
        reshaped = trimmed.reshape(n_bins, chunk_size)
        envelope = reshaped.max(axis=1)
        peak = envelope.max()
        return envelope / peak if peak > 0 else envelope

    def get_frame_amplitudes(self, fps, offset=0.0):
        n_frames = int(self.duration * fps) + 1
        amps = np.zeros(n_frames)
        samples_per_frame = self.sample_rate / fps
        for i in range(n_frames):
            start = int(i * samples_per_frame)
            end = int((i + 1) * samples_per_frame)
            chunk = self.samples[start:end]
            if len(chunk) > 0:
                amps[i] = float(np.sqrt(np.mean(chunk ** 2)))
        peak = amps.max()
        return amps / peak if peak > 0 else amps

# ============================================================================
# Typing Animator
# ============================================================================
class TypingAnimator:
    def __init__(self, text, duration, style="Cubic Ease-Out", typing_end_ratio=0.8):
        self.text = text
        self.duration = duration
        self.typing_end = max(0.5, duration * typing_end_ratio)
        self.style = style

    def visible_text(self, t):
        if t >= self.typing_end: return self.text
        progress = max(0.0, t / self.typing_end)
        
        if self.style == "Linear":
            eased = progress
        elif self.style == "Typewriter":
            chars_to_show = math.floor(progress * len(self.text))
            eased = (chars_to_show - (chars_to_show % 3)) / len(self.text)
        elif self.style == "Bursts":
            eased = math.floor(progress * 5) / 5.0
        else: 
            eased = 1 - (1 - progress) ** 3 
            
        return self.text[:int(len(self.text) * eased)]

    def cursor_visible(self, t, blink_rate=2.5):
        return int(t * blink_rate) % 2 == 0

# ============================================================================
# Concurrent Frame Renderer
# ============================================================================
class FrameRenderer:
    def __init__(self, audio_data, text, sc_code, width=1280, height=720, fps=30, 
                 typing_style="Cubic Ease-Out", visual_style="Circular + Waveform"):
        self.audio = audio_data
        self.text = text
        self.sc_code = sc_code
        self.width = width
        self.height = height
        self.fps = fps
        self.typing_style = typing_style
        self.visual_style = visual_style
            
        self.code_typing = TypingAnimator(sc_code, audio_data.duration, typing_style, 0.95)
        self.audio_typing = TypingAnimator(text, audio_data.duration, typing_style, 0.8)
        
        self.n_bars = 120
        self.envelope = audio_data.get_envelope(self.n_bars)
        self.frame_amps = audio_data.get_frame_amplitudes(fps)
        
        self.font_title = QFont("Consolas", 14, QFont.Bold)
        self.font_time = QFont("Consolas", 12)
        self.font_body = QFont("Consolas", 18)
        self.font_label = QFont("Consolas", 10)
        self.font_code = QFont("Consolas", 16)

        self.canvas = QImage(self.width, self.height, QImage.Format_RGBA8888)

    def render_frame_to_canvas(self, frame_idx):
        t = frame_idx / self.fps
        self.canvas.fill(Qt.transparent)
        p = QPainter(self.canvas)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        amp = float(self.frame_amps[frame_idx]) if frame_idx < len(self.frame_amps) else 0.0
        
        self._draw_background(p, amp)
        self._draw_header(p, t)
        self._draw_code_phase(p, t)
        
        if self.visual_style == "Bars Only":
            self._draw_waveform(p, t, y_ratio=0.72, height_ratio=0.20)
        elif self.visual_style == "Minimal Waveform":
            self._draw_waveform(p, t, y_ratio=0.80, height_ratio=0.12, alpha=200)
        else: 
            self._draw_circular_viz(p, t, amp, y_ratio=0.80)
            self._draw_waveform(p, t, y_ratio=0.90, height_ratio=0.06)
            
        self._draw_progress_bar(p, t)
        
        p.end()
        return self.canvas

    def _draw_background(self, p, amp):
        grad = QLinearGradient(0, 0, 0, self.height)
        grad.setColorAt(0.0, QColor(15, 18, 35)); grad.setColorAt(0.5, QColor(10, 12, 25)); grad.setColorAt(1.0, QColor(4, 5, 12))
        p.fillRect(0, 0, self.width, self.height, QBrush(grad))

        glow = QRadialGradient(self.width/2, self.height/2, self.width/2)
        glow.setColorAt(0, QColor(0, 150, 255, int(60 * amp))); glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, self.width, self.height, QBrush(glow))

        p.setPen(QPen(QColor(80, 100, 150, 22), 1))
        for x in range(0, self.width, 40): p.drawLine(x, 0, x, self.height)
        for y in range(0, self.height, 40): p.drawLine(0, y, self.width, y)

    def _draw_code_phase(self, p, t):
        p.setPen(QPen(QColor(0, 200, 255, 150), 2))
        p.setBrush(QColor(20, 22, 30, 230)) 
        h_ratio = 0.65 if self.width > self.height else 0.55
        rect = QRect(40, 50, self.width - 80, int(self.height * h_ratio))
        p.drawRoundedRect(rect, 10, 10)

        p.setPen(QColor(150, 160, 180))
        p.setFont(self.font_label)
        p.drawText(rect.adjusted(15, 10, 0, 0), Qt.AlignTop | Qt.AlignLeft, "superCollider_nrt.scd")
        
        p.setPen(QColor(255, 100, 100)); p.drawEllipse(rect.left() + 20, rect.top() + 15, 8, 8)
        p.setPen(QColor(255, 200, 100)); p.drawEllipse(rect.left() + 35, rect.top() + 15, 8, 8)
        p.setPen(QColor(100, 255, 100)); p.drawEllipse(rect.left() + 50, rect.top() + 15, 8, 8)

        visible_code = self.code_typing.visible_text(t)
        if self.code_typing.cursor_visible(t): visible_code += "█"

        p.setPen(QColor(0, 255, 150))
        p.setFont(self.font_code)
        text_area = rect.adjusted(20, 50, -20, -40)
        p.drawText(text_area, Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap, visible_code)

    def _draw_header(self, p, t):
        p.setPen(QColor(200, 220, 240)); p.setFont(self.font_title)
        p.drawText(40, 32, "◢ SuperCollider NRT Visualizer")

        p.setPen(QColor(0, 220, 255)); p.setFont(self.font_time)
        time_str = f"t = {t:6.2f}s / {self.audio.duration:6.2f}s"
        fm = p.fontMetrics(); tw = fm.horizontalAdvance(time_str)
        p.drawText(self.width - 40 - tw, 32, time_str)

    def _draw_circular_viz(self, p, t, amp, y_ratio=0.35):
        cx = self.width // 2
        cy = int(self.height * y_ratio)
        base_r = 60
        p.setPen(QPen(QColor(255, 255, 255, 30), 1)); p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), base_r, base_r)

        playhead_progress = t / max(0.001, self.audio.duration)
        n_segments = 80
        
        for i in range(n_segments):
            angle = (i / n_segments) * 2 * math.pi
            env_idx = int((i / n_segments) * self.n_bars)
            env_val = float(self.envelope[env_idx])
            
            r1 = base_r + 10
            r2 = base_r + 10 + (env_val * 40 * amp * 2)
            
            x1, y1 = cx + math.cos(angle) * r1, cy + math.sin(angle) * r1
            x2, y2 = cx + math.cos(angle) * r2, cy + math.sin(angle) * r2
            
            seg_progress = i / n_segments
            if seg_progress <= playhead_progress:
                color = self._lerp_color(QColor(0, 200, 255), QColor(255, 100, 200), seg_progress)
                color.setAlpha(220)
            else:
                color = QColor(70, 90, 130, 80)
            p.setPen(QPen(color, 2))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _draw_waveform(self, p, t, y_ratio=0.85, height_ratio=0.10, alpha=230):
        wf_x = 60
        wf_y = int(self.height * y_ratio)
        wf_w = self.width - 120
        wf_h = int(self.height * height_ratio)
        mid_y = wf_y + wf_h // 2

        p.fillRect(wf_x, wf_y, wf_w, wf_h, QColor(0, 0, 0, 110))
        p.setPen(QPen(QColor(100, 130, 170, 110), 1)); p.setBrush(Qt.NoBrush)
        p.drawRect(wf_x, wf_y, wf_w, wf_h)

        bar_w = wf_w / self.n_bars
        playhead_progress = t / max(0.001, self.audio.duration)

        p.setPen(Qt.NoPen)
        for i, amp_val in enumerate(self.envelope):
            x = wf_x + i * bar_w
            h = amp_val * (wf_h / 2) * 0.95
            if (i / self.n_bars) <= playhead_progress:
                color = self._lerp_color(QColor(0, 200, 255), QColor(255, 100, 200), i / self.n_bars)
                color.setAlpha(alpha)
            else:
                color = QColor(70, 90, 130, 100)
            p.setBrush(color)
            p.drawRect(QRectF(x, mid_y - h, max(1.0, bar_w - 1.0), 2.0 * h))

        ph_x = wf_x + playhead_progress * wf_w
        p.setPen(QPen(QColor(255, 255, 255, 230), 2))
        p.drawLine(QPointF(ph_x, wf_y - 6), QPointF(ph_x, wf_y + wf_h + 6))

    def _draw_progress_bar(self, p, t):
        pb_y, pb_h = self.height - 22, 4
        pb_x, pb_w = 60, self.width - 120

        p.setPen(Qt.NoPen); p.setBrush(QColor(40, 50, 70))
        p.drawRect(pb_x, pb_y, pb_w, pb_h)

        progress = t / max(0.001, self.audio.duration)
        grad = QLinearGradient(pb_x, 0, pb_x + pb_w, 0)
        grad.setColorAt(0.0, QColor(0, 200, 255)); grad.setColorAt(1.0, QColor(255, 100, 200))
        p.setBrush(QBrush(grad))
        p.drawRect(pb_x, pb_y, int(pb_w * progress), pb_h)

    @staticmethod
    def _lerp_color(c1, c2, t):
        t = max(0.0, min(1.0, t))
        r = int(c1.red()   + (c2.red()   - c1.red())   * t)
        g = int(c1.green() + (c2.green() - c1.green()) * t)
        b = int(c1.blue()  + (c2.blue()  - c1.blue())  * t)
        return QColor(r, g, b)

# ============================================================================
# Video Encoder
# ============================================================================
class VideoEncoder:
    @staticmethod
    def start_ffmpeg_process(wav_path, output_mp4, fps, width, height, log_fn):
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg: raise Exception("ffmpeg not found on PATH")
        
        cmd = [
            ffmpeg, '-y',
            '-f', 'rawvideo', '-vcodec', 'rawvideo',
            '-s', f'{width}x{height}', '-pix_fmt', 'rgba',
            '-r', str(fps), '-i', 'pipe:0',
            '-i', wav_path,
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '192k',
            '-shortest', '-movflags', '+faststart', output_mp4
        ] 
        
        log_fn("  Starting FFmpeg process...")
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        def drain_stderr():
            while True:
                line = proc.stderr.readline()
                if not line: break
                log_fn(f"  ffmpeg: {line.decode('utf-8', errors='replace').strip()}")
            proc.stderr.close()
            
        t = threading.Thread(target=drain_stderr, daemon=True)
        t.start()
        return proc

    @staticmethod
    def write_frame(proc, qimage, log_fn):
        if proc.poll() is not None:
            raise Exception(f"FFmpeg died prematurely with code {proc.returncode}")
        try:
            ptr = qimage.constBits()
            if hasattr(ptr, 'setsize'): ptr.setsize(qimage.sizeInBytes())
            proc.stdin.write(ptr)
        except BrokenPipeError:
            raise Exception("Broken pipe to FFmpeg.")

    @staticmethod
    def finalize(proc, log_fn):
        if proc.poll() is None:
            proc.stdin.close()
            try: proc.wait(timeout=15)
            except subprocess.TimeoutExpired: proc.kill(); raise Exception("FFmpeg timed out.")
        if proc.returncode != 0: raise Exception(f"FFmpeg exited with error code {proc.returncode}")

# ============================================================================
# Pipeline Worker
# ============================================================================
class PipelineWorker(QObject):
    log = Signal(str)
    progress = Signal(int, str)
    state_changed = Signal(str)
    frame_preview = Signal(object)
    wav_ready = Signal(str)
    duration_ready = Signal(float, int)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, sc_code, description, output_mp4, fps=30, width=1280, height=720, 
                 typing_style="Cubic Ease-Out", visual_style="Circular + Waveform"):
        super().__init__()
        self.sc_code = sc_code
        self.description = description
        self.output_mp4 = output_mp4
        self.fps = fps
        self.width = width
        self.height = height
        self.typing_style = typing_style
        self.visual_style = visual_style
        self.temp_dir = tempfile.mkdtemp(prefix="nrt_viz_")
        self._cancel = False

    def cancel(self): self._cancel = True

    def _set_state(self, state, message="", progress_val=-1):
        log.info(f"STATE -> {state.name}: {message}")
        self.state_changed.emit(state.name)
        if message: self.log.emit(f"[{state.name}] {message}")
        if progress_val >= 0: self.progress.emit(progress_val, message if message else state.name)

    @Slot()
    def run(self):
        proc = None
        try:
            self._set_state(PipelineState.CHECKING_DEPS, "Checking dependencies...", 2)
            missing = [c for c in ['sclang', 'scsynth', 'ffmpeg'] if not shutil.which(c)]
            if missing: raise Exception(f"Missing on PATH: {', '.join(missing)}.")

            score_path = os.path.join(self.temp_dir, "score.osc").replace('\\', '/')
            wav_path = os.path.join(self.temp_dir, "audio.wav").replace('\\', '/')

            audio_error = [None]
            def generate_audio_async():
                try:
                    AudioGenerator.generate(self.sc_code, score_path, wav_path, self.temp_dir, self.log.emit, self._set_state)
                except Exception as e:
                    audio_error[0] = "".join(traceback.format_exception(e))
                    self._cancel = True

            self._set_state(PipelineState.COMPILING_OSC_SCORE, "Starting concurrent audio generation...", 5)
            audio_thread = threading.Thread(target=generate_audio_async, daemon=True)
            audio_thread.start()

            start_wait = time.time()
            while audio_thread.is_alive():
                if self._cancel:
                    audio_thread.join(timeout=2.0)
                    break
                if time.time() - start_wait > 150.0: 
                    self._cancel = True
                    audio_thread.join(timeout=2.0)
                    raise Exception("Audio generation timed out (>150s).")
                time.sleep(0.1)

            if audio_error[0]:
                raise Exception(f"Audio generation thread crashed:\n{audio_error[0]}")
            
            if self._cancel:
                raise Exception("Cancelled by user.")

            if not os.path.exists(wav_path):
                if os.path.exists(score_path):
                    raise Exception("Score generated successfully, but scsynth failed to produce a WAV file.")
                else:
                    raise Exception("sclang failed to produce an OSC score file.")

            persistent_wav = os.path.join(OUTPUT_FOLDER, "temp_preview.wav")
            try: shutil.copy(wav_path, persistent_wav)
            except: pass
            self.wav_ready.emit(persistent_wav)

            self._set_state(PipelineState.READING_WAV_FILE, "Reading WAV file...", 20)
            audio_data = AudioData(wav_path)
            
            total_duration = audio_data.duration
            n_frames = int(total_duration * self.fps) + 1
            self.duration_ready.emit(total_duration, n_frames)

            self._set_state(PipelineState.INITIALIZING_RENDERER, "Initializing renderer...", 28)
            renderer = FrameRenderer(audio_data, self.description, self.sc_code, self.width, self.height, 
                                     self.fps, self.typing_style, self.visual_style)

            self._set_state(PipelineState.STARTING_ENCODER, "Starting FFmpeg process...", 30)
            proc = VideoEncoder.start_ffmpeg_process(wav_path, self.output_mp4, self.fps, self.width, self.height, self.log.emit)

            self._set_state(PipelineState.STREAMING_FRAMES, "Streaming raw frames to FFmpeg...", 32)
            start_stream_time = time.time()
            
            for i in range(n_frames):
                if self._cancel:
                    if proc: proc.stdin.close(); proc.kill()
                    raise Exception("Cancelled by user.")
                
                img = renderer.render_frame_to_canvas(i)
                VideoEncoder.write_frame(proc, img, self.log.emit)
                
                if i % 3 == 0:
                    elapsed = time.time() - start_stream_time
                    actual_fps = (i + 1) / elapsed if elapsed > 0 else 0
                    eta = (n_frames - i - 1) / actual_fps if actual_fps > 0 else 0
                    pct = 32 + int((i / max(1, n_frames)) * 65)
                    self.progress.emit(pct, f"Streaming {i+1}/{n_frames} ({actual_fps:.1f} fps, ETA: {eta:.1f}s)")
                    
                if i % 10 == 0: self.frame_preview.emit(img.copy())

            self._set_state(PipelineState.FINALIZING_MP4, "Finalizing MP4...", 97)
            VideoEncoder.finalize(proc, self.log.emit)
            if not os.path.exists(self.output_mp4): raise Exception("FFmpeg did not produce MP4.")
            
            self._set_state(PipelineState.CLEANUP, "Cleaning up temporary files...", 99)
            shutil.rmtree(self.temp_dir, ignore_errors=True)

            self._set_state(PipelineState.COMPLETE, "Item Complete!", 100)
            self.finished.emit(self.output_mp4)

        except Exception as e:
            if proc: proc.kill()
            log.exception("Pipeline failed:")
            
            self._set_state(PipelineState.CLEANUP, "Cleaning up temporary files...", 99)
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            
            self._set_state(PipelineState.ERROR, str(e), 0)
            self.error.emit(str(e))

# ============================================================================
# Main Window
# ============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SuperCollider NRT Visualizer (Enhanced UI & Auto-Save)")
        self.resize(1150, 850)
        log.info("UI initializing...")

        os.makedirs(INPUT_FOLDER, exist_ok=True)
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)

        self.settings = QSettings("SCNRT_Viz", "AppSettings")

        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.8)
        self.current_wav_path = ""

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # File List
        file_group = QGroupBox(f"SuperCollider Source Files (Auto-loaded from '{os.path.basename(INPUT_FOLDER)}')")
        fg_layout = QVBoxLayout(file_group)
        
        self.file_list = QListWidget()
        self.file_list.setStyleSheet("""
            QListWidget { background-color: #1E1E2E; color: #D4D4D4; font-family: Consolas; font-size: 12px; border: 1px solid #2A2A40; }
            QListWidget::item { padding: 4px; }
            QListWidget::item::checkbox { border: 1px solid #555; border-radius: 3px; background: #2A2A40; width: 14px; height: 14px; margin-right: 6px; }
            QListWidget::item::checkbox:checked { background: #007ACC; border: 1px solid #007ACC; }
        """)
        fg_layout.addWidget(self.file_list)
        
        file_btn_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("☑ Select All")
        self.select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        file_btn_layout.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("☐ Deselect All")
        self.deselect_all_btn.clicked.connect(lambda: self._set_all_checked(False))
        file_btn_layout.addWidget(self.deselect_all_btn)
        file_btn_layout.addStretch()

        self.refresh_btn = QPushButton("🔄 Refresh List")
        self.refresh_btn.clicked.connect(self.load_files_from_folder)
        file_btn_layout.addWidget(self.refresh_btn)
        fg_layout.addLayout(file_btn_layout)
        root.addWidget(file_group)

        # Output & Layout Options
        out_group = QGroupBox("Output & Layout Options")
        out_layout = QVBoxLayout(out_group)
        
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output Folder:"))
        self.out_dir_edit = QLineEdit(self.settings.value("output_folder", OUTPUT_FOLDER))
        out_row.addWidget(self.out_dir_edit, 2)
        self.browse_out_btn = QPushButton("Browse...")
        self.browse_out_btn.clicked.connect(self.on_browse_out)
        out_row.addWidget(self.browse_out_btn)
        out_layout.addLayout(out_row)

        opts_row1 = QHBoxLayout()
        opts_row1.addWidget(QLabel("Video Layout:"))
        self.layout_combo = QComboBox()
        self.layout_combo.addItems(["YouTube Video (16:9)", "YouTube Short (9:16)"])
        self.layout_combo.setCurrentText(self.settings.value("layout", "YouTube Video (16:9)"))
        self.layout_combo.currentTextChanged.connect(self.on_layout_changed)
        opts_row1.addWidget(self.layout_combo)
        opts_row1.addStretch()
        out_layout.addLayout(opts_row1)

        opts_row2 = QHBoxLayout()
        opts_row2.addWidget(QLabel("Typing Style:"))
        self.type_style_combo = QComboBox()
        self.type_style_combo.addItems(["Cubic Ease-Out", "Linear", "Typewriter", "Bursts"])
        self.type_style_combo.setCurrentText(self.settings.value("typing_style", "Cubic Ease-Out"))
        opts_row2.addWidget(self.type_style_combo)
        
        opts_row2.addWidget(QLabel("Visual Style:"))
        self.viz_style_combo = QComboBox()
        self.viz_style_combo.addItems(["Circular + Waveform", "Bars Only", "Minimal Waveform"])
        self.viz_style_combo.setCurrentText(self.settings.value("visual_style", "Circular + Waveform"))
        opts_row2.addWidget(self.viz_style_combo)
        opts_row2.addStretch()
        out_layout.addLayout(opts_row2)

        opts_row3 = QHBoxLayout()
        opts_row3.addWidget(QLabel("FPS:"))
        self.fps_spin = QSpinBox(); self.fps_spin.setRange(10, 60); self.fps_spin.setValue(int(self.settings.value("fps", 30)))
        opts_row3.addWidget(self.fps_spin)
        opts_row3.addWidget(QLabel("Width:"))
        self.width_spin = QSpinBox(); self.width_spin.setRange(640, 1920); self.width_spin.setSingleStep(80); self.width_spin.setValue(int(self.settings.value("width", 1280)))
        opts_row3.addWidget(self.width_spin)
        opts_row3.addWidget(QLabel("Height:"))
        self.height_spin = QSpinBox(); self.height_spin.setRange(360, 1920); self.height_spin.setSingleStep(80); self.height_spin.setValue(int(self.settings.value("height", 720)))
        opts_row3.addWidget(self.height_spin)
        opts_row3.addStretch()
        out_layout.addLayout(opts_row3)
        root.addWidget(out_group)

        self.on_layout_changed(self.layout_combo.currentText())

        # Description
        desc_group = QGroupBox("Typing Animation Text (Logs/Description)")
        desc_layout = QVBoxLayout(desc_group)
        self.desc_edit = QTextEdit()
        self.desc_edit.setStyleSheet("background-color: #1E1E2E; color: #D4D4D4; font-family: Consolas; font-size: 13px;")
        self.desc_edit.setMaximumHeight(60)
        self.desc_edit.setPlainText(self.settings.value("desc_text", ">> AUDIO ENGINE ONLINE.\n>> Generating SuperCollider NRT Output.\n>> Rendering Visualization."))
        desc_layout.addWidget(self.desc_edit)
        root.addWidget(desc_group)

        # Controls
        ctrl_row = QHBoxLayout()
        self.run_btn = QPushButton("▶  Generate MP4s")
        self.run_btn.setStyleSheet("background-color: #007ACC; color: white; font-weight: bold; padding: 12px; font-size: 14px; border-radius: 4px;")
        self.run_btn.clicked.connect(self.start_pipeline)
        ctrl_row.addWidget(self.run_btn)
        
        self.preview_audio_btn = QPushButton("🔊 Preview Audio")
        self.preview_audio_btn.setEnabled(False)
        self.preview_audio_btn.setStyleSheet("padding: 12px; font-size: 14px;")
        self.preview_audio_btn.clicked.connect(self.toggle_audio_preview)
        ctrl_row.addWidget(self.preview_audio_btn)

        self.cancel_btn = QPushButton("Cancel"); self.cancel_btn.setEnabled(False)
        self.cancel_btn.setStyleSheet("padding: 12px; font-size: 14px;")
        self.cancel_btn.clicked.connect(self.cancel_pipeline)
        ctrl_row.addWidget(self.cancel_btn)
        ctrl_row.addStretch()
        root.addLayout(ctrl_row)

        # State Info
        info_row = QHBoxLayout()
        info_row.addWidget(QLabel("State:"))
        self.state_label = QLabel("IDLE")
        self.state_label.setStyleSheet("font-weight: bold; color: #007ACC; padding: 2px 6px;")
        info_row.addWidget(self.state_label)
        
        info_row.addStretch()
        
        self.duration_label = QLabel("Estimated Duration: N/A")
        self.duration_label.setStyleSheet("font-weight: bold; color: #D4D4D4; padding: 2px 6px;")
        info_row.addWidget(self.duration_label)
        root.addLayout(info_row)

        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.setValue(0)
        self.progress.setFormat("Idle"); self.progress.setFixedHeight(22)
        root.addWidget(self.progress)

        # Animation Preview
        root.addWidget(QLabel("Live Animation Preview:"))
        self.preview_label = QLabel(); self.preview_label.setMinimumHeight(300)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("background-color: #111122; border: 1px solid #2A2A40;")
        self.preview_label.setText("Preview will appear here during rendering...")
        root.addWidget(self.preview_label, 1)

        self.worker_thread = None
        self.worker = None
        self.queue = []
        
        self.load_files_from_folder()

    def on_layout_changed(self, text):
        if "16:9" in text:
            self.width_spin.setValue(1280)
            self.height_spin.setValue(720)
        elif "9:16" in text:
            self.width_spin.setValue(720)
            self.height_spin.setValue(1280)

    def _set_all_checked(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.flags() & Qt.ItemIsUserCheckable: 
                item.setCheckState(state)

    def load_files_from_folder(self):
        self.file_list.clear()
        if os.path.exists(INPUT_FOLDER):
            for f in sorted(os.listdir(INPUT_FOLDER)):
                if f.lower().endswith(".scd"):
                    item = QListWidgetItem(os.path.join(INPUT_FOLDER, f))
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked)
                    self.file_list.addItem(item)
        
        if self.file_list.count() == 0:
            item = QListWidgetItem(f"No .scd files found. Put your files in: {INPUT_FOLDER}")
            item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable & ~Qt.ItemIsEnabled)
            self.file_list.addItem(item)

    def on_browse_out(self):
        d = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if d: self.out_dir_edit.setText(d)

    def toggle_audio_preview(self):
        if not self.current_wav_path: return
        if self.media_player.playbackState() == QMediaPlayer.PlayingState:
            self.media_player.stop()
            self.preview_audio_btn.setText("🔊 Preview Audio")
        else:
            self.media_player.setSource(QUrl.fromLocalFile(self.current_wav_path))
            self.media_player.play()
            self.preview_audio_btn.setText("⏸ Stop Audio")

    def start_pipeline(self):
        files = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == Qt.Checked and item.text().endswith(".scd"):
                files.append(item.text())
        
        if not files:
            QMessageBox.warning(self, "No Files Selected", "No .scd files checked! Please check at least one file to render.")
            return
            
        out_dir = self.out_dir_edit.text().strip()
        if not os.path.isdir(out_dir):
            QMessageBox.warning(self, "Invalid Path", "Output directory does not exist.")
            return

        self.queue = files
        self.run_btn.setEnabled(False); self.cancel_btn.setEnabled(True); self.file_list.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.select_all_btn.setEnabled(False)
        self.deselect_all_btn.setEnabled(False)
        self.preview_audio_btn.setEnabled(False)
        self.progress.setValue(0)
        self.duration_label.setText("Estimated Duration: Calculating...")
        log.info(f"Starting queue processing: {len(self.queue)} file(s).")
        
        self.process_next_in_queue()

    def process_next_in_queue(self):
        if self.worker_thread is not None:
            self.worker_thread.quit()
            self.worker_thread.wait(5000) 
            self.worker_thread = None
            self.worker = None

        if len(self.queue) == 0:
            self._reset_controls()
            log.info("\n✓✓ ALL QUEUE ITEMS COMPLETED ✓✓")
            self.progress.setFormat("Finished")
            self.state_label.setText("FINISHED")
            self.state_label.setStyleSheet("font-weight: bold; color: #4CAF50; padding: 2px 6px;")
            return

        filepath = self.queue.pop(0)
        filename = os.path.basename(filepath)
        log.info(f"\n--- Processing: {filename} ---")
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                sc_code = f.read()
        except Exception as e:
            log.error(f"[ERROR] Could not read {filename}: {e}")
            self.process_next_in_queue()
            return

        desc = self.desc_edit.toPlainText().strip() or ">> Executing SuperCollider Script."
        base_name = os.path.splitext(filename)[0]
        out_mp4 = os.path.join(self.out_dir_edit.text().strip(), f"{base_name}_viz.mp4")
        
        fps, w, h = self.fps_spin.value(), self.width_spin.value(), self.height_spin.value()
        
        self.worker_thread = QThread()
        self.worker = PipelineWorker(
            sc_code, desc, out_mp4, fps=fps, width=w, height=h, 
            typing_style=self.type_style_combo.currentText(), 
            visual_style=self.viz_style_combo.currentText()
        )
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.log.connect(lambda msg: log.info(str(msg).strip()))
        self.worker.progress.connect(self.on_progress)
        self.worker.state_changed.connect(self.on_state_changed)
        self.worker.frame_preview.connect(self.on_frame_preview)
        self.worker.wav_ready.connect(self.on_wav_ready)
        self.worker.duration_ready.connect(self.on_duration_ready)
        
        self.worker.finished.connect(self.on_item_finished)
        self.worker.error.connect(self.on_item_error)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.error.connect(self.worker_thread.quit)
        
        self.worker_thread.start()

    @Slot(str)
    def on_wav_ready(self, wav_path):
        self.current_wav_path = wav_path
        self.preview_audio_btn.setEnabled(True)

    @Slot(float, int)
    def on_duration_ready(self, duration, frames):
        self.duration_label.setText(f"Estimated Duration: {duration:.2f}s ({frames} frames)")

    def on_item_finished(self, mp4_path):
        log.info(f"✓ SUCCESS — Saved: {mp4_path}")
        self.process_next_in_queue()

    def on_item_error(self, msg):
        log.error(f"✗ ERROR: {msg}")
        self.process_next_in_queue()

    def cancel_pipeline(self):
        if self.worker: self.worker.cancel()
        self.queue.clear()
        log.info("[USER] Cancellation requested. Finishing current item safely and aborting queue.")
        self.cancel_btn.setEnabled(False)

    @Slot(int, str)
    def on_progress(self, val, text):
        self.progress.setValue(val)
        self.progress.setFormat(f"{val}% — {text}" if text else f"{val}%")

    @Slot(str)
    def on_state_changed(self, name):
        self.state_label.setText(name)
        if name == "ERROR": 
            self.state_label.setStyleSheet("font-weight: bold; color: #F44336; padding: 2px 6px;")
        elif name in ("COMPLETE", "FINISHED"): 
            self.state_label.setStyleSheet("font-weight: bold; color: #4CAF50; padding: 2px 6px;")
        else: 
            self.state_label.setStyleSheet("font-weight: bold; color: #007ACC; padding: 2px 6px;")

    @Slot(object)
    def on_frame_preview(self, img):
        if img is None or img.isNull(): return
        scaled = img.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(QPixmap.fromImage(scaled))

    def _reset_controls(self):
        self.run_btn.setEnabled(True); self.cancel_btn.setEnabled(False); self.file_list.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.select_all_btn.setEnabled(True)
        self.deselect_all_btn.setEnabled(True)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        pm = self.preview_label.pixmap()
        if pm and not pm.isNull():
            self.preview_label.setPixmap(pm.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def closeEvent(self, event):
        if self.worker:
            self.worker.cancel()
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait(5000)
            
        self.settings.setValue("output_folder", self.out_dir_edit.text())
        self.settings.setValue("layout", self.layout_combo.currentText())
        self.settings.setValue("typing_style", self.type_style_combo.currentText())
        self.settings.setValue("visual_style", self.viz_style_combo.currentText())
        self.settings.setValue("fps", self.fps_spin.value())
        self.settings.setValue("width", self.width_spin.value())
        self.settings.setValue("height", self.height_spin.value())
        self.settings.setValue("desc_text", self.desc_edit.toPlainText())
        super().closeEvent(event)

# ============================================================================
# Entry Point
# ============================================================================
if __name__ == "__main__":
    log.info("Application launching...")
    try:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        window = MainWindow()
        window.show()
        exit_code = app.exec()
        log.info("Application exited with code %d", exit_code)
        sys.exit(exit_code)
    except Exception as e:
        log.exception("Fatal error in main: %s", e)
        raise