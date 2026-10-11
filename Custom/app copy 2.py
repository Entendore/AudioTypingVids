"""
SuperCollider NRT Visualizer (Dual-Phase Code & Audio Pipeline)
================================================================
- Phase 1: Cinematic terminal animation of the actual SC code (3s).
- Phase 2: High-performance audio waveform visualization.
- Concurrent audio generation (sclang + scsynth) running in background thread.
- Audio delayed by 3s via FFmpeg 'adelay' to sync perfectly with Phase 1 animation.
- Zero-disk-I/O raw frame streaming via memoryview mapping.
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
from enum import Enum, auto
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLabel, QMessageBox, QProgressBar, QComboBox,
    QFileDialog, QSpinBox, QGroupBox, QLineEdit
)
from PySide6.QtCore import (
    QThread, QObject, Signal, Slot, Qt, QRect, QRectF, QPointF, QSize
)
from PySide6.QtGui import (
    QImage, QPainter, QColor, QFont, QPen, QBrush, QLinearGradient,
    QFontMetrics, QPixmap, QRadialGradient
)
import numpy as np

# ============================================================================
# Logging
# ============================================================================
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
# SuperCollider NRT Test Scripts
# ============================================================================
NRT_TESTS = {
    "1. Simple Sine Wave (3 sec)": {
        "description": (
            ">> AUDIO ENGINE ONLINE.\n"
            ">> Generating pure 440 Hz sine wave.\n"
            ">> Duration: 3 seconds. Envelope: linen(0.1, 2.8, 0.1)."
        ),
        "code": """// NRT Test: Simple Sine Wave
(
var def = SynthDef(\\nrt_sine, { arg out=0, freq=440;
    var sig = SinOsc.ar(freq) * 0.2 * EnvGen.ar(Env.linen(0.1, 2.8, 0.1), doneAction: 2);
    Out.ar(out, sig ! 2);
}).asBytes;

var bundles = [
    [0.0, [\\d_recv, def]],
    [0.01, [\\s_new, \\nrt_sine, 1001, 0, 0, \\freq, 440]],
    [3.0, [\\g_freeAll, 0]],
    [3.01, [\\quit, 0]]
];

var f = File("__SCORE_PATH__", "wb");
bundles.do({ |bundle|
    var data = bundle.asRawOSC;
    var sz = data.size;
    f.write(Int8Array[(sz >> 24) & 255, (sz >> 16) & 255, (sz >> 8) & 255, sz & 255]);
    f.write(data);
});
f.close;

"SCORE_WRITTEN".postln;
)
"""
    },
    "2. Major Chord (3 sec)": {
        "description": (
            ">> SYNTHESIS: Additive Harmony.\n"
            ">> Rendering C major chord (C4-E4-G4).\n"
            ">> Three sine oscillators with exponential decay envelopes."
        ),
        "code": """// NRT Test: Major Chord (C-E-G)
(
var def = SynthDef(\\nrt_chord, { arg out=0, freq=440;
    var sig = SinOsc.ar(freq) * 0.15 * EnvGen.ar(Env.linen(0.5, 2.0, 0.5), doneAction: 2);
    Out.ar(out, sig ! 2);
}).asBytes;

var bundles = [
    [0.0, [\\d_recv, def]],
    [0.01, [\\s_new, \\nrt_chord, 1001, 0, 0, \\freq, 261.63]],
    [0.01, [\\s_new, \\nrt_chord, 1002, 0, 0, \\freq, 329.63]],
    [0.01, [\\s_new, \\nrt_chord, 1003, 0, 0, \\freq, 392.00]],
    [3.0, [\\g_freeAll, 0]],
    [3.01, [\\quit, 0]]
];

var f = File("__SCORE_PATH__", "wb");
bundles.do({ |bundle|
    var data = bundle.asRawOSC;
    var sz = data.size;
    f.write(Int8Array[(sz >> 24) & 255, (sz >> 16) & 255, (sz >> 8) & 255, sz & 255]);
    f.write(data);
});
f.close;

"SCORE_WRITTEN".postln;
)
"""
    },
    "3. Frequency Sweep (5 sec)": {
        "description": (
            ">> SYNTHESIS: Exponential Frequency Modulation.\n"
            ">> Sweep range: 200 Hz to 800 Hz.\n"
            ">> Oscillator: Sawtooth. Duration: 5 seconds."
        ),
        "code": """// NRT Test: Frequency Sweep
