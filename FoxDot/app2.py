# foxdot_studio.py

from __future__ import annotations
import os, sys, json, math, time, random, logging, platform, subprocess, threading, shutil
from pathlib import Path
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple, Callable
import numpy as np

# PySide6 Imports
from PySide6.QtCore import (QObject, Signal, QThread, Qt, QTimer, QUrl, QTime, 
                            QPointF, QRectF)
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QImage, QLinearGradient, 
                           QPainter, QPainterPath, QPen, QRadialGradient, 
                           QSyntaxHighlighter, QTextCharFormat)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QPushButton, QProgressBar, QStatusBar, 
                               QFileDialog, QMessageBox, QPlainTextEdit, QComboBox, 
                               QToolButton, QLabel, QSlider, QSplitter, QDockWidget, 
                               QDoubleSpinBox, QCheckBox, QSpinBox, QTabWidget, 
                               QGroupBox, QFormLayout, QLineEdit)

# ==========================================
# 1. CORE DATA STRUCTURES & CONFIG
# ==========================================

SR: int = 44100
FPS: int = 30

APP_ROOT = Path(__file__).resolve().parent
SETTINGS_DIR = APP_ROOT / ".foxdot_anim"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"
LOG_PATH = SETTINGS_DIR / "app.log"
INPUT_DIR = APP_ROOT / "input"
TMP_AUDIO_DIR = APP_ROOT / ".tmp_audio"

SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
INPUT_DIR.mkdir(parents=True, exist_ok=True)
TMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH, mode='w', encoding='utf-8'),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

class TokenType(Enum):
    KEYWORD = auto(); SYNTH = auto(); FX = auto(); SAMPLE = auto()
    NUMBER = auto(); STRING = auto(); COMMENT = auto()
    OPERATOR = auto(); PUNCTUATION = auto(); IDENTIFIER = auto(); WHITESPACE = auto()

class LayoutMode(Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"

@dataclass(frozen=True, slots=True)
class Token:
    text: str
    kind: TokenType

@dataclass(slots=True)
class FrameState:
    char_index: int = 0
    waveform: np.ndarray = field(default_factory=lambda: np.zeros(256, dtype=np.float32))
    spectrum: np.ndarray = field(default_factory=lambda: np.zeros(64, dtype=np.float32))
    beat_power: float = 0.0
    code_done: bool = False
    time: float = 0.0
    beat_on: bool = False
    beat_strength: float = 0.0
    peak_l: float = 0.0
    peak_r: float = 0.0
    rms: float = 0.0
    typing_progress: float = 0.0

@dataclass(frozen=True)
class Theme:
    name: str
    bg1: Tuple[int, int, int]; bg2: Tuple[int, int, int]
    w1: Tuple[int, int, int]; w2: Tuple[int, int, int]
    accent: Tuple[int, int, int]; kw: Tuple[int, int, int]
    sym: Tuple[int, int, int]; num: Tuple[int, int, int]
    cmt: Tuple[int, int, int]; txt: Tuple[int, int, int]
    str: Tuple[int, int, int]

    def color(self, key: str, alpha: int = 255) -> QColor:
        return QColor(*getattr(self, key), alpha)

@dataclass(frozen=True)
class Preset:
    name: str
    width: int
    height: int
    layout: LayoutMode
    split: float

@dataclass
class AudioEngineConfig:
    master_volume: float = 0.85
    base_duration: float = 16.0
    beat_sensitivity: float = 0.5
    typing_speed: float = 28.0
    cursor_blink_rate: float = 2.0
    cursor_char: str = "▋"
    typing_delay: float = 0.5
    wave_amplitude: float = 0.42
    particles_enabled: bool = True
    vu_meter: bool = True
    mirror_waveform: bool = True
    fill_waveform: bool = True
    beat_flash: bool = True
    show_spectrum: bool = False
    show_progress_bar: bool = True
    show_code_glow: bool = True
    show_line_numbers: bool = True
    show_typing_cursor: bool = True
    font_size_override: int = 0
    font_family: str = "Consolas"
    code_padding: int = 40
    line_spacing: int = 4
    particle_count: int = 80
    particle_burst_on_beat: int = 10
    theme_name: str = "Midnight Blue"
    preset_name: str = "YouTube (1920x1080)"
    export_fps: int = 30
    export_codec: str = "libx264"
    export_preset: str = "ultrafast"
    export_audio_codec: str = "aac"
    export_audio_bitrate: str = "192k"

    def to_dict(self) -> Dict[str, Any]: 
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AudioEngineConfig":
        valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid)

# Python + FoxDot keywords
KEYWORDS = frozenset({
    'def', 'class', 'if', 'else', 'elif', 'while', 'for', 'in', 'return',
    'import', 'from', 'as', 'with', 'try', 'except', 'finally', 'True',
    'False', 'None', 'and', 'or', 'not', 'is', 'lambda', 'pass', 'break',
    'continue', 'global', 'nonlocal', 'yield', 'assert', 'del', 'raise',
    'Clock', 'bpm', 'Player', 'Group', 'var', 'linvar', 'expvar', 'Pvar',
    'sinvar', 'rvar', 'Scale', 'Root', 'Key', 'P', 'Pseq', 'Prand', 'Pwhite',
    'Server', 'SynthDefs', 'Tempo', 'Metro', 'fill', 'stretch', 'degrees',
    'root', 'scale', 'dur', 'sus', 'amp', 'pan', 'rate', 'octave', 'shape'
})

SYNTH_SET = frozenset({
    'pluck', 'saw', 'sine', 'square', 'noise', 'bass', 'piano', 'klank',
    'marimba', 'blip', 'growl', 'pads', 'razor', 'dab', 'dirt', 'scatter',
    'sparkle', 'soprano', 'dub', 'dublead', 'metal', 'jvbass', 'punch',
    'prophet', 'space', 'wind', 'bird', 'casio', 'sitar', 'glass', 'crunch',
    'soft', 'arena', 'kpiano', 'jbass', 'hollow', 'howl', 'karp', 'ocarina',
    'quin', 'star', 'sigh', 'sinepad', 'violin', 'tb303', 'dsaw', 'fm',
    'blade', 'dark_ambience', 'kalimba', 'pretty_bell', 'ring_mod',
    'subpulse', 'sine_pb', 'snap', 'ks', 'gabber', 'sampler', 'play'
})

FX_SET = frozenset({
    'reverb', 'echo', 'flanger', 'distortion', 'compressor', 'lpf', 'hpf',
    'wobble', 'phaser', 'chorus', 'panner', 'slicer', 'krush', 'octaver',
    'bitcrush', 'fold', 'clip', 'highpass', 'lowpass', 'bandpass', 'ringmod',
    'vibrator', 'freqshift', 'tremolo', 'delay', 'reverse', 'envelope',
    'gain', 'shape', 'tanh', 'shifter', 'vibrato', 'spin', 'cut', 'slide',
    'bend', 'vib', 'pshift', 'bpf', 'freq', 'room', 'mix', 'feedback', 'phase'
})

SAMPLE_SET = frozenset({
    'bd', 'sn', 'cp', 'hh', 'oh', 'tom', 'ride', 'crash', 'splash',
    'cow', 'cy', 'boom', 'kick', 'snare', 'clap', 'hat', 'perc', 'tabla',
    'shake', 'tamb', 'guiro', 'clave', 'maraca', 'shaker', 'cabasa',
    'vibraslap', 'cuica', 'timbale', 'agogo', 'woodblock', 'whistle', 'silence'
})

