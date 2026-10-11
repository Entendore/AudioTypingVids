import os
from pathlib import Path

PROJECT_FILES = {
    "requirements.txt": r'''PySide6>=6.5.0
python-osc>=1.8.0
numpy>=1.24.0
scipy>=1.10.0
sounddevice>=0.4.6
watchdog>=3.0.0
psutil>=5.9.0
Pillow>=10.0.0
''',
    "core.py": r'''from __future__ import annotations
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union
import numpy as np
from PySide6.QtCore import QObject, Signal, QMutex, QMutexLocker
from PySide6.QtGui import QColor

SR: int = 44100
FPS: int = 30
PREVIEW_DURATION: float = 10.0

class TokenType(Enum):
    KEYWORD = auto(); SYNTH = auto(); FX = auto(); SAMPLE = auto()
    SYMBOL = auto(); NUMBER = auto(); STRING = auto(); COMMENT = auto()
    OPERATOR = auto(); PUNCTUATION = auto(); IDENTIFIER = auto(); WHITESPACE = auto()

class LayoutMode(Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"

class TypingMode(Enum):
    CONSTANT = "constant"
    MATCH_MUSIC = "match_music"
    BEAT_SYNC = "beat_sync"

@dataclass(frozen=True, slots=True)
class Token:
    text: str
    kind: TokenType

@dataclass(frozen=True, slots=True)
class Beat:
    position: int
    strength: float

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
    str: Tuple[int, int, int]; particle: Tuple[int, int, int]

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
    normalize_audio: bool = True
    beat_sensitivity: float = 0.5
    typing_speed: float = 28.0
    typing_mode: str = "match_music"
    cursor_blink_rate: float = 2.0
    cursor_char: str = "▋"
    typing_delay: float = 0.5
    wave_amplitude: float = 0.42
    particles_enabled: bool = True
    line_highlight: bool = True
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

KEYWORDS = frozenset({'use_bpm', 'use_synth', 'live_loop', 'with_fx', 'play', 'sample', 'sleep', 'do', 'end', 'chord', 'scale', 'release', 'amp', 'attack', 'decay', 'sustain', 'cutoff', 'pan', 'if', 'else', 'elsif', 'unless', 'while', 'until', 'def', 'return', 'true', 'false', 'nil', 'in_thread', 'at', 'with_tempo', 'tick', 'look', 'set', 'get', 'use_random_seed', 'shuffle'})
SYNTH_SET = frozenset({'prophet', 'pluck', 'tb303', 'dsaw', 'fm', 'piano', 'blade', 'saw', 'sine', 'square', 'noise', 'dark_ambience', 'hollow', 'kalimba', 'pretty_bell', 'ring_mod', 'sine_pb', 'subpulse'})
FX_SET = frozenset({'reverb', 'echo', 'flanger', 'distortion', 'compressor', 'lpf', 'hpf', 'wobble', 'phaser', 'chorus', 'panner', 'slicer', 'krush', 'octaver'})
SAMPLE_SET = frozenset({'bd_haus', 'drum_cymbal_closed', 'drum_heavy_kick', 'drum_snare_soft', 'elec_hi_snare', 'elec_lo_snare', 'perc_snap', 'perc_bell', 'tabla_tas1', 'tabla_tas2', 'tabla_tas3', 'tabla_ke1', 'tabla_na_s', 'tabla_na_o', 'guit_harmonic', 'guit_em9', 'bass_hit_c', 'bass_hard_c'})

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

ThemeRegistry.register(Theme("Midnight Blue", (15,15,28), (10,10,20), (0,255,180), (140,110,255), (0,200,255), (198,120,221), (219,191,130), (209,154,102), (98,114,164), (171,178,191), (152,195,121), (0,255,180)))
ThemeRegistry.register(Theme("Dracula", (40,42,54), (30,31,40), (255,121,198), (189,147,249), (255,184,108), (255,121,198), (241,250,140), (139,233,253), (98,114,164), (248,248,242), (241,250,140), (255,121,198)))
ThemeRegistry.register(Theme("Solarized Dark", (0,43,54), (7,54,66), (133,153,0), (38,139,210), (42,161,152), (203,75,22), (181,137,0), (220,50,47), (88,110,117), (253,246,227), (42,161,152), (133,153,0)))
ThemeRegistry.register(Theme("Monokai", (39,40,34), (27,28,22), (249,38,114), (174,129,255), (102,217,239), (249,38,114), (230,219,116), (174,129,255), (117,113,94), (248,248,242), (230,219,116), (249,38,114)))
ThemeRegistry.register(Theme("Gruvbox", (40,40,40), (29,32,33), (250,189,47), (214,93,14), (152,151,26), (204,36,29), (250,189,47), (215,153,33), (146,131,116), (235,219,178), (163,190,140), (214,93,14)))

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

def tokenize_ruby_line(line: str) -> List[Token]:
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
            j = i + 1
            while j < n and line[j] != c:
                if line[j] == "\\": j += 1
                j += 1
            tokens.append(Token(line[i:min(j+1,n)], TokenType.STRING)); i = j+1; continue
        if c.isdigit() or (c == "-" and i + 1 < n and line[i + 1].isdigit()):
            j = i + 1 if c == "-" else i
            while j < n and (line[j].isdigit() or line[j] == "."): j += 1
            tokens.append(Token(line[i:j], TokenType.NUMBER)); i = j; continue
        if c.isalpha() or c == "_":
            j = i
            while j < n and (line[j].isalnum() or line[j] in "_!?"): j += 1
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
        tokens.append(Token(c, TokenType.IDENTIFIER)); i += 1
    return tokens

TOKEN_COLOR_MAP: Dict[TokenType, str] = {
    TokenType.KEYWORD: "kw", TokenType.SYNTH: "kw", TokenType.FX: "kw", TokenType.SAMPLE: "kw",
    TokenType.SYMBOL: "sym", TokenType.NUMBER: "num", TokenType.STRING: "str", TokenType.COMMENT: "cmt",
    TokenType.OPERATOR: "sym", TokenType.PUNCTUATION: "sym", TokenType.IDENTIFIER: "txt", TokenType.WHITESPACE: "txt",
}
''',
    "audio_engine.py": r'''from __future__ import annotations
import os, re, socket, subprocess, time, threading, platform, shutil, struct
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple, Union
import numpy as np
from PySide6.QtCore import QThread, Signal, QObject
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from core import SR, FPS, FrameState, AudioEngineConfig, TypingMode

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[int, int, str], None]
CancelCheck = Callable[[], bool]

APP_ROOT = Path(__file__).resolve().parent
TMP_AUDIO_DIR = APP_ROOT / ".tmp_audio"

class OSCManager:
    def __init__(self):
        self.send_port: Optional[int] = None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind(("127.0.0.1", 4557))
            logger.info("OSC Manager bound to GUI port 4557")
        except OSError as e:
            logger.warning(f"Could not bind to 4557: {e}. Binding to ephemeral port.")
            self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.5)
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def _listen_loop(self):
        while True:
            try: self.sock.recvfrom(8192)
            except socket.timeout: continue
            except OSError: break

    @staticmethod
    def _pad(data: Union[str, bytes]) -> bytes:
        if isinstance(data, str): data = data.encode("utf-8")
        return data + b"\x00" * ((4 - (len(data) % 4)) % 4)

    def send(self, address: str, *args: Any) -> bool:
        if not self.send_port: return False
        try:
            msg = self._pad(address)
            type_tags, payload = ",", b""
            for arg in args:
                if isinstance(arg, bool): type_tags += "T" if arg else "F"
                elif isinstance(arg, str): type_tags += "s"; payload += self._pad(arg)
                elif isinstance(arg, int): type_tags += "i"; payload += struct.pack(">i", arg)
                elif isinstance(arg, float): type_tags += "f"; payload += struct.pack(">f", arg)
            msg += self._pad(type_tags) + payload
            self.sock.sendto(msg, ("127.0.0.1", self.send_port))
            return True
        except Exception as e:
            logger.error(f"OSC send failed to {address}: {e}")
            return False

class SonicPiManager(QObject):
    status_changed = Signal(str, dict)

    def __init__(self):
        super().__init__()
        self.process: Optional[subprocess.Popen] = None
        self.token: Optional[int] = None
        self.daemon_port: Optional[int] = None
        self._scsynth_ready = False
        self.osc = OSCManager()
        self._find_executable()

    def _find_executable(self) -> None:
        sys_os = platform.system()
        if sys_os == "Windows": base = r"C:\Program Files\Sonic Pi\app\server"
        elif sys_os == "Darwin": base = "/Applications/Sonic Pi.app/server"
        else: base = "/opt/sonic-pi/app/server"
        self.base_dir = base
        self.executable_path = os.path.join(base, "native", "ruby", "bin", "ruby")
        self._daemon_path = os.path.join(base, "ruby", "bin", "daemon.rb")

    def _is_alive(self) -> bool: return self.process is not None and self.process.poll() is None

    def _kill_stale_processes(self):
        try:
            import psutil
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    name = (proc.info["name"] or "").lower()
                    cmdline = " ".join(proc.info["cmdline"] or "").lower()
                    if "scsynth" in name or "daemon.rb" in cmdline:
                        proc.terminate()
                        try: proc.wait(timeout=3)
                        except psutil.TimeoutExpired: proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied): continue
            time.sleep(1.0)
        except ImportError: pass

    def launch(self) -> Tuple[bool, str]:
        self._kill_stale_processes()
        self.token = None; self.daemon_port = None; self._scsynth_ready = False
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0
        cmd = [self.executable_path, self._daemon_path, "--no-scsynth-inputs"]
        env = os.environ.copy(); env["SONIC_PI_SERVER_ROOT"] = self.base_dir
        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, cwd=self.base_dir, env=env, creationflags=creationflags)
        threading.Thread(target=self._read_loop, daemon=True).start()
        start_time = time.time()
        while time.time() - start_time < 45.0:
            if self.process.poll() is not None: return False, "Daemon crashed during boot."
            if self.token and self.daemon_port:
                time.sleep(2.0); return True, "Boot successful"
            time.sleep(0.2)
        return False, "Token timeout."

    def _read_loop(self):
        token_re = re.compile(r'\b(\d{6,})\b'); port_re = re.compile(r'\b(\d{4,5})\b')
        while self.process and self.process.poll() is None:
            line = self.process.stdout.readline()
            if not line: continue
            line = line.strip()
            if not line: continue
            if not (self.token and self.daemon_port):
                tok_match = token_re.search(line)
                if tok_match and not self.token: self.token = int(tok_match.group(1))
                port_match = port_re.search(line)
                if port_match and not self.daemon_port:
                    self.daemon_port = int(port_match.group(1)); self.osc.send_port = self.daemon_port
            if "SuperCollider 3" in line or "scsynth ready" in line.lower(): self._scsynth_ready = True

    def run_code(self, code: str) -> bool:
        if not self.token or not self._is_alive(): return False
        return self.osc.send("/run-code", self.token, code)

    def stop_all(self) -> bool:
        if not self.token or not self._is_alive(): return False
        return self.osc.send("/stop-all-jobs", self.token)

    def start_recording(self) -> bool:
        if not self.token or not self._is_alive(): return False
        return self.osc.send("/start-recording", self.token)

    def stop_recording(self) -> bool:
        if not self.token or not self._is_alive(): return False
        return self.osc.send("/stop-recording", self.token)

    def save_recording(self, fp: str) -> bool:
        if not self.token or not self._is_alive(): return False
        abs_fp = str(Path(fp).resolve()).replace("\\", "/")
        return self.osc.send("/save-recording", self.token, abs_fp)

class WavReadyHandler(FileSystemEventHandler):
    def __init__(self, target_filename: str):
        self.target_filename = target_filename
        self.file_ready = threading.Event()
    def on_created(self, event):
        if not event.is_directory and Path(event.src_path).name == self.target_filename: self.file_ready.set()
    def on_moved(self, event):
        if not event.is_directory and Path(event.dest_path).name == self.target_filename: self.file_ready.set()

def load_wav(path: Path, normalize: bool = True) -> np.ndarray:
    import wave
    with wave.open(str(path), "r") as w:
        n_channels = w.getnchannels(); sampwidth = w.getsampwidth(); frames = w.readframes(w.getnframes())
        if sampwidth == 2: audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        elif sampwidth == 4:
            try: audio = np.frombuffer(frames, dtype=np.float32)
            except ValueError: audio = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
        elif sampwidth == 3:
            audio = np.frombuffer(frames, dtype=np.uint8).astype(np.float32).reshape(-1, 3)
            audio = (audio[:, 0] | (audio[:, 1] << 8) | (audio[:, 2] << 16))
            audio = np.where(audio & 0x800000, audio - 0x1000000, audio).astype(np.float32) / 8388608.0
        else: raise ValueError(f"Unsupported sample width: {sampwidth}")
        if n_channels == 2: audio = audio.reshape(-1, 2).mean(axis=1)
    if normalize and len(audio) > 0:
        peak = np.max(np.abs(audio))
        if peak > 0: audio = audio / peak * 0.85
    return audio

def save_wav(audio: np.ndarray, path: Path) -> None:
    import wave
    data = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(data.tobytes())

def precompute(code: str, audio: np.ndarray, audio_dur: float, cfg: AudioEngineConfig, progress_cb: Optional[ProgressCallback] = None, is_cancelled: Optional[CancelCheck] = None) -> Tuple[List[FrameState], float]:
    nc = len(code); speed = cfg.typing_speed
    if cfg.typing_mode == "match_music":
        if nc > 0:
            avail = audio_dur - cfg.typing_delay - 3.0
            if avail > 0.2: speed = nc / avail
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
            if cfg.typing_mode == "beat_sync":
                beat_boost = 1.0; s_idx = int(t * SR); e_idx = min(s_idx + 1024, len(audio))
                if e_idx > s_idx:
                    seg = audio[s_idx:e_idx]; power = float(np.sqrt(np.mean(seg ** 2)))
                    if power > cfg.beat_sensitivity: beat_boost = 1.5
                v.char_index = max(0, min(int(elapsed_typing * speed * beat_boost), nc))
            else: v.char_index = max(0, min(int(elapsed_typing * speed), nc))
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

class CancelableWorker(QThread):
    progress = Signal(int, int, str); error = Signal(str); status = Signal(str)
    def __init__(self):
        super().__init__(); self._cancel = False; self._lock = threading.Lock()
    def cancel(self):
        with self._lock: self._cancel = True
    @property
    def is_cancelled(self):
        with self._lock: return self._cancel

class AudioPreviewWorker(CancelableWorker):
    finished = Signal(np.ndarray, float, str)
    def __init__(self, code: str, sp: SonicPiManager, base_dur: float):
        super().__init__(); self.code = code; self.sp = sp; self.base_dur = base_dur
    def _kill_daemon(self):
        if self.sp.process:
            try: self.sp.process.terminate(); self.sp.process.wait(timeout=5)
            except Exception:
                try: self.sp.process.kill()
                except: pass
            self.sp.process = None; self.sp.token = None; self.sp.daemon_port = None
    def run(self):
        tries = 0
        while tries < 2:
            tries += 1
            try:
                if not self.sp.process or self.sp.process.poll() is not None:
                    ok, msg = self.sp.launch()
                    if not ok:
                        if tries < 2: continue
                        self.error.emit(msg); return
                self.progress.emit(10, 100, "Recording...")
                if not self.sp.start_recording(): raise RuntimeError("start-recording failed")
                time.sleep(0.3)
                if not self.sp.run_code(self.code): raise RuntimeError("run-code failed")
                adur = self.base_dur
                for i in range(int(adur * 2)):
                    if self.is_cancelled: self.sp.stop_all(); return
                    time.sleep(0.5); self.progress.emit(10 + int(70 * (i / (adur * 2))), 100, "Recording...")
                    if not self.sp._is_alive(): raise RuntimeError("Daemon died during recording")
                self.progress.emit(80, 100, "Stopping all jobs..."); self.sp.stop_all(); time.sleep(1.0)
                self.progress.emit(85, 100, "Saving recording..."); self.sp.stop_recording(); time.sleep(0.5)
                temp_wav = TMP_AUDIO_DIR / "preview.wav"; temp_wav.parent.mkdir(exist_ok=True, parents=True)
                if temp_wav.exists(): temp_wav.unlink()
                if not self.sp.save_recording(str(temp_wav)): raise RuntimeError("save-recording send failed")
                observer = Observer(); handler = WavReadyHandler("preview.wav")
                observer.schedule(handler, str(TMP_AUDIO_DIR), recursive=False); observer.start()
                timeout = 30.0; start_time = time.time()
                while not handler.file_ready.is_set():
                    if time.time() - start_time > timeout: observer.stop(); observer.join(); raise FileNotFoundError(f"Sonic Pi did not write {temp_wav} within 30 s.")
                    if not self.sp._is_alive(): observer.stop(); observer.join(); raise RuntimeError("Daemon died while saving WAV.")
                    time.sleep(0.1)
                observer.stop(); observer.join()
                self.progress.emit(95, 100, "Loading audio..."); audio = load_wav(temp_wav)
                self.finished.emit(audio, len(audio) / SR, self.code); return
            except Exception as e:
                if tries < 2: self._kill_daemon(); time.sleep(3.0); continue
                logger.error(f"AudioPreviewWorker failed: {e}", exc_info=True); self.error.emit(str(e)); return

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
                err_output = proc.stderr.read().decode('utf-8', errors='ignore'); logger.error(f"FFmpeg failed:\n{err_output}")
                self.finished.emit("", False, f"FFmpeg encoding failed:\n{err_output[-500:]}")
            else: self.finished.emit(self.path, True, "Export complete")
        except Exception as e:
            logger.error(f"Export worker error: {e}", exc_info=True); self.finished.emit("", False, str(e))
''',
    "renderer.py": r'''from __future__ import annotations
import math, random
from typing import Dict, List, Optional, Tuple
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
import numpy as np
from core import FrameState, Theme, Preset, LayoutMode, AudioEngineConfig, Token, tokenize_ruby_line, TOKEN_COLOR_MAP

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
        from core import ThemeRegistry, PresetRegistry
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
            tokens = self._token_cache.get(line) or (self._token_cache.setdefault(line, tokenize_ruby_line(line)))
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
''',
    "main.py": r'''from __future__ import annotations
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
                               QDockWidget, QDoubleSpinBox, QCheckBox, QSpinBox, QTabWidget,
                               QGroupBox, QFormLayout, QLineEdit, QRadioButton, QButtonGroup)
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
        for tok in tokenize_ruby_line(text):
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
    def __init__(self, cfg: AudioEngineConfig, sp: SonicPiManager):
        super().__init__(); self.cfg = cfg; self.sonic_pi = sp
        self.setWindowTitle("Sonic Pi Animation Studio"); self.resize(1400, 800)
        self._playing = False; self._frame_idx = 0; self._frames = []; self._total_dur = 0.0
        self._current_code = ""; self._current_audio: Optional[np.ndarray] = None
        self._export_audio: Optional[np.ndarray] = None; self._current_audio_path = ""; self._is_exporting = False
        self._preview_worker: Optional[AudioPreviewWorker] = None; self._export_worker: Optional[ExportWorker] = None
        self.player = QMediaPlayer(); self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output); self.audio_output.setVolume(self.cfg.master_volume)
        self.player.positionChanged.connect(self._on_pos_changed); self.player.durationChanged.connect(self._on_dur_changed)
        self.timer = QTimer(); self.timer.setInterval(int(1000 / 30)); self.timer.timeout.connect(self._tick)
        self._build_ui(); self._load_settings(); self._load_input_scripts()
        self.anim.renderer.apply_config(self.cfg); self.highlighter.set_theme(ThemeRegistry.get(self.cfg.theme_name))

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
        self.code_edit.setPlainText("# Sonic Pi Animation Studio\nuse_bpm 120\n\nlive_loop :melody do\n  use_synth :tb303\n  play :e3, release: 0.2, cutoff: 80\n  sleep 0.25\n  play :g3, release: 0.2, cutoff: 90\n  sleep 0.25\nend\n\nlive_loop :drums do\n  sample :bd_haus\n  sleep 0.5\nend")
        self.highlighter = RubyHighlighter(self.code_edit.document(), ThemeRegistry.default()); splitter.addWidget(self.code_edit)
        self.anim = AnimWidget(); splitter.addWidget(self.anim); splitter.setSizes([450, 950]); root.addWidget(splitter, 1)
        audio_ctrl = QHBoxLayout()
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
        self.vol_spin.valueChanged.connect(self._update_cfg); general_layout.addRow("Master Volume:", self.vol_spin); tabs.addTab(general_tab, "General")
        typing_tab = QWidget(); typing_layout = QFormLayout(typing_tab)
        self.typing_mode_group = QButtonGroup()
        self.rb_constant = QRadioButton("Constant Speed"); self.rb_match_music = QRadioButton("Match to Music"); self.rb_beat_sync = QRadioButton("Beat Sync")
        self.typing_mode_group.addButton(self.rb_constant); self.typing_mode_group.addButton(self.rb_match_music); self.typing_mode_group.addButton(self.rb_beat_sync)
        if self.cfg.typing_mode == "constant": self.rb_constant.setChecked(True)
        elif self.cfg.typing_mode == "match_music": self.rb_match_music.setChecked(True)
        else: self.rb_beat_sync.setChecked(True)
        self.rb_constant.toggled.connect(self._update_cfg); self.rb_match_music.toggled.connect(self._update_cfg); self.rb_beat_sync.toggled.connect(self._update_cfg)
        typing_layout.addRow("Typing Mode:", self.rb_constant); typing_layout.addRow("", self.rb_match_music); typing_layout.addRow("", self.rb_beat_sync)
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
        if self.rb_constant.isChecked(): self.cfg.typing_mode = "constant"
        elif self.rb_match_music.isChecked(): self.cfg.typing_mode = "match_music"
        else: self.cfg.typing_mode = "beat_sync"
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
            for f in sorted(INPUT_DIR.glob("*.rb")): self.file_combo.addItem(str(f))
    def _browse_scripts(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Sonic Pi script", "", "Ruby (*.rb);;All files (*)")
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
    def _generate_audio(self):
        self._current_code = self.code_edit.toPlainText(); logger.info("Generating audio for code (%d chars)", len(self._current_code))
        self.status_bar.showMessage("Booting Sonic Pi and generating audio..."); self.progress.setVisible(True); self.progress.setValue(0)
        self._preview_worker = AudioPreviewWorker(self._current_code, self.sonic_pi, self.cfg.base_duration)
        self._preview_worker.progress.connect(lambda c,t,m: self.progress.setValue(c))
        self._preview_worker.finished.connect(self._on_audio_ready); self._preview_worker.error.connect(self._on_error); self._preview_worker.start()
    def _on_audio_ready(self, audio: np.ndarray, duration: float, code: str):
        logger.info("Audio ready: duration=%.2fs, samples=%d", duration, len(audio))
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
        if success: logger.info("Export success: %s", path); QMessageBox.information(self, "Success", f"Saved to {path}")
        else: logger.error("Export failed: %s", msg); QMessageBox.critical(self, "Error", msg)
    def _on_error(self, msg: str):
        logger.error("Worker error: %s", msg); self.progress.setVisible(False); QMessageBox.critical(self, "Error", msg)
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
        logger.info("Application shutting down"); self._save_settings()
        if self.sonic_pi.process:
            try: self.sonic_pi.process.terminate(); self.sonic_pi.process.wait(timeout=3)
            except subprocess.TimeoutExpired: self.sonic_pi.process.kill()
            except Exception: pass
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv); app.setStyle("Fusion")
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True); INPUT_DIR.mkdir(parents=True, exist_ok=True); TMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_firewall_rules()
    logger.info("=" * 60); logger.info("Sonic Pi Animation Studio starting up")
    logger.info("Log file: %s", LOG_PATH); logger.info("Settings: %s", SETTINGS_PATH)
    logger.info("Input dir: %s", INPUT_DIR); logger.info("Temp Audio dir: %s", TMP_AUDIO_DIR); logger.info("=" * 60)
    cfg = AudioEngineConfig(); sp = SonicPiManager()
    win = MainWindow(cfg, sp); win.show(); sys.exit(app.exec())

if __name__ == "__main__":
    main()
'''
}

def create_project():
    print("=" * 50)
    print(" Sonic Pi Animation Studio - Setup Script ")
    print("=" * 50)
    
    base_dir = Path.cwd()
    print(f"\nSetting up project in: {base_dir}")
    
    for filename, content in PROJECT_FILES.items():
        filepath = base_dir / filename
        print(f"Writing {filepath}...")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
            
    input_dir = base_dir / "input"
    input_dir.mkdir(exist_ok=True)
    print(f"Created directory: {input_dir}")
    
    print("\n✅ Project files created successfully!")
    print("\nNext steps:")
    print("1. Install dependencies: pip install -r requirements.txt")
    print("2. Run the app: python main.py")
    print("\nNote: Ensure Sonic Pi and FFmpeg are installed and in your system PATH.")

if __name__ == "__main__":
    create_project()