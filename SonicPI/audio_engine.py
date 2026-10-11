from __future__ import annotations
import os, re, socket, subprocess, time, threading, platform, shutil
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple, Union
import numpy as np
from PySide6.QtCore import QThread, Signal, QObject
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from core import SR, FPS, FrameState, AudioEngineConfig

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[int, int, str], None]
CancelCheck = Callable[[], bool]

APP_ROOT = Path(__file__).resolve().parent
TMP_AUDIO_DIR = APP_ROOT / ".tmp_audio"


class OSCManager:
    """Handles standard OSC UDP communication without crashing Windows network stacks."""
    def __init__(self):
        self.send_port: Optional[int] = None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Bind to port 4557 (Sonic Pi GUI port). This prevents Windows from sending 
        # ICMP Port Unreachable packets back to Ruby, which was causing the server to crash.
        try:
            self.sock.bind(("127.0.0.1", 4557))
            logger.info("OSC Manager bound to GUI port 4557")
        except OSError as e:
            logger.warning(f"Could not bind to 4557: {e}. Binding to ephemeral port.")
            self.sock.bind(("127.0.0.1", 0))
            
        self.sock.settimeout(0.5)
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def _listen_loop(self):
        """Consume incoming OSC packets to prevent buffer overflow and Windows network resets."""
        while True:
            try:
                self.sock.recvfrom(8192)
            except socket.timeout:
                continue
            except OSError:
                break

    @staticmethod
    def _pad(data: Union[str, bytes]) -> bytes:
        if isinstance(data, str):
            data = data.encode("utf-8")
        return data + b"\x00" * ((4 - (len(data) % 4)) % 4)

    def send(self, address: str, *args: Any) -> bool:
        if not self.send_port:
            return False
        try:
            msg = self._pad(address)
            type_tags, payload = ",", b""
            for arg in args:
                if isinstance(arg, bool):
                    type_tags += "T" if arg else "F"
                elif isinstance(arg, str):
                    type_tags += "s"; payload += self._pad(arg)
                elif isinstance(arg, int):
                    type_tags += "i"; payload += struct.pack(">i", arg)
                elif isinstance(arg, float):
                    type_tags += "f"; payload += struct.pack(">f", arg)
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
        if sys_os == "Windows":
            base = r"C:\Program Files\Sonic Pi\app\server"
        elif sys_os == "Darwin":
            base = "/Applications/Sonic Pi.app/server"
        else:
            base = "/opt/sonic-pi/app/server"

        self.base_dir = base
        self.executable_path = os.path.join(base, "native", "ruby", "bin", "ruby")
        self._daemon_path = os.path.join(base, "ruby", "bin", "daemon.rb")

    def _is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def _kill_stale_processes(self):
        try:
            import psutil
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    name = (proc.info["name"] or "").lower()
                    cmdline = " ".join(proc.info["cmdline"] or []).lower()
                    if "scsynth" in name or "daemon.rb" in cmdline:
                        proc.terminate()
                        try: proc.wait(timeout=3)
                        except psutil.TimeoutExpired: proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            time.sleep(1.0)
        except ImportError:
            pass

    def launch(self) -> Tuple[bool, str]:
        self._kill_stale_processes()
        self.token = None
        self.daemon_port = None
        self._scsynth_ready = False

        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0
        
        # Pure, unmodified daemon.rb launch. No patches.
        cmd = [self.executable_path, self._daemon_path, "--no-scsynth-inputs"]
        logger.info(f"Launching daemon: {' '.join(cmd)}")

        env = os.environ.copy()
        env["SONIC_PI_SERVER_ROOT"] = self.base_dir

        self.process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, cwd=self.base_dir, env=env, creationflags=creationflags
        )

        threading.Thread(target=self._read_loop, daemon=True).start()

        start_time = time.time()
        while time.time() - start_time < 45.0:
            if self.process.poll() is not None:
                return False, "Daemon crashed during boot."
            if self.token and self.daemon_port:
                time.sleep(2.0) # Give scsynth a moment to finalize
                return True, "Boot successful"
            time.sleep(0.2)
        return False, "Token timeout."

    def _read_loop(self):
        token_re = re.compile(r'\b(\d{6,})\b')
        port_re = re.compile(r'\b(\d{4,5})\b')
        
        while self.process and self.process.poll() is None:
            line = self.process.stdout.readline()
            if not line: continue
            line = line.strip()
            if not line: continue
            logger.info(f"[Sonic Pi] {line}")

            if not (self.token and self.daemon_port):
                tok_match = token_re.search(line)
                if tok_match and not self.token:
                    self.token = int(tok_match.group(1))
                port_match = port_re.search(line)
                if port_match and not self.daemon_port:
                    self.daemon_port = int(port_match.group(1))
                    self.osc.send_port = self.daemon_port

            if "SuperCollider 3" in line or "scsynth ready" in line.lower():
                self._scsynth_ready = True

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
        if not event.is_directory and Path(event.src_path).name == self.target_filename:
            self.file_ready.set()
            
    def on_moved(self, event):
        if not event.is_directory and Path(event.dest_path).name == self.target_filename:
            self.file_ready.set()