class ThemeRegistry:
    _themes: Dict[str, Theme] = {}
    @classmethod
    def register(cls, t: Theme) -> None: cls._themes[t.name] = t
    @classmethod
    def get(cls, name: str) -> Theme: return cls._themes.get(name, cls.default())
    @classmethod
    def names(cls) -> List[str]: return list(cls._themes.keys())
    @classmethod
    def default(cls) -> Theme: return next(iter(cls._themes.values()))

ThemeRegistry.register(Theme("Midnight Blue", (15,15,28), (10,10,20), (0,255,180), (140,110,255), (0,200,255), (198,120,221), (219,191,130), (209,154,102), (98,114,164), (171,178,191), (152,195,121)))
ThemeRegistry.register(Theme("Dracula", (40,42,54), (30,31,40), (255,121,198), (189,147,249), (255,184,108), (255,121,198), (241,250,140), (139,233,253), (98,114,164), (248,248,242), (241,250,140)))
ThemeRegistry.register(Theme("Solarized Dark", (0,43,54), (7,54,66), (133,153,0), (38,139,210), (42,161,152), (203,75,22), (181,137,0), (220,50,47), (88,110,117), (253,246,227), (42,161,152)))
ThemeRegistry.register(Theme("Monokai", (39,40,34), (27,28,22), (249,38,114), (174,129,255), (102,217,239), (249,38,114), (230,219,116), (174,129,255), (117,113,94), (248,248,242), (230,219,116)))
ThemeRegistry.register(Theme("Gruvbox", (40,40,40), (29,32,33), (250,189,47), (214,93,14), (152,151,26), (204,36,29), (250,189,47), (215,153,33), (146,131,116), (235,219,178), (163,190,140)))

class PresetRegistry:
    _presets: Dict[str, Preset] = {}
    @classmethod
    def register(cls, p: Preset) -> None: cls._presets[p.name] = p
    @classmethod
    def get(cls, name: str) -> Preset: return cls._presets.get(name, cls.default())
    @classmethod
    def names(cls) -> List[str]: return list(cls._presets.keys())
    @classmethod
    def default(cls) -> Preset: return next(iter(cls._presets.values()))

PresetRegistry.register(Preset("YouTube (1920x1080)", 1920, 1080, LayoutMode.HORIZONTAL, 0.48))
PresetRegistry.register(Preset("TikTok (1080x1920)", 1080, 1920, LayoutMode.VERTICAL, 0.55))
PresetRegistry.register(Preset("Instagram (1080x1080)", 1080, 1080, LayoutMode.HORIZONTAL, 0.5))
PresetRegistry.register(Preset("Twitter (1280x720)", 1280, 720, LayoutMode.HORIZONTAL, 0.45))
PresetRegistry.register(Preset("Square (1080x1080)", 1080, 1080, LayoutMode.VERTICAL, 0.6))

def tokenize_python_line(line: str) -> List[Token]:
    tokens: List[Token] = []
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if c == "#": tokens.append(Token(line[i:], TokenType.COMMENT)); break
        if c in " \t":
            j = i
            while j < n and line[j] in " \t": j += 1
            tokens.append(Token(line[i:j], TokenType.WHITESPACE)); i = j; continue
        if c in "\"'":
            quote = c
            if i + 2 < n and line[i+1] == quote and line[i+2] == quote:
                j = i + 3
                while j < n:
                    if j + 2 < n and line[j] == quote and line[j+1] == quote and line[j+2] == quote:
                        j += 3; break
                    if line[j] == "\\": j += 1
                    j += 1
                tokens.append(Token(line[i:j], TokenType.STRING)); i = j; continue
            j = i + 1
            while j < n and line[j] != quote:
                if line[j] == "\\": j += 1
                j += 1
            tokens.append(Token(line[i:min(j+1, n)], TokenType.STRING)); i = j + 1; continue
        if c.isdigit() or (c == "-" and i + 1 < n and line[i + 1].isdigit()):
            j = i + 1 if c == "-" else i
            if c == "0" and j < n and j + 1 < n and line[j + 1] in "xXbBoO":
                j += 2
                while j < n and (line[j].isalnum()): j += 1
            else:
                while j < n and (line[j].isdigit() or line[j] == "."): j += 1
                if j < n and line[j] in "eE":
                    j += 1
                    if j < n and line[j] in "+-": j += 1
                    while j < n and line[j].isdigit(): j += 1
            tokens.append(Token(line[i:j], TokenType.NUMBER)); i = j; continue
        if c.isalpha() or c == "_":
            j = i
            while j < n and (line[j].isalnum() or line[j] == "_"): j += 1
            word = line[i:j]
            kind = TokenType.IDENTIFIER
            if word in KEYWORDS: kind = TokenType.KEYWORD
            elif word in SYNTH_SET: kind = TokenType.SYNTH
            elif word in FX_SET: kind = TokenType.FX
            elif word in SAMPLE_SET: kind = TokenType.SAMPLE
            tokens.append(Token(word, kind)); i = j; continue
        if c in "+-*/=<>!&|%^~":
            j = i
            while j < n and line[j] in "+-*/=<>!&|%^~": j += 1
            tokens.append(Token(line[i:j], TokenType.OPERATOR)); i = j; continue
        if c in "(){}[],.;:":
            tokens.append(Token(c, TokenType.PUNCTUATION)); i += 1; continue
        if c in "fF" and i + 1 < n and line[i + 1] in "\"'":
            j = i + 2
            quote = line[i + 1]
            while j < n and line[j] != quote:
                if line[j] == "\\": j += 1
                j += 1
            tokens.append(Token(line[i:min(j+1, n)], TokenType.STRING)); i = j + 1; continue
        if c == "@":
            tokens.append(Token(c, TokenType.OPERATOR)); i += 1; continue
        tokens.append(Token(c, TokenType.IDENTIFIER)); i += 1
    return tokens

TOKEN_COLOR_MAP: Dict[TokenType, str] = {
    TokenType.KEYWORD: "kw", TokenType.SYNTH: "kw", TokenType.FX: "kw", TokenType.SAMPLE: "kw",
    TokenType.NUMBER: "num", TokenType.STRING: "str", TokenType.COMMENT: "cmt",
    TokenType.OPERATOR: "sym", TokenType.PUNCTUATION: "sym", TokenType.IDENTIFIER: "txt", TokenType.WHITESPACE: "txt",
}

# ==========================================
# 2. AUDIO ENGINE & THREADING
# ==========================================

def _find_loopback_device() -> Optional[int]:
    try:
        import sounddevice as sd
        for i in range(len(sd.query_hostapis())):
            api = sd.query_hostapis(i)
            if api["name"] == "WASAPI":
                default_output = api["default_output_device"]
                if default_output is not None and default_output >= 0:
                    return default_output
    except Exception:
        pass
    return None

def save_wav(audio: np.ndarray, path: Path) -> None:
    import wave
    data = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(data.tobytes())

