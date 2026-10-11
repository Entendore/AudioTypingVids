from __future__ import annotations

import os
import queue
import random
import signal
import base64
import subprocess
import logging
import traceback
import json  # Added import
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Callable, Final, Optional, final
from enum import Enum, auto

from PySide6.QtCore import QObject, QThread, Signal, QTimer, QUrl, Qt
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QWidget

# ============================================================================= Logging
LOG_FILE: Final[Path] = Path.cwd() / "strudel_animator.log"

class ColorCodes:
    RESET = "\033[0m"; DEBUG = "\033[94m"; INFO = "\033[92m"
    WARNING = "\033[93m"; ERROR = "\033[91m"; CRITICAL = "\033[41m"

class ColoredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if __import__("sys").stdout.isatty():
            color = getattr(ColorCodes, record.levelname, ColorCodes.RESET)
            record = logging.makeLogRecord(record.__dict__)
            record.levelname = f"{color}{record.levelname:<7}{ColorCodes.RESET}"
            record.name = f"{color}{record.name}{ColorCodes.RESET}"
        return super().format(record)

_FMT = "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s"
_DATEFMT = "%H:%M:%S"

_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)
_root_logger.handlers.clear()

_file_handler = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
_file_handler.setFormatter(logging.Formatter(_FMT, datefmt=_DATEFMT))
_root_logger.addHandler(_file_handler)

_console_handler = logging.StreamHandler(__import__("sys").stdout)
_console_handler.setFormatter(ColoredFormatter(_FMT, datefmt=_DATEFMT))
_root_logger.addHandler(_console_handler)

log = logging.getLogger("strudel")
log.info("Logging initialized — file: %s", LOG_FILE)

# ============================================================================= Constants & Config
DEFAULT_SPEED_MS: Final[int] = 45
SPEED_MIN_MS: Final[int] = 10
SPEED_MAX_MS: Final[int] = 200
FRAME_QUEUE_MAX: Final[int] = 180
TICK_MS: Final[int] = 33
AUDIO_POLL_MS: Final[int] = 50
REC_BLINK_MS: Final[int] = 500
SAVE_DEBOUNCE_MS: Final[int] = 800
FINAL_HOLD_MS: Final[int] = 1000

AUDIO_READY_POLL_MS: Final[int] = 400
AUDIO_MAX_READY_RETRIES: Final[int] = 80
AUDIO_READY_TIMEOUT_MS: Final[int] = 1000

STRUDEL_PROD_URL: Final[str] = "https://unpkg.com/strudel@latest/dist/strudel.min.js"

class StrEnum(str, Enum):
    def __str__(self) -> str: return self.value

class VisualizationMode(StrEnum):
    BARS = "Bars"; MIRROR = "Mirror"; WAVE = "Wave"; CIRCULAR = "Circular"

class AspectMode(StrEnum):
    FIT = "Fit (letterbox)"; FILL = "Fill (crop)"; STRETCH = "Stretch"

@final
@dataclass(frozen=True, slots=True)
class ExportConfig:
    width: int; height: int; fps: int; crf: int
    audio_bitrate: str; aspect: AspectMode
    include_visualizer: bool; gradient_background: bool

    @property
    def frame_interval_ms(self) -> int: return int(1000 / self.fps)

# ============================================================================= Utilities
def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def decode_audio_data_url(data_url: str, output_path: str | Path) -> int:
    if not data_url or not isinstance(data_url, str): return 0
    try:
        _, b64 = data_url.split(",", 1)
        audio_bytes = base64.b64decode(b64)
        Path(output_path).write_bytes(audio_bytes)
        log.info("Audio saved: %s (%d bytes)", output_path, len(audio_bytes))
        return len(audio_bytes)
    except Exception as e:
        log.error("Failed to decode audio data URL: %s", e)
        return 0

def _check_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except FileNotFoundError:
        log.error("FFmpeg not found in PATH — video export disabled.")
        return False
    except subprocess.CalledProcessError as e:
        log.error("FFmpeg check failed (rc=%d).", e.returncode)
        return False