def load_wav(path: Path, normalize: bool = True) -> np.ndarray:
    import wave
    with wave.open(str(path), "r") as w:
        n_channels = w.getnchannels()
        sampwidth = w.getsampwidth()
        frames = w.readframes(w.getnframes())
        
        if sampwidth == 2:
            audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        elif sampwidth == 4:
            try:
                audio = np.frombuffer(frames, dtype=np.float32)
            except ValueError:
                audio = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
        elif sampwidth == 3:
            audio = np.frombuffer(frames, dtype=np.uint8).astype(np.float32)
            audio = audio.reshape(-1, 3)
            audio = (audio[:, 0] | (audio[:, 1] << 8) | (audio[:, 2] << 16))
            audio = np.where(audio & 0x800000, audio - 0x1000000, audio).astype(np.float32) / 8388608.0
        else:
            raise ValueError(f"Unsupported sample width: {sampwidth}")
            
        if n_channels == 2:
            audio = audio.reshape(-1, 2).mean(axis=1)
            
    if normalize and len(audio) > 0:
        peak = np.max(np.abs(audio))
        if peak > 0:
            audio = audio / peak * 0.85
    return audio

def save_wav(audio: np.ndarray, path: Path) -> None:
    import wave
    data = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(data.tobytes())

def precompute(code: str, audio: np.ndarray, audio_dur: float, cfg: AudioEngineConfig,
               progress_cb: Optional[ProgressCallback] = None,
               is_cancelled: Optional[CancelCheck] = None) -> Tuple[List[FrameState], float]:
    nc = len(code)
    speed = cfg.typing_speed
    if cfg.match_typing_to_music and nc > 0:
        avail = audio_dur - 0.5 - 3.0
        if avail > 0.2:
            speed = nc / avail

    typing_dur = nc / speed if speed > 0 else audio_dur
    total = max(0.5 + typing_dur + 3.0, audio_dur)
    nf = int(total * FPS) + 1
    times = np.arange(nf) / FPS

    frames = []
    for i, t in enumerate(times):
        if is_cancelled and is_cancelled():
            return [], 0.0
        v = FrameState()
        v.char_index = max(0, min(int((t - 0.5) * speed), nc))
        v.time = float(t)
        v.code_done = t >= 0.5 + typing_dur

        s = int(t * SR)
        e = min(s + 1024, len(audio))
        if e > s:
            seg = audio[s:e]
            v.waveform = np.interp(np.linspace(0, len(seg) - 1, 256),
                                   np.arange(len(seg)), seg).astype(np.float32)
            v.beat_power = min(float(np.sqrt(np.mean(seg ** 2))) * 5, 1.0)
            v.rms = v.beat_power / 5.0
            v.peak_l = v.beat_power * np.random.uniform(0.85, 1.0)
            v.peak_r = v.beat_power * np.random.uniform(0.85, 1.0)

            if v.beat_power > (1.0 - cfg.beat_sensitivity):
                v.beat_on = True
                v.beat_strength = v.beat_power

            fft_seg = seg[:512] if len(seg) >= 512 else seg
            if len(fft_seg) > 0:
                fft_data = np.abs(np.fft.rfft(fft_seg))
                if len(fft_data) > 0:
                    v.spectrum = np.interp(np.linspace(0, len(fft_data) - 1, 64),
                                           np.arange(len(fft_data)),
                                           fft_data).astype(np.float32)
                    max_val = np.max(v.spectrum)
                    if max_val > 0:
                        v.spectrum /= max_val

        frames.append(v)
        if progress_cb and i % 30 == 0:
            progress_cb(i, nf, "Analyzing audio...")
    return frames, total


class CancelableWorker(QThread):
    progress = Signal(int, int, str)
    error = Signal(str)
    status = Signal(str)

    def __init__(self):
        super().__init__()
        self._cancel = False
        self._lock = threading.Lock()

    def cancel(self):
        with self._lock:
            self._cancel = True

    @property
    def is_cancelled(self):
        with self._lock:
            return self._cancel