def precompute(code: str, audio: np.ndarray, audio_dur: float, cfg: AudioEngineConfig, progress_cb: Optional[Callable[[int, int, str], None]] = None, is_cancelled: Optional[Callable[[], bool]] = None) -> Tuple[List[FrameState], float]:
    nc = len(code); speed = cfg.typing_speed
    typing_dur = nc / speed if speed > 0 else audio_dur
    total = max(cfg.typing_delay + typing_dur + 3.0, audio_dur)
    nf = int(total * FPS) + 1; times = np.arange(nf) / FPS
    frames = []
    for i, t in enumerate(times):
        if is_cancelled and is_cancelled(): return [], 0.0
        v = FrameState()
        if t < cfg.typing_delay: v.char_index = 0; v.typing_progress = 0.0
        else:
            elapsed_typing = t - cfg.typing_delay
            v.char_index = max(0, min(int(elapsed_typing * speed), nc))
            v.typing_progress = v.char_index / nc if nc > 0 else 1.0
        v.time = float(t); v.code_done = v.char_index >= nc
        s = int(t * SR); e = min(s + 1024, len(audio))
        if e > s:
            seg = audio[s:e]
            v.waveform = np.interp(np.linspace(0, len(seg) - 1, 256), np.arange(len(seg)), seg).astype(np.float32)
            v.beat_power = min(float(np.sqrt(np.mean(seg ** 2))) * 5, 1.0); v.rms = v.beat_power / 5.0
            v.peak_l = v.beat_power * np.random.uniform(0.85, 1.0); v.peak_r = v.beat_power * np.random.uniform(0.85, 1.0)
            if v.beat_power > (1.0 - cfg.beat_sensitivity): v.beat_on = True; v.beat_strength = v.beat_power
            fft_seg = seg[:512] if len(seg) >= 512 else seg
            if len(fft_seg) > 0:
                fft_data = np.abs(np.fft.rfft(fft_seg))
                if len(fft_data) > 0:
                    v.spectrum = np.interp(np.linspace(0, len(fft_data) - 1, 64), np.arange(len(fft_data)), fft_data).astype(np.float32)
                    max_val = np.max(v.spectrum)
                    if max_val > 0: v.spectrum /= max_val
        frames.append(v)
        if progress_cb and i % 30 == 0: progress_cb(i, nf, "Analyzing audio & computing typing animation...")
    return frames, total

class FoxDotManager(QObject):
    status_changed = Signal(str, dict)

    def __init__(self):
        super().__init__()
        self._started: bool = False
        self._ns: dict = {}
        self._lock = threading.Lock()

    def _is_alive(self) -> bool:
        return self._started

    def _kill_stale_processes(self):
        try:
            import psutil
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    name = (proc.info["name"] or "").lower()
                    cmdline = " ".join(proc.info["cmdline"] or "").lower()
                    if "scsynth" in name or "supernova" in name:
                        proc.terminate()
                        try: proc.wait(timeout=3)
                        except psutil.TimeoutExpired: proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied): continue
            time.sleep(1.0)
        except ImportError: pass

    def launch(self) -> Tuple[bool, str]:
        with self._lock:
            if self._started: return True, "FoxDot already running"
            self._kill_stale_processes()
            try:
                logger.info("Importing FoxDot...")
                exec("from FoxDot import *", self._ns)
                
                logger.info("Booting SuperCollider server...")
                try: exec("Server.boot()", self._ns)
                except Exception as e: logger.warning(f"Server.boot() error: {e}")
                
                time.sleep(4.0)
                
                logger.info("Loading synth definitions...")
                try: exec("SynthDefs.load()", self._ns)
                except Exception as e: logger.warning(f"SynthDefs.load() error: {e}")
                
                time.sleep(1.0)
                
                logger.info("Starting clock...")
                try: exec("Clock.start()", self._ns)
                except Exception as e: logger.warning(f"Clock.start() error: {e}")
                
                self._started = True
                logger.info("FoxDot started successfully")
                return True, "FoxDot started successfully"
            except ImportError:
                msg = "FoxDot not found. Install with: pip install FoxDot"
                logger.error(msg)
                return False, msg
            except Exception as e:
                msg = f"Failed to start FoxDot: {e}\nMake sure SuperCollider is installed."
                logger.error(msg, exc_info=True)
                return False, msg

    def run_code(self, code: str) -> bool:
        with self._lock:
            if not self._started: return False
            try:
                exec(code, self._ns)
                return True
            except SyntaxError as e:
                logger.error(f"Syntax error in FoxDot code: {e}")
                return False
            except Exception as e:
                logger.error(f"FoxDot code execution error: {e}")
                return False

    def stop_all(self) -> bool:
        with self._lock:
            if not self._started: return False
            try: exec("Clock.clear()", self._ns)
            except Exception: pass
            try: exec("for _p in list(Player.players): _p.stop()", self._ns)
            except Exception: pass
            return True

    def kill(self) -> None:
        with self._lock:
            if not self._started: return
            try: exec("Clock.clear()", self._ns)
            except Exception: pass
            try: exec("Server.quit()", self._ns)
            except Exception: pass
            self._started = False

class CancelableWorker(QThread):
    progress = Signal(int, int, str); error = Signal(str); status = Signal(str)
    def __init__(self):
        super().__init__(); self._cancel = False; self._lock = threading.Lock()
    def cancel(self):
        with self._lock: self._cancel = True
    @property
    def is_cancelled(self):
        with self._lock: return self._cancel

class FoxDotBootWorker(CancelableWorker):
    finished = Signal(bool, str)
    def __init__(self, fd: FoxDotManager):
        super().__init__(); self.fd = fd
    def run(self):
        ok, msg = self.fd.launch()
        self.finished.emit(ok, msg)

class AudioPreviewWorker(CancelableWorker):
    finished = Signal(np.ndarray, float, str)
    def __init__(self, code: str, fd: FoxDotManager, base_dur: float):
        super().__init__()
        self.code = code; self.fd = fd; self.base_dur = base_dur

    def run(self):
        try:
            if not self.fd._is_alive():
                self.error.emit("FoxDot is not running. Please boot it first.")
                return

            self.progress.emit(5, 100, "Preparing recording...")
            audio = self._record_audio()
            self.progress.emit(95, 100, "Processing audio...")
            self.finished.emit(audio, len(audio) / SR, self.code)
        except Exception as e:
            logger.error(f"AudioPreviewWorker failed: {e}", exc_info=True)
            self.error.emit(str(e))

    def _record_audio(self) -> np.ndarray:
        import sounddevice as sd
        sr = SR
        total_dur = self.base_dur + 2.0
        total_samples = int(total_dur * sr)
        
        loopback_device = _find_loopback_device() if platform.system() == "Windows" else None
        recording = None
        
        if loopback_device is not None:
            try:
                self.progress.emit(10, 100, "Starting WASAPI loopback recording...")
                recording = sd.rec(
                    total_samples, samplerate=sr, channels=2, dtype="float32",
                    device=loopback_device, extra_settings=sd.WasapiSettings(loopback=True)
                )
            except Exception as e:
                logger.warning(f"WASAPI loopback recording failed: {e}")
                recording = None
                
        if recording is None:
            self.progress.emit(10, 100, "Starting default recording...")
            try:
                recording = sd.rec(total_samples, samplerate=sr, channels=2, dtype="float32")
            except Exception as e:
                raise RuntimeError(f"Could not start audio recording: {e}")
                
        time.sleep(0.3)
        
        self.progress.emit(15, 100, "Playing FoxDot code...")
        if not self.fd.run_code(self.code):
            sd.stop()
            raise RuntimeError("Failed to execute FoxDot code.")
            
        steps = int(self.base_dur * 2)
        for i in range(steps):
            if self.is_cancelled:
                self.fd.stop_all(); sd.stop()
                return np.zeros(total_samples, dtype=np.float32)
            time.sleep(0.5)
            self.progress.emit(15 + int(65 * (i / steps)), 100, "Recording audio...")
            
        self.progress.emit(82, 100, "Stopping playback...")
        self.fd.stop_all()
        time.sleep(1.5)
        sd.wait()
        
        if recording.ndim > 1 and recording.shape[1] > 1:
            audio = recording.mean(axis=1)
        else:
            audio = recording.flatten()
            
        if len(audio) > 0:
            peak = np.max(np.abs(audio))
            if peak > 0: audio = audio / peak * 0.85
            
        trim_samples = int(self.base_dur * sr) + int(1.0 * sr)
        if len(audio) > trim_samples:
            audio = audio[:trim_samples]
            
        return audio