HAS_FFMPEG: Final[bool] = _check_ffmpeg()

INPUT_DIR: Final[Path] = Path.cwd() / "input"
INPUT_DIR.mkdir(exist_ok=True)
OUTPUT_DIR: Final[Path] = Path.cwd() / "exports"
OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR: Final[Path] = Path.cwd() / "strudel_temp"
TEMP_DIR.mkdir(exist_ok=True)

def configure_environment() -> None:
    import sys
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    qt_flags = [
        "--no-sandbox",
        "--disable-features=IsolateOrigins,site-per-process",
        "--enable-features=JavaScriptHarmony",
        "--enable-experimental-web-platform-features",
        "--enable-javascript-harmony",
        "--autoplay-policy=no-user-gesture-required",
    ]
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", " ".join(qt_flags))
    signal.signal(signal.SIGINT, signal.SIG_DFL)

# ============================================================================= WebEngine Page
class LoggedWebPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        src_name = Path(sourceID).name if sourceID else "JS"
        msg = f"[JS:{src_name}:{lineNumber}] {message}"
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            log.error(msg)
        elif level == QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel:
            log.warning(msg)
        else:
            log.info(msg)

# ============================================================================= Audio bridge
@final
class StrudelAudio(QObject):
    audio_levels = Signal(list)
    ready_changed = Signal(bool)
    play_failed = Signal(str)
    status_message = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.view: Optional[QWebEngineView] = None
        self._page: Optional[LoggedWebPage] = None
        self._ready: bool = False
        self._recording: bool = False
        self._volume: int = 80
        self._ready_retries: int = 0
        self._pending_code: Optional[str] = None
        self._user_gesture_seen: bool = False

    def init(self, parent: QWidget, bridge_html_path: Path) -> bool:
        try:
            self.view = QWebEngineView(parent)
            self._page = LoggedWebPage(self.view)
            self.view.setPage(self._page)
            self.view.setFixedSize(1, 1)
            self.view.move(-10, -10)
            self.view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)

            s = self.view.settings()
            for attr in (
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
                QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
                QWebEngineSettings.WebAttribute.JavascriptEnabled,
                QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture,
                QWebEngineSettings.WebAttribute.AllowRunningInsecureContent,
            ):
                s.setAttribute(attr, True)
            try:
                s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptHarmony, True)
            except AttributeError:
                pass

            if not bridge_html_path.exists():
                log.error("Bridge HTML not found: %s", bridge_html_path)
                self.play_failed.emit(f"Bridge HTML not found:\n{bridge_html_path}")
                return False

            self.view.setUrl(QUrl.fromLocalFile(str(bridge_html_path)))
            self.view.loadFinished.connect(self._on_load_finished)
            log.info("StrudelAudio initialized: %s", bridge_html_path)
            self.status_message.emit("Loading Strudel engine…")
            return True
        except Exception as e:
            log.error("StrudelAudio init failed: %s\n%s", e, traceback.format_exc())
            self.play_failed.emit(f"WebEngine init failed:\n{e}")
            return False

    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            log.error("Bridge HTML failed to load")
            self.play_failed.emit("Strudel bridge HTML failed to load.")
            return
        QTimer.singleShot(AUDIO_READY_TIMEOUT_MS, self._check_ready_once)

    def _check_ready_once(self) -> None:
        js = (
            "(function(){"
            "  if (typeof window.isReady === 'function') return !!window.isReady();"
            "  if (typeof strudel !== 'undefined') return true;"
            "  if (window.strudelPlay) return true;"
            "  return false;"
            "})()"
        )
        self._run_js(js, self._on_ready_check)

    def _on_ready_check(self, ready: Any) -> None:
        ready = bool(ready)
        if ready and not self._ready:
            self._ready = True
            self._ready_retries = 0
            self.set_volume(self._volume)
            if self._user_gesture_seen:
                self.resume_audio_context()
            self.ready_changed.emit(True)
            log.info("Strudel audio engine ready")
            self.status_message.emit("Audio engine ready.")
            if self._pending_code is not None:
                code, self._pending_code = self._pending_code, None
                self.play(code)
            return

        if not ready:
            self._ready_retries += 1
            if self._ready_retries >= AUDIO_MAX_READY_RETRIES:
                msg = (f"Strudel audio engine failed to become ready after "
                       f"{AUDIO_MAX_READY_RETRIES} retries.")
                log.error(msg)
                self.play_failed.emit(msg)
                self.status_message.emit("Audio engine failed to initialize.")
                return
            if self._ready_retries % 5 == 0:
                self.status_message.emit(f"Waiting for Strudel engine… ({self._ready_retries})")
            QTimer.singleShot(AUDIO_READY_POLL_MS, self._check_ready_once)

    def is_ready(self) -> bool: return self._ready

    def notify_user_gesture(self) -> None:
        self._user_gesture_seen = True
        if self._ready:
            self.resume_audio_context()
        else:
            if self._ready_retries >= AUDIO_MAX_READY_RETRIES:
                self._ready_retries = 0
                QTimer.singleShot(50, self._check_ready_once)

    def _run_js(self, code: str, callback: Optional[Callable[[Any], None]] = None) -> None:
        if self.view and self.view.page():
            self.view.page().runJavaScript(code, 0, callback or (lambda _: None))
        elif callback:
            callback(None)

    def resume_audio_context(self) -> None:
        if self.view and self._ready:
            self._run_js(
                "window.resumeAudioContext && window.resumeAudioContext()",
                lambda r: log.debug("Audio context resume: %s", r),
            )

    def set_volume(self, vol: int) -> None:
        self._volume = int(vol)
        if self.view and self._ready:
            self._run_js(f"window.setMasterVolume && window.setMasterVolume({int(vol)});")

    def play(self, code: str) -> None:
        if not self.view:
            self.play_failed.emit("Audio view is not initialized.")
            return
        if not self._ready:
            log.warning("Cannot play yet — engine not ready, queuing request")
            self._pending_code = code
            self.status_message.emit("Waiting for engine…")
            if self._ready_retries >= AUDIO_MAX_READY_RETRIES:
                self._ready_retries = 0
                QTimer.singleShot(50, self._check_ready_once)
            return

        try:
            self.resume_audio_context()
            js = (
                "window.strudelPlay && window.strudelPlay(" + json.dumps(code) +
                ").catch(function(e){console.error('Strudel play error:',e)});"
            )
            self._run_js(js)
            log.info("Audio playback initiated")
        except Exception as e:
            log.error("Audio play failed: %s", e)
            self.play_failed.emit(f"Playback failed: {e}")

    def stop(self) -> None:
        if self.view:
            self._run_js(
                "window.strudelStop && window.strudelStop();",
                lambda _: log.info("Audio playback stopped"),
            )

    def start_recording(self, callback: Callable[[bool], None]) -> None:
        if not (self.view and self._ready):
            callback(False); return
        try:
            self._run_js(
                "window.startRecording ? window.startRecording() : Promise.resolve(false)",
                callback,
            )
            self._recording = True
            log.info("Web Audio recording started")
        except Exception as e:
            log.error("Start recording failed: %s", e)
            callback(False)

    def stop_recording(self, callback: Callable[[Optional[str]], None]) -> None:
        if not (self.view and self._recording):
            callback(None); return
        try:
            self._recording = False
            self._run_js(
                "(function(){return window.stopRecording ? window.stopRecording() "
                ": Promise.resolve(null);})()",
                callback,
            )
            log.info("Web Audio recording stopped, reading blob…")
        except Exception as e:
            log.error("Stop recording failed: %s", e)
            callback(None)

    def poll_audio_levels(self) -> None:
        if self.view and self._ready:
            self._run_js(
                "window.getAudioLevels ? window.getAudioLevels() : []",
                lambda levels: self.audio_levels.emit(levels if levels else []),
            )

    def cleanup(self) -> None:
        self.stop()
        if self.view:
            try: self.view.loadFinished.disconnect()
            except RuntimeError: pass
            self.view.deleteLater()
            self.view = None
        self._ready = False
        self._pending_code = None
        log.info("StrudelAudio cleaned up")