class AudioPreviewWorker(CancelableWorker):
    finished = Signal(np.ndarray, float, str)

    def __init__(self, code: str, sp: SonicPiManager, base_dur: float):
        super().__init__()
        self.code = code
        self.sp = sp
        self.base_dur = base_dur

    def _kill_daemon(self):
        if self.sp.process:
            try:
                self.sp.process.terminate()
                self.sp.process.wait(timeout=5)
            except Exception:
                try: self.sp.process.kill()
                except: pass
            self.sp.process = None
            self.sp.token = None
            self.sp.daemon_port = None

    def run(self):
        tries = 0
        while tries < 2:
            tries += 1
            try:
                if not self.sp.process or self.sp.process.poll() is not None:
                    ok, msg = self.sp.launch()
                    if not ok:
                        if tries < 2: continue
                        self.error.emit(msg)
                        return

                self.progress.emit(10, 100, "Recording...")
                if not self.sp.start_recording(): raise RuntimeError("start-recording failed")
                time.sleep(0.3)
                if not self.sp.run_code(self.code): raise RuntimeError("run-code failed")

                adur = self.base_dur
                for i in range(int(adur * 2)):
                    if self.is_cancelled:
                        self.sp.stop_all()
                        return
                    time.sleep(0.5)
                    self.progress.emit(10 + int(70 * (i / (adur * 2))), 100, "Recording...")
                    if not self.sp._is_alive():
                        raise RuntimeError("Daemon died during recording")

                self.progress.emit(80, 100, "Stopping all jobs...")
                self.sp.stop_all()
                time.sleep(1.0)

                self.progress.emit(85, 100, "Saving recording...")
                self.sp.stop_recording()
                time.sleep(0.5)

                temp_wav = TMP_AUDIO_DIR / "preview.wav"
                temp_wav.parent.mkdir(exist_ok=True, parents=True)
                if temp_wav.exists():
                    temp_wav.unlink()

                if not self.sp.save_recording(str(temp_wav)):
                    raise RuntimeError("save-recording send failed")

                # Event-driven file wait
                observer = Observer()
                handler = WavReadyHandler("preview.wav")
                observer.schedule(handler, str(TMP_AUDIO_DIR), recursive=False)
                observer.start()

                timeout = 30.0
                start_time = time.time()
                while not handler.file_ready.is_set():
                    if time.time() - start_time > timeout:
                        observer.stop()
                        observer.join()
                        raise FileNotFoundError(f"Sonic Pi did not write {temp_wav} within 30 s.")
                    if not self.sp._is_alive():
                        observer.stop()
                        observer.join()
                        raise RuntimeError("Daemon died while saving WAV.")
                    time.sleep(0.1)

                observer.stop()
                observer.join()

                self.progress.emit(95, 100, "Loading audio...")
                audio = load_wav(temp_wav)
                self.finished.emit(audio, len(audio) / SR, self.code)
                return

            except Exception as e:
                if tries < 2:
                    logger.warning(f"Attempt {tries} failed: {e}; retrying...")
                    self._kill_daemon()
                    time.sleep(3.0)
                    continue
                logger.error(f"AudioPreviewWorker failed: {e}", exc_info=True)
                self.error.emit(str(e))
                return


class ExportWorker(CancelableWorker):
    finished = Signal(str, bool, str)

    def __init__(self, path: str, renderer: Any, code: str,
                 audio: np.ndarray, cfg: AudioEngineConfig):
        super().__init__()
        self.path = path
        self.renderer = renderer
        self.code = code
        self.audio = audio
        self.cfg = cfg

    def run(self):
        try:
            if not shutil.which("ffmpeg"):
                raise Exception("FFmpeg not found. Please install FFmpeg and ensure it's in your system PATH.")
            
            frames, td = precompute(
                self.code, self.audio, len(self.audio) / SR, self.cfg,
                lambda c, t, m: self.progress.emit(int(10 * c / t), 100, m),
                lambda: self.is_cancelled,
            )
            self.renderer.set_data(self.code, frames, td)

            temp_wav = TMP_AUDIO_DIR / "export.wav"
            temp_wav.parent.mkdir(exist_ok=True, parents=True)
            save_wav(self.audio, temp_wav)

            cmd = [
                "ffmpeg", "-y",
                "-f", "rawvideo", "-pix_fmt", "rgb32",
                "-s", f"{self.renderer.vw}x{self.renderer.vh}",
                "-r", str(FPS),
                "-i", "-",
                "-i", str(temp_wav),
                "-c:v", "libx264", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-shortest",
                self.path,
            ]
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            from PySide6.QtGui import QImage
            img = QImage(self.renderer.vw, self.renderer.vh, QImage.Format.Format_RGB32)
            for i, frame in enumerate(frames):
                if self.is_cancelled:
                    proc.kill()
                    self.finished.emit("", False, "Cancelled")
                    return
                self.renderer.render_to_image(img, i)
                proc.stdin.write(img.constBits().tobytes())
                self.progress.emit(10 + int(80 * (i / len(frames))), 100, f"Rendering {i}/{len(frames)}")

            proc.stdin.close()
            proc.wait()
            
            if proc.returncode != 0:
                err_output = proc.stderr.read().decode('utf-8', errors='ignore')
                logger.error(f"FFmpeg failed:\n{err_output}")
                self.finished.emit("", False, f"FFmpeg encoding failed:\n{err_output[-500:]}")
            else:
                self.finished.emit(self.path, True, "Export complete")
        except Exception as e:
            logger.error(f"Export worker error: {e}", exc_info=True)
            self.finished.emit("", False, str(e))