class ExportWorker(CancelableWorker):
    finished = Signal(str, bool, str)
    def __init__(self, path: str, renderer: Any, code: str, audio: np.ndarray, cfg: AudioEngineConfig):
        super().__init__(); self.path = path; self.renderer = renderer; self.code = code; self.audio = audio; self.cfg = cfg
    def run(self):
        try:
            if not shutil.which("ffmpeg"): raise Exception("FFmpeg not found. Please install FFmpeg and ensure it's in your system PATH.")
            frames, td = precompute(self.code, self.audio, len(self.audio) / SR, self.cfg, lambda c, t, m: self.progress.emit(int(10 * c / t), 100, m), lambda: self.is_cancelled)
            self.renderer.set_data(self.code, frames, td)
            temp_wav = TMP_AUDIO_DIR / "export.wav"; temp_wav.parent.mkdir(exist_ok=True, parents=True)
            save_wav(self.audio, temp_wav)
            cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb32", "-s", f"{self.renderer.vw}x{self.renderer.vh}", "-r", str(self.cfg.export_fps), "-i", "-", "-i", str(temp_wav), "-c:v", self.cfg.export_codec, "-preset", self.cfg.export_preset, "-pix_fmt", "yuv420p", "-c:a", self.cfg.export_audio_codec, "-b:a", self.cfg.export_audio_bitrate, "-shortest", self.path]
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            from PySide6.QtGui import QImage
            img = QImage(self.renderer.vw, self.renderer.vh, QImage.Format.Format_RGB32)
            for i, frame in enumerate(frames):
                if self.is_cancelled: proc.kill(); self.finished.emit("", False, "Cancelled"); return
                self.renderer.render_to_image(img, i); proc.stdin.write(img.constBits().tobytes())
                self.progress.emit(10 + int(80 * (i / len(frames))), 100, f"Rendering {i}/{len(frames)}")
            proc.stdin.close(); proc.wait()
            if proc.returncode != 0:
                err_output = proc.stderr.read().decode('utf-8', errors='ignore')
                self.finished.emit("", False, f"FFmpeg encoding failed:\n{err_output[-500:]}")
            else: self.finished.emit(self.path, True, "Export complete")
        except Exception as e:
            logger.error(f"Export worker error: {e}", exc_info=True)
            self.finished.emit("", False, str(e))

# ==========================================
# 3. RENDERER
# ==========================================

class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "color_idx")
    def __init__(self, x, y, vx, vy, life, size, c_idx):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life, self.max_life, self.size, self.color_idx = life, life, size, c_idx

class ParticleSystem:
    def __init__(self, max_p=200): self.particles = []; self.max_p = max_p; self._rng = random.Random(42)
    def emit_burst(self, cx, cy, count, strength, colors=(0,1)):
        for _ in range(count):
            if len(self.particles) >= self.max_p: break
            a = self._rng.uniform(0, 2 * math.pi); s = self._rng.uniform(0.5, 3.0) * (0.5 + strength)
            self.particles.append(Particle(cx, cy, math.cos(a)*s, math.sin(a)*s, self._rng.uniform(0.3, 0.8), self._rng.uniform(2, 6), self._rng.choice(colors)))
    def update(self, dt):
        surv = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0: continue
            p.x += p.vx; p.y += p.vy; p.vy += 0.05; p.vx *= 0.98; surv.append(p)
        self.particles = surv
    def draw(self, p: QPainter, colors):
        p.setPen(Qt.PenStyle.NoPen)
        for prt in self.particles:
            a = prt.life / prt.max_life; c = colors[prt.color_idx % len(colors)]; r = prt.size * a
            if r < 0.5: continue
            grad = QRadialGradient(QPointF(prt.x, prt.y), r * 2)
            grad.setColorAt(0, QColor(c[0], c[1], c[2], int(200 * a))); grad.setColorAt(1, QColor(c[0], c[1], c[2], 0))
            p.setBrush(QBrush(grad)); p.drawEllipse(QPointF(prt.x, prt.y), r * 2, r * 2)