# ============================================================================= Typing engine
@final
class TypingEngine(QObject):
    typed = Signal(str); progress = Signal(int); finished = Signal()

    _HUMAN_BASE: Final[dict[str, float]] = {
        " ": 0.85, "\n": 1.8, ".": 2.2, ",": 1.6, ";": 1.5, ":": 1.4,
        "(": 1.2, ")": 1.1, "{": 1.3, "}": 1.2, "[": 1.2, "]": 1.1,
        "=": 1.1, '"': 1.2, "'": 1.1,
    }

    def __init__(self) -> None:
        super().__init__()
        self._code: str = ""; self._idx: int = 0; self._typed: str = ""
        self._speed: int = DEFAULT_SPEED_MS; self._human: bool = True
        self._paused: bool = False; self._running: bool = False
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._rng = random.Random()

    @property
    def running(self) -> bool: return self._running
    @property
    def paused(self) -> bool: return self._paused
    @property
    def progress_pct(self) -> int:
        return int(self._idx / len(self._code) * 100) if self._code else 0

    def set_code(self, code: str) -> None:
        self._code = code; self._idx = 0; self._typed = ""

    def set_speed(self, ms: int) -> None:
        self._speed = max(SPEED_MIN_MS, int(ms))
        if self._running and not self._paused:
            self._timer.setInterval(self._next_delay())

    def set_human(self, on: bool) -> None: self._human = on

    def start(self) -> None:
        if self._running or not self._code: return
        self._running = True; self._paused = False
        self._idx = 0; self._typed = ""
        self._timer.start(self._next_delay())

    def pause(self) -> None:
        if not self._running: return
        if self._paused:
            self._paused = False; self._timer.start(self._next_delay())
        else:
            self._paused = True; self._timer.stop()

    def stop(self) -> None:
        self._timer.stop(); self._running = False; self._paused = False

    def _next_delay(self) -> int:
        if not self._human: return self._speed
        ch = self._code[self._idx] if self._idx < len(self._code) else " "
        base = self._speed * self._HUMAN_BASE.get(ch, 1.0)
        jitter = self._rng.uniform(-0.15, 0.35) * self._speed
        delay = base + jitter
        if self._rng.random() < 0.012:
            delay += self._rng.uniform(1.0, 2.5) * self._speed
        return int(max(SPEED_MIN_MS, delay))

    def _chunk_size(self) -> int:
        if self._speed <= 15: return 3
        if self._speed <= 25: return 2
        return 1

    def _tick(self) -> None:
        if self._idx >= len(self._code):
            self._timer.stop(); self._running = False
            self.finished.emit(); return
        chunk = self._chunk_size()
        end = min(self._idx + chunk, len(self._code))
        added = self._code[self._idx:end]
        self._typed += added; self._idx = end
        self.typed.emit(added)
        self.progress.emit(self.progress_pct)
        self._timer.setInterval(self._next_delay())