(
var def = SynthDef(\\nrt_sweep, { arg out=0, start=200, end=800, dur=4;
    var freq = XLine.kr(start, end, dur);
    var sig = Saw.ar(freq) * 0.2 * EnvGen.ar(Env.linen(0.1, 4.8, 0.1), doneAction: 2);
    Out.ar(out, sig ! 2);
}).asBytes;

var bundles = [
    [0.0, [\\d_recv, def]],
    [0.01, [\\s_new, \\nrt_sweep, 1001, 0, 0, \\start, 200, \\end, 800, \\dur, 4]],
    [5.0, [\\g_freeAll, 0]],
    [5.01, [\\quit, 0]]
];

var f = File("__SCORE_PATH__", "wb");
bundles.do({ |bundle|
    var data = bundle.asRawOSC;
    var sz = data.size;
    f.write(Int8Array[(sz >> 24) & 255, (sz >> 16) & 255, (sz >> 8) & 255, sz & 255]);
    f.write(data);
});
f.close;

"SCORE_WRITTEN".postln;
)
"""
    },
    "4. FM Synthesis Bell (4 sec)": {
        "description": (
            ">> SYNTHESIS: 2-Operator FM.\n"
            ">> Carrier: 440 Hz. Modulator Ratio: 2.0.\n"
            ">> Index: 3.0. Envelope: Percussive (0.01s attack, 3.5s decay)."
        ),
        "code": """// NRT Test: FM Synthesis Bell