class FrameRenderer:
    def __init__(self):
        self.frames: List[FrameState] = []; self.cf: int = 0; self.code: str = ""
        self.vw: int = 1920; self.vh: int = 1080; self.theme: Theme = None; self.preset: Preset = None; self.cfg: AudioEngineConfig = None
        self.total_time: float = 0.0; self.particles = ParticleSystem(); self._token_cache: Dict[str, List[Token]] = {}

    def apply_config(self, cfg: AudioEngineConfig):
        self.cfg = cfg; self.theme = ThemeRegistry.get(cfg.theme_name); self.preset = PresetRegistry.get(cfg.preset_name)
        self.vw, self.vh = self.preset.width, self.preset.height; self.particles = ParticleSystem(cfg.particle_count)

    def clone(self) -> "FrameRenderer":
        r = FrameRenderer(); r.apply_config_from_renderer(self); return r

    def apply_config_from_renderer(self, src: "FrameRenderer"):
        self.cfg, self.vw, self.vh, self.theme, self.preset = src.cfg, src.vw, src.vh, src.theme, src.preset

    def set_data(self, code: str, frames: List[FrameState], total_time: float = 0.0):
        self.code = code; self.frames = frames; self.cf = 0; self.total_time = total_time; self._token_cache.clear()

    def draw_live(self, p: QPainter, w: int, h: int, fi: Optional[int] = None):
        if fi is not None: self.cf = min(fi, len(self.frames) - 1) if self.frames else 0
        self._draw(p, w, h)

    def render_to_image(self, img: QImage, fi: int):
        p = QPainter(img); p.setRenderHint(QPainter.RenderHint.Antialiasing, True); img.fill(self.theme.color("bg1"))
        if self.frames: self.cf = min(fi, len(self.frames) - 1); self._draw(p, img.width(), img.height())
        p.end()

    def _draw(self, p: QPainter, w: int, h: int):
        if not self.frames or not self.cfg: p.fillRect(0, 0, w, h, self.theme.color("bg1")); return
        v = self.frames[min(self.cf, len(self.frames) - 1)]
        grad = QLinearGradient(0, 0, w, h); grad.setColorAt(0, self.theme.color("bg1")); grad.setColorAt(1, self.theme.color("bg2"))
        p.fillRect(0, 0, w, h, grad)
        if self.cfg.particles_enabled:
            if v.beat_on: self.particles.emit_burst(w//2, h//2, self.cfg.particle_burst_on_beat, v.beat_strength, colors=(self.theme.w1, self.theme.w2))
            self.particles.update(1.0 / 30.0); self.particles.draw(p, [self.theme.w1, self.theme.w2, self.theme.accent])
        if self.cfg.beat_flash and v.beat_on: p.fillRect(0, 0, w, h, QColor(255, 255, 255, int(50 * v.beat_strength)))
        if self.preset.layout == LayoutMode.HORIZONTAL:
            cw = int(w * self.preset.split); code_rect, wave_rect = QRectF(0, 0, cw, h), QRectF(cw, 0, w - cw, h)
        else:
            ch = int(h * self.preset.split); code_rect, wave_rect = QRectF(0, 0, w, ch), QRectF(0, ch, w, h - ch)
        self._draw_code(p, code_rect, v); self._draw_wave(p, wave_rect, v)
        if self.cfg.show_progress_bar and self.total_time > 0:
            progress = v.time / self.total_time; p.fillRect(0, h - 5, int(w * progress), 5, self.theme.color("accent"))

    def _draw_code(self, p: QPainter, rect: QRectF, v: FrameState):
        x, y, pw, ph = int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())
        p.fillRect(x, y, pw, ph, QColor(self.theme.bg1[0]+5, self.theme.bg1[1]+5, self.theme.bg1[2]+5, 230))
        fnt_size = self.cfg.font_size_override if self.cfg.font_size_override > 0 else 14
        fnt = QFont(self.cfg.font_family, fnt_size); fnt.setStyleHint(QFont.StyleHint.Monospace); p.setFont(fnt)
        fm = QFontMetrics(fnt); lh = fm.height() + self.cfg.line_spacing
        vis = self.code[:v.char_index]
        if self.cfg.show_typing_cursor and not v.code_done:
            if int(v.time * self.cfg.cursor_blink_rate) % 2 == 0: vis += self.cfg.cursor_char
        lines = vis.split("\n")
        total_height = len(lines) * lh
        if total_height < ph - 40: start_y = y + (ph - total_height) // 2
        else: start_y = y + 20
        if self.cfg.show_line_numbers:
            ln_width = fm.horizontalAdvance("000") + 20; p.fillRect(x, y, ln_width, ph, QColor(0, 0, 0, 100))
        for i, line in enumerate(lines):
            ly = start_y + i * lh
            if ly > y + ph - lh: break
            tokens = self._token_cache.get(line) or (self._token_cache.setdefault(line, tokenize_python_line(line)))
            tx = x + self.cfg.code_padding
            if self.cfg.show_line_numbers:
                p.setPen(self.theme.color("cmt")); p.drawText(x + 10, ly + fm.ascent() + 2, str(i + 1)); tx = x + ln_width + 10
            if self.cfg.show_code_glow:
                p.setPen(QPen(self.theme.color("accent", 80)))
                for tok in tokens: p.drawText(tx + 1, ly + fm.ascent() + 3, tok.text); tx += fm.horizontalAdvance(tok.text)
                tx = x + self.cfg.code_padding
                if self.cfg.show_line_numbers: tx = x + ln_width + 10
            for tok in tokens:
                color_key = TOKEN_COLOR_MAP.get(tok.kind, "txt"); p.setPen(self.theme.color(color_key))
                p.drawText(tx, ly + fm.ascent() + 2, tok.text); tx += fm.horizontalAdvance(tok.text)

    def _draw_wave(self, p: QPainter, rect: QRectF, v: FrameState):
        vx, vy, vw, vh = int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())
        p.fillRect(vx, vy, vw, vh, QColor(self.theme.bg2[0]+2, self.theme.bg2[1]+2, self.theme.bg2[2]+2, 200))
        cy = vy + vh // 2
        if self.cfg.show_spectrum:
            bars = v.spectrum; n = len(bars)
            if n > 0:
                bw = vw / n
                for i, b in enumerate(bars): bh = b * (vh * 0.3); p.fillRect(vx + i * bw, vy + vh - bh, bw - 2, bh, self.theme.color("accent", 150))
        path = QPainterPath(); wf = v.waveform; n = len(wf)
        if n == 0: return
        for i in range(n):
            px = vx + (i / max(1, n - 1)) * vw; py = cy - wf[i] * (vh * 0.4) * self.cfg.wave_amplitude
            if i == 0: path.moveTo(px, py)
            else: path.lineTo(px, py)
        if self.cfg.mirror_waveform:
            mirror_path = QPainterPath()
            for i in range(n):
                px = vx + (i / max(1, n - 1)) * vw; py = cy + wf[i] * (vh * 0.4) * self.cfg.wave_amplitude
                if i == 0: mirror_path.moveTo(px, py)
                else: mirror_path.lineTo(px, py)
            p.setPen(QPen(self.theme.color("w2"), 2)); p.drawPath(mirror_path)
        if self.cfg.fill_waveform:
            fill_path = QPainterPath(path); fill_path.lineTo(vx + vw, cy); fill_path.lineTo(vx, cy)
            grad = QLinearGradient(vx, vy, vx, vy + vh); grad.setColorAt(0, self.theme.color("w1", 100)); grad.setColorAt(1, self.theme.color("w1", 0))
            p.fillPath(fill_path, QBrush(grad))
        p.setPen(QPen(self.theme.color("w1"), 2)); p.drawPath(path)
        if self.cfg.vu_meter:
            lh = v.peak_l * (vh * 0.45); p.fillRect(vx + 10, cy - lh, 6, lh * 2, self.theme.color("accent"))
            rh = v.peak_r * (vh * 0.45); p.fillRect(vx + vw - 16, cy - rh, 6, rh * 2, self.theme.color("accent"))

# ==========================================
# 4. GUI MAIN WINDOW
# ==========================================

class FoxDotHighlighter(QSyntaxHighlighter):
    def __init__(self, document, theme):
        super().__init__(document); self.theme = theme; self._build_formats()

    def _build_formats(self):
        self._fmts = {}
        for kind, key in TOKEN_COLOR_MAP.items():
            fmt = QTextCharFormat(); c = getattr(self.theme, key)
            fmt.setForeground(QColor(c[0], c[1], c[2]))
            if key == "kw": fmt.setFontWeight(QFont.Weight.Bold)
            self._fmts[kind] = fmt

    def set_theme(self, theme):
        self.theme = theme; self._build_formats(); self.rehighlight()

    def highlightBlock(self, text: str):
        idx = 0
        for tok in tokenize_python_line(text):
            fmt = self._fmts.get(tok.kind)
            if fmt: self.setFormat(idx, len(tok.text), fmt)
            idx += len(tok.text)

class AnimWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.renderer = FrameRenderer(); self.setMinimumSize(400, 250)
    def set_data(self, code: str, frames: List[FrameState], total_time: float = 0.0):
        self.renderer.set_data(code, frames, total_time); self.update()
    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.renderer.draw_live(p, self.width(), self.height(), self.renderer.cf); p.end()