# ============================================================================= Video writer worker
@final
class VideoWriterWorker(QObject):
    progress = Signal(str); finished_ok = Signal(str)
    failed = Signal(str); frame_dropped = Signal(int)

    def __init__(self, cfg: ExportConfig, output_path: str) -> None:
        super().__init__()
        self.cfg = cfg; self.output_path = output_path
        self.queue: queue.Queue[Optional[bytes]] = queue.Queue(maxsize=FRAME_QUEUE_MAX)
        self.audio_file: Optional[str] = None
        self._is_running = True; self._dropped = 0; self._cancelled = False

    def add_frame(self, frame_bytes: bytes) -> None:
        if not self._is_running: return
        try:
            self.queue.put(frame_bytes, block=True, timeout=0.5)
        except queue.Full:
            self._dropped += 1
            self.frame_dropped.emit(self._dropped)
            log.warning("Encoder queue full, dropped frame #%d", self._dropped)

    def finish_and_mux(self, audio_file: Optional[str]) -> None:
        self.audio_file = audio_file
        try:
            self.queue.put(None, block=True, timeout=5.0)
        except queue.Full:
            log.error("Could not enqueue finish sentinel")

    def cancel(self) -> None:
        self._cancelled = True
        try: self.queue.put_nowait(None)
        except queue.Full: pass

    def run(self) -> None:
        silent_video = str(TEMP_DIR / f"silent_{datetime.now().strftime('%H%M%S%f')}.mp4")
        cmd = [
            "ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{self.cfg.width}x{self.cfg.height}", "-r", str(self.cfg.fps),
            "-i", "-", "-c:v", "libx264", "-preset", "ultrafast",
            "-crf", str(self.cfg.crf), "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", silent_video,
        ]
        proc: Optional[subprocess.Popen] = None
        try:
            self.progress.emit("Encoding video stream…")
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                    stderr=subprocess.PIPE, stdout=subprocess.DEVNULL)
            stdin = proc.stdin
            while stdin is not None:
                frame = self.queue.get()
                if frame is None: break
                stdin.write(frame)

            if proc.stdin: proc.stdin.close()
            _, stderr = proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"FFmpeg video encoding failed:\n{stderr.decode('utf-8', errors='ignore')[-2000:]}")

            if self._cancelled:
                if os.path.exists(silent_video): os.unlink(silent_video)
                self.failed.emit("Export cancelled by user"); return

            has_audio = self.audio_file and os.path.exists(self.audio_file) and os.path.getsize(self.audio_file) > 1000
            if has_audio:
                self.progress.emit("Muxing audio stream…")
                mux_cmd = [
                    "ffmpeg", "-y", "-i", silent_video, "-i", self.audio_file,
                    "-c:v", "copy", "-c:a", "aac", "-b:a", self.cfg.audio_bitrate,
                    "-shortest", self.output_path,
                ]
                mux_proc = subprocess.run(mux_cmd, capture_output=True)
                if mux_proc.returncode != 0:
                    raise RuntimeError(f"FFmpeg muxing failed:\n{mux_proc.stderr.decode('utf-8', errors='ignore')[-2000:]}")
                for f in (silent_video, self.audio_file):
                    try:
                        if f: os.unlink(f)
                    except OSError: pass
            else:
                os.replace(silent_video, self.output_path)

            self.finished_ok.emit(self.output_path)
        except Exception as e:
            self.failed.emit(str(e))
        finally:
            self._is_running = False
            if proc is not None and proc.poll() is None:
                try: proc.kill()
                except Exception: pass