(
var def = SynthDef(\\nrt_fm, { arg out=0, freq=440, car=1, mod=2, index=3, dur=3.5;
    var modulator = SinOsc.ar(freq * mod) * (freq * index);
    var sig = SinOsc.ar(freq * car + modulator) * 0.2 * EnvGen.ar(Env.perc(0.01, dur), doneAction: 2);
    Out.ar(out, sig ! 2);
}).asBytes;

var bundles = [
    [0.0, [\\d_recv, def]],
    [0.01, [\\s_new, \\nrt_fm, 1001, 0, 0, \\freq, 440, \\dur, 3.5]],
    [4.0, [\\g_freeAll, 0]],
    [4.01, [\\quit, 0]]
];

var f = File("__SCORE_PATH__", "wb");
bundles.do({ |bundle|
    var data = bundle.asRawOSC;
    var sz = data.size;
    f.write(Int8Array[(sz >> 24) & 255, (sz >> 16) & 255, (sz >> 8) & 255, sz & 255]);
    f.write(data);
});
f.close;

"SCORE_WRITTEN".postln;
)
"""
    }
}

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
    COMPUTING_AUDIO_ENVELOPE = auto()
    INITIALIZING_RENDERER = auto()
    STARTING_ENCODER = auto()
    STREAMING_FRAMES = auto()
    FINALIZING_MP4 = auto()
    CLEANUP = auto()
    COMPLETE = auto()
    ERROR = auto()

# ============================================================================
# Audio Generation (SuperCollider NRT)
# ============================================================================
class AudioGenerator:
    @staticmethod
    def generate(sc_code, score_path, wav_path, temp_dir, log_fn, state_cb=None):
        def _cb(state, msg, pct):
            if state_cb: state_cb(state, msg, pct)

        _cb(PipelineState.PREPARING_SCRIPT, "Preparing SC script...", 5)
        final_sc_code = sc_code.replace("__SCORE_PATH__", score_path)
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
            if time.time() - start_time > 30:
                process.kill(); process.wait()
                raise Exception("sclang timed out.")
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
            raise Exception("sclang failed to write score.\nOutput:\n" + "".join(output_lines))

        _cb(PipelineState.RENDERING_AUDIO_WAV, "Running scsynth -N to render audio...", 15)
        scsynth = shutil.which('scsynth')
        if not scsynth: raise Exception("scsynth not found on PATH")
        
        cmd = [scsynth, '-o', '2', '-N', score_path, '_', wav_path, '44100', 'WAV', 'int16']
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
            text=True, encoding='utf-8', errors='replace', timeout=60
        )
        if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 1024:
            raise Exception(f"scsynth failed.\nOutput:\n{result.stdout}\n{result.stderr}")

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
    def __init__(self, text, duration, typing_end_ratio=0.6):
        self.text = text
        self.duration = duration
        self.typing_end = max(0.5, duration * typing_end_ratio)

    def visible_text(self, t):
        if t >= self.typing_end: return self.text
        progress = max(0.0, t / self.typing_end)
        eased = 1 - (1 - progress) ** 3 # Cubic ease-out
        return self.text[:int(len(self.text) * eased)]

    def cursor_visible(self, t, blink_rate=2.5):
        return int(t * blink_rate) % 2 == 0

# ============================================================================
# Dual-Phase Frame Renderer
# ============================================================================
class FrameRenderer:
    def __init__(self, audio_data, text, sc_code, width=1280, height=720, fps=30):
        self.audio = audio_data
        self.text = text
        self.sc_code = sc_code
        self.width = width
        self.height = height
        self.fps = fps
        
        # Phase 1: Code Animation (3 seconds)
        self.intro_duration = 3.0
        self.code_typing = TypingAnimator(sc_code, self.intro_duration, 0.8)
        
        # Phase 2: Audio Visualization
        self.audio_typing = TypingAnimator(text, audio_data.duration, 0.4)
        
        self.n_bars = 120
        self.envelope = audio_data.get_envelope(self.n_bars)
        # Offset frame amplitudes so they start rendering at t=0 of Phase 2
        self.frame_amps = audio_data.get_frame_amplitudes(fps)
        
        # Fonts
        self.font_title = QFont("Consolas", 14, QFont.Bold)
        self.font_time = QFont("Consolas", 12)
        self.font_body = QFont("Consolas", 22)
        self.font_label = QFont("Consolas", 10)
        self.font_code = QFont("Consolas", 16)  # For Phase 1

        # PRE-ALLOCATED CANVAS
        self.canvas = QImage(self.width, self.height, QImage.Format_RGBA8888)

    def render_frame_to_canvas(self, frame_idx):
        t = frame_idx / self.fps
        
        # Reuse the same canvas
        self.canvas.fill(Qt.transparent)
        p = QPainter(self.canvas)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        if t < self.intro_duration:
            self._draw_code_phase(p, t)
        else:
            audio_t = t - self.intro_duration
            self._draw_audio_phase(p, audio_t, frame_idx - int(self.intro_duration * self.fps))
        
        p.end()
        return self.canvas

    # --- PHASE 1: CODE ANIMATION ---
    def _draw_code_phase(self, p, t):
        # Dark terminal background
        p.fillRect(0, 0, self.width, self.height, QColor(12, 12, 18))
        
        # Terminal Window Frame
        p.setPen(QPen(QColor(0, 200, 255, 150), 2))
        p.setBrush(QColor(20, 22, 30))
        rect = QRect(40, 40, self.width - 80, self.height - 100)
        p.drawRoundedRect(rect, 10, 10)

        # Terminal Header
        p.setPen(QColor(150, 160, 180))
        p.setFont(self.font_label)
        p.drawText(rect.adjusted(15, 10, 0, 0), Qt.AlignTop | Qt.AlignLeft, "superCollider_nrt.scd")
        
        p.setPen(QColor(255, 100, 100))
        p.drawEllipse(rect.left() + 20, rect.top() + 15, 8, 8)
        p.setPen(QColor(255, 200, 100))
        p.drawEllipse(rect.left() + 35, rect.top() + 15, 8, 8)
        p.setPen(QColor(100, 255, 100))
        p.drawEllipse(rect.left() + 50, rect.top() + 15, 8, 8)

        # Code Text Typing
        visible_code = self.code_typing.visible_text(t)
        if self.code_typing.cursor_visible(t):
            visible_code += "█"

        p.setPen(QColor(0, 255, 150))
        p.setFont(self.font_code)
        
        text_area = rect.adjusted(20, 50, -20, -40)
        p.drawText(text_area, Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap, visible_code)

        # Progress Bar for Compilation
        pb_y = self.height - 50
        pb_h = 6
        pb_x = 60
        pb_w = self.width - 120
        
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(40, 50, 70))
        p.drawRect(pb_x, pb_y, pb_w, pb_h)

        progress = t / self.intro_duration
        grad = QLinearGradient(pb_x, 0, pb_x + pb_w, 0)
        grad.setColorAt(0.0, QColor(0, 255, 150))
        grad.setColorAt(1.0, QColor(0, 200, 255))
        p.setBrush(QBrush(grad))
        p.drawRect(pb_x, pb_y, int(pb_w * progress), pb_h)

        p.setPen(QColor(200, 220, 240))
        p.setFont(self.font_time)
        p.drawText(pb_x, pb_y - 10, f"Compiling SuperCollider Script... {int(progress*100)}%")

    # --- PHASE 2: AUDIO VISUALIZATION ---
    def _draw_audio_phase(self, p, t, audio_frame_idx):
        amp = float(self.frame_amps[audio_frame_idx]) if audio_frame_idx < len(self.frame_amps) else 0.0
        
        self._draw_background(p, amp)
        self._draw_circular_viz(p, t, amp)
        self._draw_header(p, t)
        self._draw_typing_text(p, t)
        self._draw_waveform(p, t)
        self._draw_amplitude_meter(p, audio_frame_idx)
        self._draw_progress_bar(p, t)

    def _draw_background(self, p, amp):
        grad = QLinearGradient(0, 0, 0, self.height)
        grad.setColorAt(0.0, QColor(15, 18, 35))
        grad.setColorAt(0.5, QColor(10, 12, 25))
        grad.setColorAt(1.0, QColor(4, 5, 12))
        p.fillRect(0, 0, self.width, self.height, QBrush(grad))

        glow = QRadialGradient(self.width/2, self.height/2, self.width/2)
        glow.setColorAt(0, QColor(0, 150, 255, int(60 * amp)))
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, self.width, self.height, QBrush(glow))

        p.setPen(QPen(QColor(80, 100, 150, 22), 1))
        for x in range(0, self.width, 40): p.drawLine(x, 0, x, self.height)
        for y in range(0, self.height, 40): p.drawLine(0, y, self.width, y)

    def _draw_circular_viz(self, p, t, amp):
        cx, cy = self.width // 2, int(self.height * 0.35)
        base_r = 80
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), base_r, base_r)

        playhead_progress = t / max(0.001, self.audio.duration)
        n_segments = 80
        
        for i in range(n_segments):
            angle = (i / n_segments) * 2 * math.pi
            env_idx = int((i / n_segments) * self.n_bars)
            env_val = float(self.envelope[env_idx])
            
            r1 = base_r + 10
            r2 = base_r + 10 + (env_val * 60 * amp * 2)
            
            x1 = cx + math.cos(angle) * r1
            y1 = cy + math.sin(angle) * r1
            x2 = cx + math.cos(angle) * r2
            y2 = cy + math.sin(angle) * r2
            
            seg_progress = i / n_segments
            if seg_progress <= playhead_progress:
                color = self._lerp_color(QColor(0, 200, 255), QColor(255, 100, 200), seg_progress)
                color.setAlpha(220)
            else:
                color = QColor(70, 90, 130, 80)
                
            p.setPen(QPen(color, 2))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _draw_header(self, p, t):
        p.setPen(QColor(200, 220, 240))
        p.setFont(self.font_title)
        p.drawText(40, 32, "◢ SuperCollider NRT Visualizer")

        p.setPen(QColor(0, 220, 255))
        p.setFont(self.font_time)
        time_str = f"t = {t:6.2f}s / {self.audio.duration:6.2f}s"
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(time_str)
        p.drawText(self.width - 40 - tw, 32, time_str)

    def _draw_typing_text(self, p, t):
        text_area = QRect(60, int(self.height*0.55), self.width - 120, int(self.height * 0.25))
        visible = self.audio_typing.visible_text(t)

        if self.audio_typing.cursor_visible(t):
            visible = visible + "▎"

        for offset, alpha in [(3, 30), (2, 60), (1, 120)]:
            p.setPen(QColor(0, 200, 255, alpha))
            p.setFont(self.font_body)
            p.drawText(text_area.adjusted(offset, offset, offset, offset),
                       Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap, visible)

        p.setPen(QColor(240, 250, 255))
        p.drawText(text_area, Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap, visible)

        p.setPen(QPen(QColor(0, 200, 255, 60), 1))
        p.drawLine(60, text_area.bottom() + 10, self.width - 60, text_area.bottom() + 10)

    def _draw_waveform(self, p, t):
        wf_x = 60
        wf_y = int(self.height * 0.85)
        wf_w = self.width - 120
        wf_h = int(self.height * 0.10)
        mid_y = wf_y + wf_h // 2

        p.fillRect(wf_x, wf_y, wf_w, wf_h, QColor(0, 0, 0, 110))
        p.setPen(QPen(QColor(100, 130, 170, 110), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(wf_x, wf_y, wf_w, wf_h)

        bar_w = wf_w / self.n_bars
        playhead_progress = t / max(0.001, self.audio.duration)

        p.setPen(Qt.NoPen)
        for i, amp_val in enumerate(self.envelope):
            x = wf_x + i * bar_w
            h = amp_val * (wf_h / 2) * 0.95
            bar_progress = i / self.n_bars
            
            if bar_progress <= playhead_progress:
                color = self._lerp_color(QColor(0, 200, 255), QColor(255, 100, 200), bar_progress)
                color.setAlpha(230)
            else:
                color = QColor(70, 90, 130, 100)
            p.setBrush(color)
            p.drawRect(QRectF(x, mid_y - h, max(1.0, bar_w - 1.0), 2.0 * h))

        ph_x = wf_x + playhead_progress * wf_w
        p.setPen(QPen(QColor(255, 255, 255, 230), 2))
        p.drawLine(QPointF(ph_x, wf_y - 6), QPointF(ph_x, wf_y + wf_h + 6))

    def _draw_amplitude_meter(self, p, frame_idx):
        amp = float(self.frame_amps[frame_idx]) if frame_idx < len(self.frame_amps) else 0.0
        bar_x = self.width - 45
        bar_y = int(self.height * 0.85)
        bar_w = 10
        bar_h = int(self.height * 0.10)

        p.setPen(QPen(QColor(100, 130, 170, 110), 1))
        p.setBrush(QColor(0, 0, 0, 110))
        p.drawRect(bar_x, bar_y, bar_w, bar_h)

        fill_h = int(bar_h * amp)
        if fill_h > 0:
            grad = QLinearGradient(0, bar_y + bar_h, 0, bar_y)
            grad.setColorAt(0.0, QColor(0, 200, 255))
            grad.setColorAt(1.0, QColor(255, 100, 200))
            p.setBrush(QBrush(grad))
            p.setPen(Qt.NoPen)
            p.drawRect(bar_x, bar_y + bar_h - fill_h, bar_w, fill_h)

    def _draw_progress_bar(self, p, t):
        pb_y = self.height - 22
        pb_h = 4
        pb_x = 60
        pb_w = self.width - 120

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(40, 50, 70))
        p.drawRect(pb_x, pb_y, pb_w, pb_h)

        progress = t / max(0.001, self.audio.duration)
        grad = QLinearGradient(pb_x, 0, pb_x + pb_w, 0)
        grad.setColorAt(0.0, QColor(0, 200, 255))
        grad.setColorAt(1.0, QColor(255, 100, 200))
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
# Video Encoder (Raw Memory-Mapped Stream + Audio Delay)
# ============================================================================
class VideoEncoder:
    @staticmethod
    def start_ffmpeg_process(wav_path, output_mp4, fps, width, height, intro_duration, log_fn):
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            raise Exception("ffmpeg not found on PATH")

        # Delay audio by intro_duration (in ms) to sync with Phase 2
        delay_ms = int(intro_duration * 1000)
        
        cmd = [
            ffmpeg, '-y',
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{width}x{height}',
            '-pix_fmt', 'rgba',
            '-r', str(fps),
            '-i', 'pipe:0',
            '-i', wav_path,
            '-c:v', 'libx264',
            '-preset', 'veryfast',
            '-crf', '20',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-af', f'adelay={delay_ms}|{delay_ms}',  # | denotes stereo channels
            '-shortest',
            '-movflags', '+faststart',
            output_mp4
        ]
        log_fn("  Starting FFmpeg raw stream pipe (Audio Delay: {}ms)...".format(delay_ms))
        
        proc = subprocess.Popen(
            cmd, 
            stdin=subprocess.PIPE, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        
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
            # PySide6 versions differ: older returns sip.voidptr, newer returns memoryview
            ptr = qimage.constBits()
            if hasattr(ptr, 'setsize'):
                ptr.setsize(qimage.sizeInBytes())
            
            # Write directly to stdin (Zero-copy if memoryview, fast copy if bytes)
            proc.stdin.write(ptr)
        except BrokenPipeError:
            raise Exception("Broken pipe to FFmpeg. Check FFmpeg logs.")

    @staticmethod
    def finalize(proc, log_fn):
        if proc.poll() is None:
            proc.stdin.close()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                raise Exception("FFmpeg timed out during finalization.")
        if proc.returncode != 0:
            raise Exception(f"FFmpeg exited with error code {proc.returncode}")
        
# ============================================================================
# Pipeline Worker
# ============================================================================
class PipelineWorker(QObject):
    log = Signal(str)
    progress = Signal(int, str)
    state_changed = Signal(str)
    frame_preview = Signal(object)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, sc_code, description, output_mp4, fps=30, width=1280, height=720):
        super().__init__()
        self.sc_code = sc_code
        self.description = description
        self.output_mp4 = output_mp4
        self.fps = fps
        self.width = width
        self.height = height
        self.temp_dir = tempfile.mkdtemp(prefix="nrt_viz_")
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _set_state(self, state, message="", progress_val=-1):
        log.info(f"STATE -> {state.name}: {message}")
        self.state_changed.emit(state.name)
        if message: self.log.emit(f"[{state.name}] {message}")
        if progress_val >= 0: self.progress.emit(progress_val, message if message else state.name)

    @Slot()
    def run(self):
        proc = None
        audio_thread = None
        try:
            # 1. Check dependencies
            self._set_state(PipelineState.CHECKING_DEPS, "Checking dependencies...", 2)
            missing = [c for c in ['sclang', 'scsynth', 'ffmpeg'] if not shutil.which(c)]
            if missing:
                raise Exception(f"Missing on PATH: {', '.join(missing)}.")

            # 2. Prepare paths
            score_path = os.path.join(self.temp_dir, "score.osc").replace('\\', '/')
            wav_path = os.path.join(self.temp_dir, "audio.wav").replace('\\', '/')

            # 3. Start Audio Generation in Background Thread
            def generate_audio_async():
                try:
                    AudioGenerator.generate(
                        self.sc_code, score_path, wav_path, self.temp_dir, self.log.emit, self._set_state
                    )
                except Exception as e:
                    self.log.emit(f"[AUDIO_THREAD] FATAL: {e}")
                    self._cancel = True # Trigger pipeline cancellation

            self._set_state(PipelineState.COMPILING_OSC_SCORE, "Starting concurrent audio generation...", 5)
            audio_thread = threading.Thread(target=generate_audio_async, daemon=True)
            audio_thread.start()

            # Wait for audio thread to finish (it updates UI via callbacks)
            # Timeout safety
            timeout = 45.0
            start_wait = time.time()
            while audio_thread.is_alive():
                if self._cancel:
                    raise Exception("Cancelled by user or Audio thread failed.")
                if time.time() - start_wait > timeout:
                    raise Exception("Audio generation timed out.")
                time.sleep(0.1)

            if not os.path.exists(wav_path):
                raise Exception("Audio generation failed silently. Check logs.")

            # 4. Analyze audio
            self._set_state(PipelineState.READING_WAV_FILE, "Reading WAV file...", 20)
            audio_data = AudioData(wav_path)
            
            intro_duration = 3.0
            total_duration = intro_duration + audio_data.duration
            n_frames = int(total_duration * self.fps) + 1
            self.log.emit(f"  Total Video Duration: {total_duration:.2f}s | Frames: {n_frames}")

            self._set_state(PipelineState.COMPUTING_AUDIO_ENVELOPE, "Computing audio envelope...", 25)

            # 5. Initialize Renderer
            self._set_state(PipelineState.INITIALIZING_RENDERER, "Initializing dual-phase renderer...", 28)
            renderer = FrameRenderer(audio_data, self.description, self.sc_code, self.width, self.height, self.fps)

            # 6. Start FFmpeg
            self._set_state(PipelineState.STARTING_ENCODER, "Starting FFmpeg process (with audio delay)...", 30)
            proc = VideoEncoder.start_ffmpeg_process(wav_path, self.output_mp4, self.fps, self.width, self.height, intro_duration, self.log.emit)

            # 7. Stream Frames
            self._set_state(PipelineState.STREAMING_FRAMES, "Streaming raw frames to FFmpeg...", 32)
            
            start_stream_time = time.time()
            for i in range(n_frames):
                if self._cancel:
                    if proc: 
                        proc.stdin.close()
                        proc.kill()
                    raise Exception("Cancelled by user.")
                
                img = renderer.render_frame_to_canvas(i)
                VideoEncoder.write_frame(proc, img, self.log.emit)
                
                if i % 3 == 0:
                    elapsed = time.time() - start_stream_time
                    actual_fps = (i + 1) / elapsed if elapsed > 0 else 0
                    eta = (n_frames - i - 1) / actual_fps if actual_fps > 0 else 0
                    
                    pct = 32 + int((i / max(1, n_frames)) * 65)
                    msg = f"Streaming {i+1}/{n_frames} ({actual_fps:.1f} fps, ETA: {eta:.1f}s)"
                    self.progress.emit(pct, msg)
                    
                if i % 10 == 0:
                    self.frame_preview.emit(img.copy())

            # 8. Finalize MP4
            self._set_state(PipelineState.FINALIZING_MP4, "Finalizing MP4 (closing pipe)...", 97)
            VideoEncoder.finalize(proc, self.log.emit)
            if not os.path.exists(self.output_mp4):
                raise Exception("FFmpeg did not produce the output MP4 file.")

            # 9. Done
            self._set_state(PipelineState.COMPLETE, "Complete!", 100)
            self.finished.emit(self.output_mp4)

        except subprocess.TimeoutExpired:
            if proc: proc.kill()
            self._set_state(PipelineState.ERROR, "Process timed out.", 0)
            self.error.emit("A subprocess (sclang/scsynth/ffmpeg) timed out.")
        except Exception as e:
            if proc: proc.kill()
            log.exception("Pipeline failed:")
            self._set_state(PipelineState.ERROR, str(e), 0)
            self.error.emit(str(e))
        finally:
            self._set_state(PipelineState.CLEANUP, "Cleaning up temporary files...", 99)
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            except Exception as e:
                log.warning(f"Cleanup failed: {e}")

# ============================================================================
# Main Window
# ============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SuperCollider NRT Visualizer → MP4 (Dual-Phase Pipeline)")
        self.resize(1100, 780)
        log.info("UI initializing...")

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Top
        top = QHBoxLayout()
        top.addWidget(QLabel("Test:"))
        self.test_combo = QComboBox()
        self.test_combo.addItems(NRT_TESTS.keys())
        self.test_combo.currentTextChanged.connect(self.on_test_changed)
        top.addWidget(self.test_combo, 2)
        top.addWidget(QLabel("Output MP4:"))
        self.mp4_edit = QLineEdit(os.path.join(os.getcwd(), "nrt_visualization.mp4"))
        top.addWidget(self.mp4_edit, 2)
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.on_browse)
        top.addWidget(self.browse_btn)
        root.addLayout(top)

        # Description
        desc_group = QGroupBox("Typing Animation Text (Audio Phase)")
        desc_layout = QVBoxLayout(desc_group)
        self.desc_edit = QTextEdit()
        self.desc_edit.setStyleSheet("background-color: #1E1E2E; color: #D4D4D4; font-family: Consolas; font-size: 13px;")
        self.desc_edit.setMaximumHeight(110)
        desc_layout.addWidget(self.desc_edit)
        root.addWidget(desc_group)

        # Options
        opts = QHBoxLayout()
        opts.addWidget(QLabel("FPS:"))
        self.fps_spin = QSpinBox(); self.fps_spin.setRange(10, 60); self.fps_spin.setValue(30)
        opts.addWidget(self.fps_spin)
        opts.addWidget(QLabel("Width:"))
        self.width_spin = QSpinBox(); self.width_spin.setRange(640, 1920); self.width_spin.setSingleStep(80); self.width_spin.setValue(1280)
        opts.addWidget(self.width_spin)
        opts.addWidget(QLabel("Height:"))
        self.height_spin = QSpinBox(); self.height_spin.setRange(360, 1080); self.height_spin.setSingleStep(60); self.height_spin.setValue(720)
        opts.addWidget(self.height_spin)
        opts.addStretch()
        root.addLayout(opts)

        # Controls
        run_row = QHBoxLayout()
        self.run_btn = QPushButton("▶  Generate MP4")
        self.run_btn.setStyleSheet("background-color: #007ACC; color: white; font-weight: bold; padding: 10px; font-size: 14px; border-radius: 4px;")
        self.run_btn.clicked.connect(self.start_pipeline)
        run_row.addWidget(self.run_btn)
        self.cancel_btn = QPushButton("Cancel"); self.cancel_btn.setEnabled(False)
        self.cancel_btn.setStyleSheet("padding: 10px; font-size: 14px;")
        self.cancel_btn.clicked.connect(self.cancel_pipeline)
        run_row.addWidget(self.cancel_btn)
        run_row.addStretch()
        root.addLayout(run_row)

        # State
        state_row = QHBoxLayout()
        state_row.addWidget(QLabel("State:"))
        self.state_label = QLabel("IDLE")
        self.state_label.setStyleSheet("font-weight: bold; color: #007ACC; padding: 2px 6px;")
        state_row.addWidget(self.state_label)
        state_row.addStretch()
        root.addLayout(state_row)

        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.setValue(0)
        self.progress.setFormat("Idle"); self.progress.setFixedHeight(22)
        root.addWidget(self.progress)

        # Preview
        root.addWidget(QLabel("Live Frame Preview:"))
        self.preview_label = QLabel(); self.preview_label.setMinimumHeight(280)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("background-color: #111122; border: 1px solid #2A2A40;")
        self.preview_label.setText("Preview will appear here during rendering...")
        root.addWidget(self.preview_label, 1)

        # Log
        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("Console Log:"))
        log_header.addStretch()
        self.clear_log_btn = QPushButton("Clear")
        self.clear_log_btn.setStyleSheet("padding: 2px 10px;")
        log_header.addWidget(self.clear_log_btn)
        root.addLayout(log_header)

        self.log_edit = QTextEdit(); self.log_edit.setReadOnly(True); self.log_edit.setMaximumHeight(140)
        self.log_edit.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4; font-family: Consolas; font-size: 12px;")
        root.addWidget(self.log_edit)
        self.clear_log_btn.clicked.connect(self.log_edit.clear)

        self.worker_thread = None
        self.worker = None
        self.on_test_changed(self.test_combo.currentText())

    def on_test_changed(self, name):
        info = NRT_TESTS.get(name, {})
        self.desc_edit.setPlainText(info.get("description", ""))

    def on_browse(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save MP4 as", self.mp4_edit.text(), "MP4 files (*.mp4)")
        if path:
            if not path.lower().endswith(".mp4"): path += ".mp4"
            self.mp4_edit.setText(path)

    def append_log(self, msg):
        self.log_edit.append(msg)
        sb = self.log_edit.verticalScrollBar(); sb.setValue(sb.maximum())

    def start_pipeline(self):
        name = self.test_combo.currentText()
        info = NRT_TESTS.get(name)
        if not info: return
        
        desc = self.desc_edit.toPlainText().strip()
        if not desc: return
        out_mp4 = self.mp4_edit.text().strip()
        if not out_mp4: return

        fps, w, h = self.fps_spin.value(), self.width_spin.value(), self.height_spin.value()

        self.run_btn.setEnabled(False); self.cancel_btn.setEnabled(True); self.test_combo.setEnabled(False)
        self.progress.setValue(0); self.progress.setFormat("Starting...")
        self.state_label.setText("STARTING")
        self.state_label.setStyleSheet("font-weight: bold; color: #007ACC; padding: 2px 6px;")
        self.log_edit.clear()
        self.append_log(f"Starting pipeline for: {name}")
        self.append_log(f"Output: {out_mp4}  ({w}x{h} @ {fps}fps)")

        self.worker_thread = QThread()
        self.worker = PipelineWorker(info["code"], desc, out_mp4, fps=fps, width=w, height=h)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker.run)
        self.worker.log.connect(self.append_log)
        self.worker.progress.connect(self.on_progress)
        self.worker.state_changed.connect(self.on_state_changed)
        self.worker.frame_preview.connect(self.on_frame_preview)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.error.connect(self.worker_thread.quit)
        self.worker_thread.start()

    def cancel_pipeline(self):
        if self.worker:
            self.worker.cancel()
            self.append_log("[USER] Cancellation requested...")
            self.cancel_btn.setEnabled(False)

    @Slot(int, str)
    def on_progress(self, val, text):
        self.progress.setValue(val)
        self.progress.setFormat(f"{val}% — {text}" if text else f"{val}%")

    @Slot(str)
    def on_state_changed(self, name):
        self.state_label.setText(name)
        if name == "ERROR": self.state_label.setStyleSheet("font-weight: bold; color: #F44336; padding: 2px 6px;")
        elif name == "COMPLETE": self.state_label.setStyleSheet("font-weight: bold; color: #4CAF50; padding: 2px 6px;")
        else: self.state_label.setStyleSheet("font-weight: bold; color: #007ACC; padding: 2px 6px;")

    @Slot(object)
    def on_frame_preview(self, img):
        if img is None or img.isNull(): return
        scaled = img.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(QPixmap.fromImage(scaled))

    def on_finished(self, mp4_path):
        self._reset_controls()
        self.append_log(f"\n✓ SUCCESS — MP4 saved to: {mp4_path}")
        self.progress.setFormat("Done")
        reply = QMessageBox.information(self, "Success", f"MP4 generated!\n\n{mp4_path}\n\nOpen it now?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                if sys.platform == "win32": os.startfile(mp4_path)
                elif sys.platform == "darwin": subprocess.run(['open', mp4_path])
                else: subprocess.run(['xdg-open', mp4_path])
            except Exception as e:
                QMessageBox.warning(self, "Open failed", str(e))

    def on_error(self, msg):
        self._reset_controls()
        self.progress.setValue(0); self.progress.setFormat("Failed")
        self.append_log(f"\n✗ ERROR: {msg}")
        QMessageBox.critical(self, "Pipeline Failed", msg)

    def _reset_controls(self):
        self.run_btn.setEnabled(True); self.cancel_btn.setEnabled(False); self.test_combo.setEnabled(True)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        pm = self.preview_label.pixmap()
        if pm and not pm.isNull():
            self.preview_label.setPixmap(pm.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

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