class MainWindow(QMainWindow):
    DEFAULT_CODE = (
        "# FoxDot Animation Studio\n"
        "Clock.bpm = 120\n"
        "\n"
        "p1 >> pluck([0, 2, 4, 2], dur=[1, 1, 1, 1], sus=1)\n"
        "\n"
        "b1 >> bass([0, 0, 4, 5], dur=2)\n"
        "\n"
        "d1 >> play(\"x-o-\")\n"
    )

    def __init__(self, cfg: AudioEngineConfig, fd: FoxDotManager):
        super().__init__(); self.cfg = cfg; self.foxdot = fd
        self.setWindowTitle("FoxDot Animation Studio"); self.resize(1400, 800)
        self._playing = False; self._frame_idx = 0; self._frames = []; self._total_dur = 0.0
        self._current_code = ""; self._current_audio: Optional[np.ndarray] = None
        self._export_audio: Optional[np.ndarray] = None; self._current_audio_path = ""; self._is_exporting = False
        self._preview_worker: Optional[AudioPreviewWorker] = None
        self._export_worker: Optional[ExportWorker] = None
        self._boot_worker: Optional[FoxDotBootWorker] = None
        
        self.player = QMediaPlayer(); self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output); self.audio_output.setVolume(self.cfg.master_volume)
        self.player.positionChanged.connect(self._on_pos_changed); self.player.durationChanged.connect(self._on_dur_changed)
        self.timer = QTimer(); self.timer.setInterval(int(1000 / 30)); self.timer.timeout.connect(self._tick)
        
        self._check_dependencies()
        self._build_ui(); self._load_settings(); self._load_input_scripts()
        self.anim.renderer.apply_config(self.cfg); self.highlighter.set_theme(ThemeRegistry.get(self.cfg.theme_name))

    def _check_dependencies(self):
        missing = []
        try:
            import FoxDot
        except ImportError:
            missing.append("FoxDot (pip install FoxDot)")
        try:
            import sounddevice
        except ImportError:
            missing.append("sounddevice (pip install sounddevice)")
        if not shutil.which("ffmpeg"):
            missing.append("FFmpeg (must be installed and in system PATH)")
        
        if missing:
            QMessageBox.warning(self, "Missing Dependencies", 
                                "The following dependencies are missing:\n\n- " + 
                                "\n- ".join(missing) + 
                                "\n\nAudio generation/export may fail until these are installed.")

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central); root = QVBoxLayout(central)
        toolbar = QHBoxLayout()
        self.file_combo = QComboBox(); self.file_combo.addItem("— select script —")
        self.file_combo.currentIndexChanged.connect(self._load_script_file)
        toolbar.addWidget(QLabel("Script:")); toolbar.addWidget(self.file_combo, 1)
        self.browse_btn = QToolButton(); self.browse_btn.setText("📂 Browse"); self.browse_btn.clicked.connect(self._browse_scripts); toolbar.addWidget(self.browse_btn)
        self.theme_combo = QComboBox(); self.theme_combo.addItems(ThemeRegistry.names()); self.theme_combo.setCurrentText(self.cfg.theme_name)
        self.theme_combo.currentTextChanged.connect(self._change_theme); toolbar.addWidget(QLabel("Theme:")); toolbar.addWidget(self.theme_combo)
        self.settings_btn = QPushButton("⚙ Settings"); self.settings_btn.clicked.connect(self._toggle_settings); toolbar.addWidget(self.settings_btn)
        root.addLayout(toolbar)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.code_edit = QPlainTextEdit(); self.code_edit.setFont(QFont("Consolas", 11))
        self.code_edit.setPlainText(self.DEFAULT_CODE)
        self.highlighter = FoxDotHighlighter(self.code_edit.document(), ThemeRegistry.default()); splitter.addWidget(self.code_edit)
        self.anim = AnimWidget(); splitter.addWidget(self.anim); splitter.setSizes([450, 950]); root.addWidget(splitter, 1)
        
        audio_ctrl = QHBoxLayout()
        self.boot_btn = QPushButton("🚀 Boot FoxDot"); self.boot_btn.clicked.connect(self._boot_foxdot); audio_ctrl.addWidget(self.boot_btn)
        self.kill_btn = QPushButton("⏹ Stop Sounds"); self.kill_btn.clicked.connect(self._kill_sounds); audio_ctrl.addWidget(self.kill_btn)
        self.play_btn = QPushButton("▶ Play"); self.play_btn.clicked.connect(self._play); audio_ctrl.addWidget(self.play_btn)
        self.stop_btn = QPushButton("⬛ Stop"); self.stop_btn.clicked.connect(self._stop); audio_ctrl.addWidget(self.stop_btn)
        self.preview_btn = QPushButton("🎬 Generate Audio"); self.preview_btn.clicked.connect(self._generate_audio); audio_ctrl.addWidget(self.preview_btn)
        self.export_btn = QPushButton("📹 Export MP4"); self.export_btn.clicked.connect(self._export); audio_ctrl.addWidget(self.export_btn)
        
        self.audio_slider = QSlider(Qt.Orientation.Horizontal); self.audio_slider.setRange(0, 1000)
        self.audio_slider.sliderMoved.connect(self._seek_audio); audio_ctrl.addWidget(self.audio_slider, 1)
        self.time_label = QLabel("00:00 / 00:00"); audio_ctrl.addWidget(self.time_label)
        self.vol_slider = QSlider(Qt.Orientation.Horizontal); self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(int(self.cfg.master_volume * 100)); self.vol_slider.valueChanged.connect(self._change_vol)
        audio_ctrl.addWidget(QLabel("Vol:")); audio_ctrl.addWidget(self.vol_slider); root.addLayout(audio_ctrl)
        
        self.progress = QProgressBar(); self.progress.setVisible(False); root.addWidget(self.progress)
        self.status_bar = QStatusBar(); self.setStatusBar(self.status_bar)
        
        self.settings_dock = QDockWidget("Settings", self)
        self.settings_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        settings_widget = self._build_settings_widget(); self.settings_dock.setWidget(settings_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.settings_dock); self.settings_dock.hide()

    def _build_settings_widget(self):
        w = QWidget(); layout = QVBoxLayout(w); tabs = QTabWidget()
        general_tab = QWidget(); general_layout = QFormLayout(general_tab)
        self.preset_combo = QComboBox(); self.preset_combo.addItems(PresetRegistry.names()); self.preset_combo.setCurrentText(self.cfg.preset_name)
        self.preset_combo.currentTextChanged.connect(self._update_cfg); general_layout.addRow("Video Preset:", self.preset_combo)
        self.duration_spin = QDoubleSpinBox(); self.duration_spin.setRange(1.0, 120.0); self.duration_spin.setValue(self.cfg.base_duration)
        self.duration_spin.valueChanged.connect(self._update_cfg); general_layout.addRow("Base Duration (s):", self.duration_spin)
        self.vol_spin = QDoubleSpinBox(); self.vol_spin.setRange(0.0, 1.0); self.vol_spin.setSingleStep(0.05); self.vol_spin.setValue(self.cfg.master_volume)
        self.vol_spin.valueChanged.connect(self._update_cfg); general_layout.addRow("Master Volume:", self.vol_spin)
        info_label = QLabel("ℹ Requires FoxDot + SuperCollider installed.\nAudio is captured via system loopback (WASAPI on Windows).")
        info_label.setWordWrap(True); general_layout.addRow(info_label)
        tabs.addTab(general_tab, "General")
        
        typing_tab = QWidget(); typing_layout = QFormLayout(typing_tab)
        self.ts_spin = QDoubleSpinBox(); self.ts_spin.setRange(1.0, 100.0); self.ts_spin.setValue(self.cfg.typing_speed)
        self.ts_spin.valueChanged.connect(self._update_cfg); typing_layout.addRow("Typing Speed (chars/s):", self.ts_spin)
        self.delay_spin = QDoubleSpinBox(); self.delay_spin.setRange(0.0, 10.0); self.delay_spin.setSingleStep(0.1); self.delay_spin.setValue(self.cfg.typing_delay)
        self.delay_spin.valueChanged.connect(self._update_cfg); typing_layout.addRow("Start Delay (s):", self.delay_spin)
        self.cursor_blink_spin = QDoubleSpinBox(); self.cursor_blink_spin.setRange(0.5, 10.0); self.cursor_blink_spin.setValue(self.cfg.cursor_blink_rate)
        self.cursor_blink_spin.valueChanged.connect(self._update_cfg); typing_layout.addRow("Cursor Blink Rate:", self.cursor_blink_spin)
        self.cursor_char_edit = QLineEdit(self.cfg.cursor_char); self.cursor_char_edit.textChanged.connect(self._update_cfg); typing_layout.addRow("Cursor Character:", self.cursor_char_edit)
        self.cb_show_cursor = QCheckBox("Show Typing Cursor"); self.cb_show_cursor.setChecked(self.cfg.show_typing_cursor)
        self.cb_show_cursor.toggled.connect(self._update_cfg); typing_layout.addRow(self.cb_show_cursor); tabs.addTab(typing_tab, "Typing")
        
        visual_tab = QWidget(); visual_layout = QVBoxLayout(visual_tab)
        effects_group = QGroupBox("Effects"); effects_layout = QVBoxLayout(effects_group)
        for attr, text in [("particles_enabled", "Particles Enabled"), ("mirror_waveform", "Mirror Waveform"), ("fill_waveform", "Fill Waveform"), ("vu_meter", "VU Meter"), ("show_spectrum", "Show Spectrum"), ("show_code_glow", "Code Glow"), ("beat_flash", "Beat Flash"), ("show_progress_bar", "Progress Bar"), ("show_line_numbers", "Line Numbers")]:
            cb = QCheckBox(text); cb.setChecked(getattr(self.cfg, attr))
            cb.toggled.connect(lambda checked, a=attr: self._update_cfg_attr(a, checked)); effects_layout.addWidget(cb)
        visual_layout.addWidget(effects_group)
        wave_group = QGroupBox("Waveform"); wave_layout = QFormLayout(wave_group)
        self.wave_amp_spin = QDoubleSpinBox(); self.wave_amp_spin.setRange(0.1, 1.0); self.wave_amp_spin.setSingleStep(0.05); self.wave_amp_spin.setValue(self.cfg.wave_amplitude)
        self.wave_amp_spin.valueChanged.connect(self._update_cfg); wave_layout.addRow("Amplitude:", self.wave_amp_spin); visual_layout.addWidget(wave_group)
        part_group = QGroupBox("Particles"); part_layout = QFormLayout(part_group)
        self.particle_count_spin = QSpinBox(); self.particle_count_spin.setRange(10, 500); self.particle_count_spin.setValue(self.cfg.particle_count)
        self.particle_count_spin.valueChanged.connect(self._update_cfg); part_layout.addRow("Max Particles:", self.particle_count_spin)
        self.burst_count_spin = QSpinBox(); self.burst_count_spin.setRange(1, 50); self.burst_count_spin.setValue(self.cfg.particle_burst_on_beat)
        self.burst_count_spin.valueChanged.connect(self._update_cfg); part_layout.addRow("Burst Count:", self.burst_count_spin); visual_layout.addWidget(part_group)
        beat_group = QGroupBox("Beat Detection"); beat_layout = QFormLayout(beat_group)
        self.beat_sens_spin = QDoubleSpinBox(); self.beat_sens_spin.setRange(0.1, 1.0); self.beat_sens_spin.setSingleStep(0.05); self.beat_sens_spin.setValue(self.cfg.beat_sensitivity)
        self.beat_sens_spin.valueChanged.connect(self._update_cfg); beat_layout.addRow("Sensitivity:", self.beat_sens_spin); visual_layout.addWidget(beat_group); visual_layout.addStretch(1); tabs.addTab(visual_tab, "Visual")
        
        code_tab = QWidget(); code_layout = QFormLayout(code_tab)
        self.font_edit = QLineEdit(self.cfg.font_family); self.font_edit.textChanged.connect(self._update_cfg); code_layout.addRow("Font Family:", self.font_edit)
        self.font_size_spin = QSpinBox(); self.font_size_spin.setRange(0, 72); self.font_size_spin.setValue(self.cfg.font_size_override)
        self.font_size_spin.valueChanged.connect(self._update_cfg); code_layout.addRow("Font Size (0=auto):", self.font_size_spin)
        self.padding_spin = QSpinBox(); self.padding_spin.setRange(0, 100); self.padding_spin.setValue(self.cfg.code_padding)
        self.padding_spin.valueChanged.connect(self._update_cfg); code_layout.addRow("Code Padding:", self.padding_spin)
        self.line_spacing_spin = QSpinBox(); self.line_spacing_spin.setRange(0, 20); self.line_spacing_spin.setValue(self.cfg.line_spacing)
        self.line_spacing_spin.valueChanged.connect(self._update_cfg); code_layout.addRow("Line Spacing:", self.line_spacing_spin); tabs.addTab(code_tab, "Code")
        
        export_tab = QWidget(); export_layout = QFormLayout(export_tab)
        self.fps_spin = QSpinBox(); self.fps_spin.setRange(10, 60); self.fps_spin.setValue(self.cfg.export_fps)
        self.fps_spin.valueChanged.connect(self._update_cfg); export_layout.addRow("Export FPS:", self.fps_spin)
        self.codec_edit = QLineEdit(self.cfg.export_codec); self.codec_edit.textChanged.connect(self._update_cfg); export_layout.addRow("Video Codec:", self.codec_edit)
        self.preset_edit = QLineEdit(self.cfg.export_preset); self.preset_edit.textChanged.connect(self._update_cfg); export_layout.addRow("Encoding Preset:", self.preset_edit)
        self.audio_codec_edit = QLineEdit(self.cfg.export_audio_codec); self.audio_codec_edit.textChanged.connect(self._update_cfg); export_layout.addRow("Audio Codec:", self.audio_codec_edit)
        self.audio_bitrate_edit = QLineEdit(self.cfg.export_audio_bitrate); self.audio_bitrate_edit.textChanged.connect(self._update_cfg); export_layout.addRow("Audio Bitrate:", self.audio_bitrate_edit); tabs.addTab(export_tab, "Export")
        
        layout.addWidget(tabs); layout.addStretch(1); return w

    def _update_cfg_attr(self, attr, value):
        setattr(self.cfg, attr, value); self.anim.renderer.apply_config(self.cfg); self.anim.update(); self._save_settings()

    def _update_cfg(self):
        self.cfg.preset_name = self.preset_combo.currentText(); self.cfg.base_duration = self.duration_spin.value(); self.cfg.master_volume = self.vol_spin.value()
        self.cfg.typing_speed = self.ts_spin.value(); self.cfg.typing_delay = self.delay_spin.value()
        self.cfg.cursor_blink_rate = self.cursor_blink_spin.value(); self.cfg.cursor_char = self.cursor_char_edit.text()
        self.cfg.show_typing_cursor = self.cb_show_cursor.isChecked(); self.cfg.wave_amplitude = self.wave_amp_spin.value()
        self.cfg.particle_count = self.particle_count_spin.value(); self.cfg.particle_burst_on_beat = self.burst_count_spin.value()
        self.cfg.beat_sensitivity = self.beat_sens_spin.value(); self.cfg.font_family = self.font_edit.text()
        self.cfg.font_size_override = self.font_size_spin.value(); self.cfg.code_padding = self.padding_spin.value()
        self.cfg.line_spacing = self.line_spacing_spin.value(); self.cfg.export_fps = self.fps_spin.value()
        self.cfg.export_codec = self.codec_edit.text(); self.cfg.export_preset = self.preset_edit.text()
        self.cfg.export_audio_codec = self.audio_codec_edit.text(); self.cfg.export_audio_bitrate = self.audio_bitrate_edit.text()
        self.audio_output.setVolume(self.cfg.master_volume); self.anim.renderer.apply_config(self.cfg); self.anim.update(); self._save_settings()

    def _toggle_settings(self): self.settings_dock.setVisible(not self.settings_dock.isVisible())
    def _change_theme(self, name):
        self.cfg.theme_name = name; self.highlighter.set_theme(ThemeRegistry.get(name))
        self.anim.renderer.apply_config(self.cfg); self.anim.update(); self._save_settings()
    def _change_vol(self, v):
        self.cfg.master_volume = v / 100.0; self.audio_output.setVolume(self.cfg.master_volume); self._save_settings()
    def _seek_audio(self, v):
        if self.player.duration() > 0: self.player.setPosition(int(v / 1000 * self.player.duration()))
    def _load_input_scripts(self):
        self.file_combo.clear(); self.file_combo.addItem("— select script —")
        if INPUT_DIR.exists():
            for f in sorted(INPUT_DIR.glob("*.py")): self.file_combo.addItem(str(f))
    def _browse_scripts(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open FoxDot script", "", "Python (*.py);;All files (*)")
        if path:
            try:
                INPUT_DIR.mkdir(parents=True, exist_ok=True); dest_path = INPUT_DIR / Path(path).name; shutil.copy2(path, dest_path)
                self._load_input_scripts(); self.file_combo.setCurrentText(str(dest_path))
            except Exception as e:
                logger.error(f"Failed to copy script: {e}"); QMessageBox.warning(self, "File Error", f"Could not copy file to input folder:\n{e}")
    def _load_script_file(self, idx):
        if idx > 0:
            path = self.file_combo.itemText(idx)
            if Path(path).exists(): self.code_edit.setPlainText(Path(path).read_text())

    def _boot_foxdot(self):
        if self.foxdot._is_alive():
            QMessageBox.information(self, "FoxDot", "FoxDot is already running.")
            return
        self.status_bar.showMessage("Booting FoxDot in background...")
        self.progress.setVisible(True); self.progress.setRange(0, 0) # Indeterminate
        self._boot_worker = FoxDotBootWorker(self.foxdot)
        self._boot_worker.finished.connect(self._on_foxdot_booted)
        self._boot_worker.start()

    def _on_foxdot_booted(self, ok: bool, msg: str):
        self.progress.setVisible(False); self.progress.setRange(0, 100)
        if ok:
            self.status_bar.showMessage("FoxDot booted successfully.", 5000)
            self.boot_btn.setText("✓ FoxDot Running"); self.boot_btn.setEnabled(False)
        else:
            self.status_bar.showMessage("FoxDot boot failed.", 5000)
            QMessageBox.critical(self, "FoxDot Boot Error", msg)

    def _kill_sounds(self):
        if self.foxdot._is_alive():
            self.foxdot.stop_all()
            self.status_bar.showMessage("Stopped all FoxDot sounds.", 3000)

    def _generate_audio(self):
        if not self.foxdot._is_alive():
            QMessageBox.warning(self, "FoxDot Not Running", "Please boot FoxDot first using the 'Boot FoxDot' button.")
            return
        self._current_code = self.code_edit.toPlainText()
        self.status_bar.showMessage("Generating audio..."); self.progress.setVisible(True); self.progress.setValue(0)
        self._preview_worker = AudioPreviewWorker(self._current_code, self.foxdot, self.cfg.base_duration)
        self._preview_worker.progress.connect(lambda c,t,m: (self.progress.setValue(c), self.status_bar.showMessage(m)))
        self._preview_worker.finished.connect(self._on_audio_ready); self._preview_worker.error.connect(self._on_error); self._preview_worker.start()

    def _on_audio_ready(self, audio: np.ndarray, duration: float, code: str):
        self.progress.setVisible(False); self._export_audio = audio
        self._current_audio = audio[:int(self.cfg.base_duration * SR)].copy() 
        wav_path = TMP_AUDIO_DIR / "preview.wav"; wav_path.parent.mkdir(exist_ok=True, parents=True)
        save_wav(self._current_audio, wav_path); self._current_audio_path = str(wav_path)
        self.player.setSource(QUrl.fromLocalFile(str(wav_path))); self.player.setLoops(QMediaPlayer.Loops.Infinite)
        self._frames, self._total_dur = precompute(self._current_code, self._current_audio, duration, self.cfg)
        self.anim.set_data(self._current_code, self._frames, self._total_dur); self.status_bar.showMessage("Audio ready. Press Play."); self._play()

    def _on_pos_changed(self, pos):
        if self.player.duration() > 0: self.audio_slider.setValue(int(pos / self.player.duration() * 1000))
        cur = QTime(0, 0).addMSecs(pos); total = QTime(0, 0).addMSecs(self.player.duration())
        self.time_label.setText(f"{cur.toString('mm:ss')} / {total.toString('mm:ss')}")
    def _on_dur_changed(self, dur):
        total = QTime(0, 0).addMSecs(dur); self.time_label.setText(f"00:00 / {total.toString('mm:ss')}")
    def _play(self):
        if not self._frames: return
        if self._playing: self.timer.stop(); self._playing = False; self.play_btn.setText("▶ Play"); self.player.pause()
        else: self.timer.start(); self._playing = True; self.play_btn.setText("⏸ Pause"); self.player.play()
    def _stop(self):
        self.timer.stop(); self._playing = False; self._frame_idx = 0; self.play_btn.setText("▶ Play"); self.player.stop()
    def _tick(self):
        if not self._frames: self.timer.stop(); return
        self.anim.renderer.cf = self._frame_idx; self.anim.update(); self._frame_idx = (self._frame_idx + 1) % len(self._frames)
    def _export(self):
        if self._export_audio is None: QMessageBox.warning(self, "Error", "Generate audio first."); return
        path, _ = QFileDialog.getSaveFileName(self, "Export MP4", "output.mp4", "MP4 (*.mp4)")
        if not path: return
        self._is_exporting = True; self.progress.setVisible(True); self.progress.setValue(0)
        renderer = self.anim.renderer.clone()
        self._export_worker = ExportWorker(path, renderer, self._current_code, self._export_audio, self.cfg)
        self._export_worker.progress.connect(lambda c,t,m: self.progress.setValue(c))
        self._export_worker.finished.connect(self._on_export_done); self._export_worker.start()
    def _on_export_done(self, path: str, success: bool, msg: str):
        self._is_exporting = False; self.progress.setVisible(False)
        if success: QMessageBox.information(self, "Success", f"Saved to {path}")
        else: QMessageBox.critical(self, "Error", msg)
    def _on_error(self, msg: str):
        self.progress.setVisible(False); QMessageBox.critical(self, "Error", msg)
    def _load_settings(self):
        if SETTINGS_PATH.exists():
            try:
                data = json.loads(SETTINGS_PATH.read_text()); self.cfg = AudioEngineConfig.from_dict(data)
                self.theme_combo.setCurrentText(self.cfg.theme_name); self.vol_slider.setValue(int(self.cfg.master_volume * 100))
            except Exception as e: logger.error(f"Failed to load settings: {e}")
    def _save_settings(self):
        try: SETTINGS_DIR.mkdir(parents=True, exist_ok=True); SETTINGS_PATH.write_text(json.dumps(self.cfg.to_dict(), indent=2))
        except Exception as e: logger.error(f"Failed to save settings: {e}")
    def closeEvent(self, event):
        self._save_settings()
        if self.foxdot and self.foxdot._is_alive():
            self.foxdot.kill()
        super().closeEvent(event)

# ==========================================
# 5. ENTRY POINT
# ==========================================

def main():
    app = QApplication(sys.argv); app.setStyle("Fusion")
    cfg = AudioEngineConfig(); fd = FoxDotManager()
    win = MainWindow(cfg, fd); win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()