# ============================================================================= Batch processor
@final
class BatchProcessor(QObject):
    file_started = Signal(int, int, str)
    file_progress = Signal(str)
    file_finished = Signal(str, bool, str)
    batch_finished = Signal(int, int)

    def __init__(self, files: list[str], output_dir: str, skip_audio: bool = False) -> None:
        super().__init__()
        self._files = files; self._output_dir = output_dir
        self._idx = 0; self._succeeded = 0; self._failed = 0
        self._skip_audio = skip_audio

    @property
    def skip_audio(self) -> bool: return self._skip_audio

    def start(self) -> None:
        if not self._files:
            self.batch_finished.emit(0, 0); return
        self._process_current()

    def _process_current(self) -> None:
        if self._idx >= len(self._files):
            self.batch_finished.emit(self._succeeded, self._failed); return
        self.file_started.emit(self._idx, len(self._files), self._files[self._idx])

    def notify_file_done(self, success: bool, message: str) -> None:
        if success: self._succeeded += 1
        else: self._failed += 1
        self.file_finished.emit(self._files[self._idx], success, message)
        self._idx += 1
        QTimer.singleShot(400, self._process_current)

    def output_path_for(self, filepath: str) -> str:
        stem = Path(filepath).stem
        out = Path(self._output_dir) / f"{stem}.mp4"
        c = 1
        while out.exists():
            out = Path(self._output_dir) / f"{stem}_{c}.mp4"; c += 1
        return str(out)