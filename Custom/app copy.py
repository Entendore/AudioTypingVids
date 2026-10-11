import sys
import os
import glob
import random
import re
import subprocess
import tempfile
import shutil
import math
import logging
import time
import threading
import queue
import numpy as np
import cv2
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QSlider, QLabel, QProgressBar, QFileDialog,
    QGroupBox, QComboBox, QGridLayout, QCheckBox, QSpinBox, QMessageBox,
    QSizePolicy, QLineEdit, QTabWidget, QFormLayout, QFrame,
    QScrollArea, QStatusBar, QListWidget, QListWidgetItem, QAbstractItemView,
    QInputDialog
)
from PySide6.QtCore import Qt, QTimer, QRect, QSize, QThread, QObject, Signal, Slot, QRegularExpression
from PySide6.QtGui import (
    QPainter, QColor, QFont, QPixmap, QImage, QIcon, QShortcut, QKeySequence,
    QSyntaxHighlighter, QTextCharFormat
)

# --- Logging Setup ---
LOG_FILE = os.path.join(os.getcwd(), "sc_animator.log")

def setup_logging():
    logger = logging.getLogger("SCAnimator")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        try:
            fh = logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
            fh.setLevel(logging.DEBUG)
            fmt = logging.Formatter(
                '%(asctime)s [%(levelname)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            fh.setFormatter(fmt)
            logger.addHandler(fh)
            logger.propagate = False
        except Exception as e:
            print(f"Failed to set up logfile at {LOG_FILE}: {e}", file=sys.stderr)
    return logger

log = setup_logging()

# --- Themes ---
THEMES = {
    "VS Code Dark": {
        "bg": "#1E1E1E", "fg": "#D4D4D4", "line_num": "#858585", "gutter_bg": "#1E1E1E",
        "status_bg": "#007ACC", "status_fg": "#FFFFFF",
        "comment": "#6A9955", "string": "#CE9178", "keyword": "#569CD6",
        "number": "#B5CEA8", "symbol": "#DCDCAA", "bracket": "#FFD700"
    },
    "Monokai": {
        "bg": "#272822", "fg": "#F8F8F2", "line_num": "#90908A", "gutter_bg": "#1E1F1C",
        "status_bg": "#75715E", "status_fg": "#FFFFFF",
        "comment": "#75715E", "string": "#E6DB74", "keyword": "#66D9EF",
        "number": "#AE81FF", "symbol": "#A6E22E", "bracket": "#F92672"
    },
    "Dracula": {
        "bg": "#282A36", "fg": "#F8F8F2", "line_num": "#6272A4", "gutter_bg": "#21222C",
        "status_bg": "#44475A", "status_fg": "#F8F8F2",
        "comment": "#6272A4", "string": "#F1FA8C", "keyword": "#8BE9FD",
        "number": "#BD93F9", "symbol": "#50FA7B", "bracket": "#FF79C6"
    },
    "Light (Solarized)": {
        "bg": "#FDF6E3", "fg": "#657B83", "line_num": "#93A1A1", "gutter_bg": "#EEE8D5",
        "status_bg": "#EEE8D5", "status_fg": "#657B83",
        "comment": "#93A1A1", "string": "#2AA198", "keyword": "#859900",
        "number": "#D33682", "symbol": "#268BD2", "bracket": "#CB4B16"
    }
}

SC_KEYWORDS = r'\b(SynthDef|Synth|Out|ar|kr|SinOsc|EnvGen|Env|Line|XLine|PlayBuf|Buffer|s|arg|var|Pbind|Ppar|Pseq)\b'

# =====================================================================
# SYNTAX HIGHLIGHTER
# =====================================================================
class SCSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, document, theme_name="VS Code Dark"):
        super().__init__(document)
        self.theme = THEMES.get(theme_name, THEMES["VS Code Dark"])
        self.rules = []
        self._build_rules()

    def _build_rules(self):
        self.rules = []
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self.theme["comment"]))
        self.rules.append((QRegularExpression(r'//[^\n]*'), fmt))

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self.theme["string"]))
        self.rules.append((QRegularExpression(r'"[^"\\]*(?:\\.[^"\\]*)*"'), fmt))

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self.theme["symbol"]))
        self.rules.append((QRegularExpression(r'\\[a-zA-Z_]\w*'), fmt))

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self.theme["number"]))
        self.rules.append((QRegularExpression(r'\b\d+\.?\d*\b'), fmt))

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self.theme["keyword"]))
        self.rules.append((QRegularExpression(SC_KEYWORDS), fmt))

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self.theme["bracket"]))
        self.rules.append((QRegularExpression(r'[\(\)\{\}\[\]]'), fmt))

    def highlightBlock(self, text):
        for pattern, format in self.rules:
            match_iter = pattern.globalMatch(text)
            while match_iter.hasNext():
                match = match_iter.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)

    def update_theme(self, theme_name):
        self.theme = THEMES.get(theme_name, THEMES["VS Code Dark"])
        self._build_rules()
        self.rehighlight()

# =====================================================================
# SUPERCOLLIDER MANAGER
# =====================================================================
class SCManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(SCManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized: return
        self._initialized = True
        self.process = None
        self.reader_thread = None
        self.output_queue = queue.Queue()
        self.cmd_lock = threading.Lock()
        self.boot_lock = threading.Lock()
        self.server_booted = False

    def start(self):
        if self.process and self.process.poll() is None: return True
        try:
            log.info("Booting persistent sclang process...")
            self.process = subprocess.Popen(
                ['sclang'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                errors='replace', bufsize=1
            )
            self.reader_thread = threading.Thread(target=self._read_output, daemon=True)
            self.reader_thread.start()
            self._wait_for_prompt()
            return True
        except FileNotFoundError:
            log.error("sclang not found in PATH.")
            return False
        except Exception as e:
            log.error(f"Failed to start sclang: {e}")
            return False

    def _read_output(self):
        buffer = ""
        while self.process and self.process.poll() is None:
            char = self.process.stdout.read(1)
            if not char: break
            if char == '\n':
                self.output_queue.put(buffer + '\n')
                buffer = ""
            else:
                buffer += char
                if 'sc3>' in buffer or '->' in buffer:
                    self.output_queue.put(buffer)
                    buffer = ""
        if buffer: self.output_queue.put(buffer)

    def _wait_for_prompt(self, timeout=30):
        start = time.time()
        while time.time() - start < timeout:
            try:
                line = self.output_queue.get(timeout=0.5)
                log.debug(f"[sclang-startup] {line.strip()}")
                if "sc3>" in line or "->" in line:
                    log.info("sclang is ready.")
                    return True
            except queue.Empty: continue
        log.warning("Timeout waiting for sclang prompt.")
        return False

    def execute(self, code, timeout=30):
        if not self.process or self.process.poll() is not None:
            if not self.start(): raise Exception("sclang process is not running.")
        with self.cmd_lock:
            while not self.output_queue.empty(): self.output_queue.get()
            sentinel = "SC_PYTHON_DONE_12345"
            stripped_code = code.strip()
            if stripped_code.startswith('(') and stripped_code.endswith(')'):
                stripped_code = stripped_code[1:-1]
            full_cmd = f'(\n{stripped_code}\n);\n"{sentinel}".postln;\n'
            try:
                self.process.stdin.write(full_cmd)
                self.process.stdin.flush()
            except Exception as e:
                raise Exception(f"Failed to write to sclang: {e}")
            start = time.time()
            collected_output = []
            while time.time() - start < timeout:
                try:
                    line = self.output_queue.get(timeout=0.5)
                    collected_output.append(line)
                    if sentinel in line:
                        out_str = "".join(collected_output).replace(sentinel, "")
                        log.debug(f"[sc-execute] Output:\n{out_str}")
                        return out_str
                except queue.Empty: continue
            out_str = "".join(collected_output)
            raise TimeoutError(f"SC execution timed out after {timeout}s. Output:\n{out_str}")

    def boot_server(self):
        with self.boot_lock:
            if self.server_booted: return True
            if not self.process:
                if not self.start(): return False
            try:
                with self.cmd_lock:
                    while not self.output_queue.empty(): self.output_queue.get()
                    log.info("Sending s.waitForBoot command...")
                    self.process.stdin.write('s.waitForBoot({ "SERVER_BOOTED_OK".postln; });\n')
                    self.process.stdin.flush()
                    start = time.time()
                    while time.time() - start < 60:
                        try:
                            line = self.output_queue.get(timeout=1.0)
                            log.debug(f"[sclang-boot] {line.strip()}")
                            if "SERVER_BOOTED_OK" in line:
                                self.server_booted = True
                                log.info("SuperCollider server booted successfully.")
                                return True
                        except queue.Empty: continue
            except Exception as e:
                log.error(f"Failed to boot server: {e}")
                return False
            log.error("Timeout waiting for server to boot.")
            return False

    def render_audio(self, code, audio_path, pre_delay, total_duration, input_files=None):
        if not self.boot_server(): raise Exception("Failed to boot SuperCollider server.")
        if input_files:
            paths_sc = [f'"{f.replace(chr(92), "/")}"' for f in input_files]
            load_code = f'~inputBufs = [ {", ".join(paths_sc)} ].collect({{ arg p; Buffer.read(s, p); }}); "Buffers Loaded".postln;'
            log.info(f"Loading input audio files into SC: {input_files}")
            self.execute(load_code, timeout=15)
            time.sleep(0.5)
        audio_path_sc = audio_path.replace('\\', '/')
        self.execute(f's.record("{audio_path_sc}");', timeout=5)
        if pre_delay > 0: time.sleep(pre_delay)
        start_time = time.time()
        self.execute(code, timeout=60)
        elapsed = time.time() - start_time + pre_delay
        remaining_time = total_duration - elapsed
        if remaining_time > 0: time.sleep(remaining_time)
        self.execute("s.stopRecording;", timeout=5)
        time.sleep(1.0)
        if not os.path.exists(audio_path): raise Exception("Audio file was not created after recording.")
        return audio_path

    def execute_live(self, code, duration=5.0):
        if not self.boot_server(): raise Exception("Failed to boot SuperCollider server.")
        self.execute(code, timeout=10)
        time.sleep(duration)
        self.execute("s.freeAll;", timeout=5)

    def stop(self):
        if self.process and self.process.poll() is None:
            try: self.execute("0.exit;", timeout=2)
            except: pass
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except: self.process.kill()
        self.process = None
        self.server_booted = False

# =====================================================================
# UI CLASSES
# =====================================================================
class CodeAnimatorWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.target_code = ""
        self.display_string = ""
        self.current_chars = 0
        self.cursor_visible = True
        self.font_family = "Consolas"
        self.font_size = 14
        self.theme = THEMES["VS Code Dark"]
        self.typo_mode = False
        self.in_typo = False
        self.executing = False
        self.post_message = "*** Welcome to SuperCollider 3.13. ***\n-> a Synth"
        self.post_chars = 0
        self.frame_index = 0
        self.fps = 30
        self.setMinimumSize(800, 600)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_code(self, text, typo_mode=False, post_msg=""):
        self.target_code = text
        self.display_string = ""
        self.current_chars = 0
        self.typo_mode = typo_mode
        self.in_typo = False
        self.executing = False
        self.post_chars = 0
        if post_msg: self.post_message = post_msg
        self.update()

    def toggle_cursor(self):
        self.cursor_visible = not self.cursor_visible
        self.update()

    def set_theme(self, theme_name):
        if theme_name in THEMES:
            self.theme = THEMES[theme_name]
            self.update()

    def set_font(self, family, size):
        self.font_family = family
        self.font_size = size
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(self.theme["bg"]))
        font = QFont(self.font_family, self.font_size)
        font.setStyleHint(QFont.Monospace)
        painter.setFont(font)
        fm = painter.fontMetrics()
        line_height = fm.height()
        
        x_margin = 60
        y_margin = 20
        post_window_height = 100
        viz_height = 60 if self.executing else 0

        painter.fillRect(0, 0, self.width(), 30, QColor(self.theme["status_bg"]))
        painter.setPen(QColor(self.theme["status_fg"]))
        painter.drawText(15, 20, "SuperCollider IDE - anim.scd")
        painter.setBrush(QColor("#FF5F56")); painter.drawEllipse(self.width() - 60, 10, 10, 10)
        painter.setBrush(QColor("#FFBD2E")); painter.drawEllipse(self.width() - 40, 10, 10, 10)
        painter.setBrush(QColor("#27C93F")); painter.drawEllipse(self.width() - 20, 10, 10, 10)

        painter.fillRect(0, 30, x_margin - 10, self.height() - 30, QColor(self.theme["gutter_bg"]))
        post_y_start = self.height() - post_window_height - viz_height
        painter.fillRect(0, post_y_start, self.width(), 2, QColor(self.theme["status_bg"]))
        painter.fillRect(0, post_y_start + 2, self.width(), post_window_height - 2, QColor(self.theme["gutter_bg"]))

        display_lines = self.display_string.split('\n')
        total_text_height = len(display_lines) * line_height
        max_visible_y = post_y_start - y_margin - 20
        y_offset = max(0, (y_margin + 30) + total_text_height - max_visible_y)
        
        painter.save()
        painter.translate(0, -y_offset)

        y = y_margin + 30
        x = x_margin
        line_num = 1
        
        for line in display_lines:
            safe_line = line.replace('\t', '    ')
            if y >= 30 - line_height and y <= post_y_start + y_offset:
                painter.setPen(QColor(self.theme["line_num"]))
                painter.drawText(10, y, str(line_num))
                self.draw_highlighted_line(painter, safe_line, x, y)
            y += line_height
            line_num += 1

        if self.cursor_visible and self.current_chars <= len(self.target_code) and not self.executing:
            text_before_cursor = self.display_string.split('\n')
            last_line = text_before_cursor[-1].replace('\t', '    ')
            cursor_x = x + fm.horizontalAdvance(last_line)
            cursor_y = y - line_height + 3 
            next_char = self.target_code[self.current_chars] if self.current_chars < len(self.target_code) else ""
            if next_char == '\n' or next_char == '': cursor_w = fm.horizontalAdvance(' ')
            else: cursor_w = fm.horizontalAdvance(next_char.replace('\t', '    '))
            cursor_w = max(cursor_w, 2)
            cursor_h = line_height - 6
            painter.fillRect(cursor_x, cursor_y, cursor_w, cursor_h, QColor(self.theme["fg"]))
        painter.restore()

        if self.executing:
            painter.setPen(QColor(self.theme["comment"]))
            painter.drawText(15, post_y_start + 20, "Post Window:")
            visible_post = self.post_message[:self.post_chars]
            post_y = post_y_start + 40
            for line in visible_post.split('\n'):
                painter.setPen(QColor(self.theme["fg"]))
                painter.drawText(x, post_y, line)
                post_y += line_height
            if self.cursor_visible:
                post_lines = visible_post.split('\n')
                last_post_line = post_lines[-1]
                pc_x = x + fm.horizontalAdvance(last_post_line)
                pc_y = post_y - line_height + 3
                pc_w = max(fm.horizontalAdvance(' '), 2)
                pc_h = line_height - 6
                painter.fillRect(pc_x, pc_y, pc_w, pc_h, QColor(self.theme["fg"]))

            viz_y = self.height() - viz_height
            painter.fillRect(0, viz_y, self.width(), viz_height, QColor(self.theme["gutter_bg"]))
            num_bars = 48
            bar_width = (self.width() - 40) / num_bars
            time_val = self.frame_index / self.fps
            for i in range(num_bars):
                height = abs(math.sin(time_val * 5.0 + i * 0.4)) * 30 + random.randint(2, 20)
                bx = 20 + (i * bar_width)
                by = viz_y + viz_height - height - 5
                painter.fillRect(bx, by, bar_width - 2, height, QColor(self.theme["keyword"]))

        painter.fillRect(0, self.height() - 20, self.width(), 20, QColor(self.theme["status_bg"]))
        painter.setPen(QColor(self.theme["status_fg"]))
        if self.executing: painter.drawText(15, self.height() - 5, "● Executing...")
        else: painter.drawText(15, self.height() - 5, "○ Ready")

    def draw_highlighted_line(self, painter, line, x, y):
        fm = painter.fontMetrics()
        patterns = [
            ('comment', r'//.*'), ('string', r'"[^\n]*?"'), ('number', r'\b\d+\.?\d*\b'),
            ('symbol', r'\\\w+'), ('keyword', SC_KEYWORDS), ('bracket', r'[\(\)\{\}\[\]]'),
            ('default', r'[^\s]')
        ]
        regex = '|'.join(f'(?P<{name}>{pat})' for name, pat in patterns)
        current_x = x
        for match in re.finditer(regex, line):
            text_type = match.lastgroup
            text = match.group()
            color = self.theme.get(text_type, self.theme["fg"])
            painter.setPen(QColor(color))
            painter.drawText(current_x, y, text)
            current_x += fm.horizontalAdvance(text)

# =====================================================================
# EXPORT WORKER
# =====================================================================
class ExportWorker(QObject):
    request_frame = Signal(dict)
    progress_update = Signal(int, int, str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, main_window, files_data, input_files=None):
        super().__init__()
        self.mw = main_window
        self.sc_manager = main_window.sc_manager
        self.files_data = files_data
        self.input_files = input_files
        self.frame_queue = queue.Queue(maxsize=1)
        self.is_running = True

    @Slot()
    def run_export(self):
        try:
            for idx, (code_text, output_path) in enumerate(self.files_data):
                if not self.is_running: break
                self.process_single_file(idx, code_text, output_path)
            self.finished.emit()
        except Exception as e:
            log.exception("Export worker failed")
            self.error.emit(str(e))

    def process_single_file(self, file_idx, code_text, output_path):
        w, h = self.mw.get_export_geometry()
        fps = self.mw.get_fps()
        mode = self.mw.mode_combo.currentText()
        base_speed = self.mw.speed_slider.value()
        audio_capture_on = self.mw.audio_capture_check.isChecked()
        post_msg = self.mw.post_input.text()
        end_padding_sec = self.mw.padding_spin.value()
        capture_real_post = self.mw.capture_post_check.isChecked()
        
        if capture_real_post and self.sc_manager.server_booted:
            self.progress_update.emit(file_idx, -1, "Capturing real SC output...")
            try:
                real_out = self.sc_manager.execute(code_text, timeout=15)
                lines = [l.strip() for l in real_out.strip().split('\n') if l.strip() and 'sc3>' not in l]
                if lines: post_msg = lines[-1]
            except Exception as e:
                log.warning(f"Failed to capture real post output: {e}")

        typo_mode = (mode == "Typo Simulation")
        chars_per_frame = base_speed / fps
        total_chars = len(code_text)
        execution_frames = int(total_chars / chars_per_frame)
        if typo_mode: execution_frames = int(execution_frames * 1.15)
        post_frames = int(len(post_msg) / 10) + 30
        padding_frames = int(end_padding_sec * fps)
        total_steps = execution_frames + post_frames + padding_frames
        total_duration = total_steps / fps
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        base_temp_dir = os.path.join(os.getcwd(), "sc_temp")
        os.makedirs(base_temp_dir, exist_ok=True)
        temp_video = os.path.join(base_temp_dir, os.path.basename(output_path) + ".raw.mp4")
        out = cv2.VideoWriter(temp_video, fourcc, fps, (w, h))
        
        local_chars = 0
        local_display = ""
        in_typo = False
        char_accumulator = 0.0
        
        for i in range(total_steps):
            if not self.is_running: break
            if i < execution_frames:
                if "Constant" in mode: char_accumulator += chars_per_frame
                elif "Human" in mode: char_accumulator += chars_per_frame * random.uniform(0.5, 1.5)
                elif "Punctuation" in mode:
                    if local_chars > 0 and code_text[local_chars-1] in ".,;({[":
                        char_accumulator += chars_per_frame * 0.2
                    else: char_accumulator += chars_per_frame * random.uniform(0.8, 1.2)
                elif "Typo" in mode: char_accumulator += chars_per_frame * random.uniform(0.8, 1.2)
                
                while char_accumulator >= 1.0 and local_chars < total_chars:
                    char_accumulator -= 1.0
                    target_char = code_text[local_chars]
                    if typo_mode:
                        if target_char.isalpha() and random.random() < 0.08 and not in_typo:
                            in_typo = True
                            local_display += chr(random.randint(97, 122))
                        elif in_typo:
                            in_typo = False
                            local_display = local_display[:-1]
                            char_accumulator = 0.0 
                        else:
                            local_display += target_char
                            local_chars += 1
                    else:
                        local_display += target_char
                        local_chars += 1
            
            executing = (i >= execution_frames)
            target_post_chars = int((i - execution_frames) * 10) if executing else 0
            post_chars = min(target_post_chars, len(post_msg)) if executing else 0
            
            state = {
                'display_string': local_display, 'current_chars': local_chars,
                'executing': executing, 'post_message': post_msg, 'post_chars': post_chars,
                'frame_index': i, 'cursor_visible': (i % (fps//2)) < (fps//4),
                'w': w, 'h': h
            }
            while not self.frame_queue.empty(): self.frame_queue.get()
            self.request_frame.emit(state)
            
            frame_arr = None
            while True:
                if not self.is_running: break
                try:
                    frame_arr = self.frame_queue.get(timeout=0.1)
                    break
                except queue.Empty: continue
            if frame_arr is None: break
            out.write(frame_arr)
            
            val = int((i / total_steps) * 100)
            self.progress_update.emit(file_idx, val, "Rendering Video...")
        
        out.release()
        if not self.is_running: return
            
        sc_audio_path = None
        if audio_capture_on:
            self.progress_update.emit(file_idx, -1, "Capturing SC audio...")
            pre_delay = execution_frames / fps
            audio_temp_dir = tempfile.mkdtemp(dir=base_temp_dir)
            sc_audio_path = os.path.join(audio_temp_dir, "output.wav")
            self.sc_manager.render_audio(code_text, sc_audio_path, pre_delay, total_duration, input_files=self.input_files)
        
        self.progress_update.emit(file_idx, -1, "Merging & Encoding MP4...")
        self.mw.merge_audio_video(temp_video, sc_audio_path, output_path, self.mw.norm_check.isChecked())
        
        if os.path.exists(temp_video): os.remove(temp_video)
        if sc_audio_path and os.path.exists(os.path.dirname(sc_audio_path)):
            shutil.rmtree(os.path.dirname(sc_audio_path))
            
    @Slot(object)
    def receive_frame(self, frame_arr):
        try: self.frame_queue.put_nowait(frame_arr)
        except queue.Full: pass

    def stop(self):
        self.is_running = False
        try: self.frame_queue.put_nowait(None)
        except queue.Full: pass

# =====================================================================
# AUDIO TEST WORKERS
# =====================================================================
class AudioTestWorker(QObject):
    progress = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, sc_manager, code, input_files=None):
        super().__init__()
        self.sc_manager = sc_manager
        self.code = code
        self.input_files = input_files

    @Slot()
    def run_test(self):
        try:
            self.progress.emit("Booting server...")
            if not self.sc_manager.boot_server():
                self.error.emit("Failed to boot SuperCollider server. Check logs.")
                return
            self.progress.emit("Recording audio (5 sec)...")
            base_temp_dir = os.path.join(os.getcwd(), "sc_temp")
            os.makedirs(base_temp_dir, exist_ok=True)
            temp_dir = tempfile.mkdtemp(dir=base_temp_dir)
            audio_path = os.path.join(temp_dir, "output.wav")
            self.sc_manager.render_audio(self.code, audio_path, 0.0, 5.0, input_files=self.input_files)
            self.progress.emit("Test complete. Playing...")
            self.finished.emit(audio_path)
        except Exception as e:
            self.error.emit(str(e))

class LiveCodeWorker(QObject):
    progress = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, sc_manager, code):
        super().__init__()
        self.sc_manager = sc_manager
        self.code = code

    @Slot()
    def run_test(self):
        try:
            self.progress.emit("Booting server...")
            if not self.sc_manager.boot_server():
                self.error.emit("Failed to boot SuperCollider server. Check logs.")
                return
            self.progress.emit("Executing live code (5 sec)...")
            self.sc_manager.execute_live(self.code, duration=5.0)
            self.progress.emit("Live test complete.")
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

# =====================================================================
# HELPERS
# =====================================================================
def styled_button(text, color=None, bold=False):
    btn = QPushButton(text)
    if color:
        btn.setStyleSheet(
            f"background-color: {color}; color: white; "
            f"font-weight: {'bold' if bold else 'normal'}; "
            f"padding: 8px; border-radius: 4px;"
        )
    else:
        btn.setStyleSheet("padding: 6px;")
    return btn

class CodeTextEdit(QTextEdit):
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Tab and event.modifiers() == Qt.NoModifier:
            self.insertPlainText("    ")
        else:
            super().keyPressEvent(event)

# =====================================================================
# MAIN WINDOW
# =====================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SuperCollider Code Animator Studio")
        self.resize(1400, 850)
        log.info("=" * 60)
        log.info("SuperCollider Code Animator Studio starting up")
        log.info("Logfile location: %s", LOG_FILE)
        
        self.sc_manager = SCManager()
        self.sc_manager.start()
        
        self.export_thread = None
        self.export_worker = None
        self.audio_test_thread = None
        self.live_test_thread = None
        
        # Project Folders
        self.input_folder_path = os.path.join(os.getcwd(), "input")
        os.makedirs(self.input_folder_path, exist_ok=True)
        self.current_code_file = None

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        self.tab_widget = QTabWidget()
        self.tab_widget.setFixedWidth(520)
        self.tab_widget.setDocumentMode(True)
        
        self._build_code_tab()
        self._build_visual_tab()
        self._build_animation_tab()
        self._build_audio_tab()
        self._build_export_tab()
        
        main_layout.addWidget(self.tab_widget)

        right_panel = QVBoxLayout()
        right_panel.setContentsMargins(0, 0, 0, 0)
        preview_header = QLabel("▶  Live Animator Preview")
        preview_header.setStyleSheet(
            "background-color: #2D2D30; color: #CCCCCC; padding: 6px; "
            "font-weight: bold; border-radius: 3px;"
        )
        right_panel.addWidget(preview_header)
        self.animator = CodeAnimatorWidget()
        right_panel.addWidget(self.animator, stretch=1)
        main_layout.addLayout(right_panel, stretch=1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("Ready")
        self.status_bar.addWidget(self.status_label)
        self.sc_status_label = QLabel("sclang: starting...")
        self.status_bar.addPermanentWidget(self.sc_status_label)
        QTimer.singleShot(100, self._check_sc_status)

        self.type_timer = QTimer()
        self.type_timer.timeout.connect(self.type_step)
        self.cursor_timer = QTimer()
        self.cursor_timer.timeout.connect(self.animator.toggle_cursor)
        self.cursor_timer.start(500)

        self.theme_test_timer = QTimer()
        self.theme_test_index = 0
        self.exec_test_timer = QTimer()
        self.exec_test_step_count = 0

        self.refresh_all_files()
        self.load_code()
        log.info("UI initialized successfully")

    # ----------------------------------------------------------------
    # TAB BUILDERS
    # ----------------------------------------------------------------
    def _build_code_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Folder Group
        folder_group = QGroupBox("Input Folder")
        folder_layout = QHBoxLayout()
        self.input_folder_label = QLabel(self.input_folder_path)
        self.input_folder_label.setWordWrap(True)
        self.input_folder_label.setStyleSheet("background-color: #2D2D30; color: #CCCCCC; padding: 4px; border-radius: 3px;")
        folder_layout.addWidget(self.input_folder_label, stretch=1)
        self.set_folder_btn = styled_button("Browse")
        self.set_folder_btn.clicked.connect(self.set_input_folder)
        folder_layout.addWidget(self.set_folder_btn)
        folder_group.setLayout(folder_layout)
        layout.addWidget(folder_group)

        # File Manager Group
        file_group = QGroupBox("File Manager")
        file_layout = QVBoxLayout()
        
        file_ctrl_layout = QHBoxLayout()
        self.file_combo = QComboBox()
        self.file_combo.currentIndexChanged.connect(self.load_selected_file)
        file_ctrl_layout.addWidget(self.file_combo, stretch=1)
        
        self.new_file_btn = styled_button("New")
        self.new_file_btn.clicked.connect(self.create_new_file)
        file_ctrl_layout.addWidget(self.new_file_btn)
        
        self.save_file_btn = styled_button("Save", color="#4CAF50")
        self.save_file_btn.clicked.connect(self.save_current_file)
        file_ctrl_layout.addWidget(self.save_file_btn)
        
        self.del_file_btn = styled_button("Delete", color="#F44336")
        self.del_file_btn.clicked.connect(self.delete_current_file)
        file_ctrl_layout.addWidget(self.del_file_btn)
        file_layout.addLayout(file_ctrl_layout)
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)
        
        # Editor Group
        code_group = QGroupBox("SuperCollider Code")
        code_layout = QVBoxLayout()
        self.code_input = CodeTextEdit()
        self.code_input.setPlainText(
            '"// Simple Synth"\n'
            'SynthDef(\\sine, {\n'
            '    arg freq=440, amp=0.5;\n'
            '    var sig;\n'
            '    sig = SinOsc.ar(freq) * amp;\n'
            '    Out.ar(0, sig ! 2);\n'
            '}).add;\n\n'
            'Synth(\\sine, [\\freq, 220]);'
        )
        self.code_input.setFont(QFont("Consolas", 11))
        self.highlighter = SCSyntaxHighlighter(self.code_input.document(), "VS Code Dark")
        QShortcut(QKeySequence("Ctrl+Return"), self.code_input, activated=self.play_animation)
        QShortcut(QKeySequence("Ctrl+S"), self.code_input, activated=self.save_current_file)
        QShortcut(QKeySequence("Ctrl+E"), self.code_input, activated=lambda: self.start_export(batch=False))
        code_layout.addWidget(self.code_input)
        code_group.setLayout(code_layout)
        layout.addWidget(code_group)
        
        post_group = QGroupBox("Simulated Post Window Output")
        post_layout = QVBoxLayout()
        self.post_input = QLineEdit('-> a Synth')
        post_layout.addWidget(self.post_input)
        post_group.setLayout(post_layout)
        layout.addWidget(post_group)
        
        btn_layout = QHBoxLayout()
        self.load_btn = styled_button("Load Code to Animator")
        self.load_btn.clicked.connect(self.load_code)
        btn_layout.addWidget(self.load_btn)
        self.play_btn = styled_button("Preview (Ctrl+Enter)", color="#607D8B", bold=True)
        self.play_btn.clicked.connect(self.play_animation)
        btn_layout.addWidget(self.play_btn)
        layout.addLayout(btn_layout)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Code")

    def _build_visual_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        theme_group = QGroupBox("Theme")
        theme_layout = QFormLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(THEMES.keys())
        self.theme_combo.currentTextChanged.connect(self.animator_theme_changed)
        theme_layout.addRow("Editor Theme:", self.theme_combo)
        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)
        
        font_group = QGroupBox("Font")
        font_layout = QFormLayout()
        self.font_combo = QComboBox()
        self.font_combo.addItems(["Consolas", "Courier New", "Monaco", "Menlo", "DejaVu Sans Mono"])
        self.font_combo.currentTextChanged.connect(self.animator_font_changed)
        font_layout.addRow("Font Family:", self.font_combo)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(10, 32)
        self.size_spin.setValue(14)
        self.size_spin.valueChanged.connect(self.animator_font_changed)
        font_layout.addRow("Font Size:", self.size_spin)
        font_group.setLayout(font_layout)
        layout.addWidget(font_group)

        test_group = QGroupBox("Visual Tests")
        test_layout = QVBoxLayout()
        self.test_themes_btn = styled_button("Cycle Themes (Preview)")
        self.test_themes_btn.clicked.connect(self.test_theme_cycle)
        test_layout.addWidget(self.test_themes_btn)
        self.test_exec_btn = styled_button("Test Execution State (Visualizer)")
        self.test_exec_btn.clicked.connect(self.test_exec_state)
        test_layout.addWidget(self.test_exec_btn)
        self.test_typing_btn = styled_button("Test Typing Animation")
        self.test_typing_btn.clicked.connect(self.play_animation)
        test_layout.addWidget(self.test_typing_btn)
        test_help = QLabel("Run these tests to see how the animator handles theme switches, the execution visualizer, and typing modes without rendering a full video.")
        test_help.setWordWrap(True)
        test_help.setStyleSheet("color: #888; font-size: 11px;")
        test_layout.addWidget(test_help)
        test_group.setLayout(test_layout)
        layout.addWidget(test_group)
        layout.addStretch()
        self.tab_widget.addTab(tab, "Visual")

    def _build_animation_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        style_group = QGroupBox("Typing Style")
        style_layout = QFormLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Constant Speed", "Human (Random)", "Punctuation Delay", "Typo Simulation"])
        style_layout.addRow("Style:", self.mode_combo)
        style_help = QLabel("• Constant Speed — fixed rate\n• Human (Random) — varied timing\n• Punctuation Delay — pause at .,;({[\n• Typo Simulation — occasionally mistypes")
        style_help.setWordWrap(True)
        style_help.setStyleSheet("color: #888; font-size: 11px;")
        style_layout.addRow(style_help)
        style_group.setLayout(style_layout)
        layout.addWidget(style_group)
        
        speed_group = QGroupBox("Typing Speed")
        speed_layout = QVBoxLayout()
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(1, 100)
        self.speed_slider.setValue(15)
        self.speed_label = QLabel("Speed: 15 cps")
        self.speed_label.setStyleSheet("font-weight: bold;")
        self.speed_slider.valueChanged.connect(lambda v: self.speed_label.setText(f"Speed: {v} cps"))
        speed_layout.addWidget(self.speed_label)
        speed_layout.addWidget(self.speed_slider)
        speed_group.setLayout(speed_layout)
        layout.addWidget(speed_group)
        
        fmt_group = QGroupBox("Output Format")
        fmt_layout = QFormLayout()
        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["24 FPS", "30 FPS", "60 FPS"])
        self.fps_combo.currentTextChanged.connect(self.update_animator_fps)
        fmt_layout.addRow("Frame Rate:", self.fps_combo)
        self.res_combo = QComboBox()
        self.res_combo.addItems(["1280x720 (HD)", "1920x1080 (Full HD)", "1080x1920 (TikTok/Shorts)", "800x600 (Default)"])
        fmt_layout.addRow("Resolution:", self.res_combo)
        self.padding_spin = QSpinBox()
        self.padding_spin.setRange(0, 30)
        self.padding_spin.setValue(3)
        self.padding_spin.setSuffix(" sec")
        fmt_layout.addRow("End Padding:", self.padding_spin)
        fmt_group.setLayout(fmt_layout)
        layout.addWidget(fmt_group)
        layout.addStretch()
        self.tab_widget.addTab(tab, "Animation")

    def _build_audio_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        cap_group = QGroupBox("Audio Capture Settings")
        cap_layout = QVBoxLayout()
        self.audio_capture_check = QCheckBox("Capture Audio from SuperCollider")
        self.audio_capture_check.setChecked(True)
        cap_layout.addWidget(self.audio_capture_check)
        self.norm_check = QCheckBox("Normalize Audio (loudnorm: I=-16, TP=-1.5)")
        self.norm_check.setChecked(True)
        cap_layout.addWidget(self.norm_check)
        self.capture_post_check = QCheckBox("Capture Real SC Output for Post Window")
        self.capture_post_check.setToolTip("Executes the code silently before rendering to capture the actual output (e.g., '-> a Synth').")
        cap_layout.addWidget(self.capture_post_check)
        cap_group.setLayout(cap_layout)
        layout.addWidget(cap_group)

        input_group = QGroupBox("Input Audio Files (from Input Folder)")
        input_layout = QVBoxLayout()
        input_ctrl_layout = QHBoxLayout()
        self.refresh_audio_btn = styled_button("Refresh List")
        self.refresh_audio_btn.clicked.connect(self.refresh_audio_files)
        input_ctrl_layout.addWidget(self.refresh_audio_btn)
        input_layout.addLayout(input_ctrl_layout)
        
        self.audio_list_widget = QListWidget()
        self.audio_list_widget.setStyleSheet("font-size: 11px;")
        input_layout.addWidget(self.audio_list_widget)
        
        input_help = QLabel("Checked files are loaded into SC as an array: ~inputBufs.\nAccess them in your code like: PlayBuf.ar(2, ~inputBufs[0]);")
        input_help.setWordWrap(True)
        input_help.setStyleSheet("color: #888; font-size: 11px;")
        input_layout.addWidget(input_help)
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)
        
        test_group = QGroupBox("Audio Testing")
        test_layout = QVBoxLayout()
        test_btn_layout = QHBoxLayout()
        self.test_audio_btn = styled_button("Test Audio Capture", color="#FF9800", bold=True)
        self.test_audio_btn.clicked.connect(self.test_audio_capture)
        test_btn_layout.addWidget(self.test_audio_btn)
        self.test_live_btn = styled_button("Test Live Execution", color="#9C27B0", bold=True)
        self.test_live_btn.clicked.connect(self.test_live_execution)
        test_btn_layout.addWidget(self.test_live_btn)
        test_layout.addLayout(test_btn_layout)
        test_group.setLayout(test_layout)
        layout.addWidget(test_group)
        layout.addStretch()
        self.tab_widget.addTab(tab, "Audio")

    def _build_export_tab(self):
        tab = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(10, 10, 10, 10)
        
        single_group = QGroupBox("Single Video Export")
        single_layout = QVBoxLayout()
        self.export_btn = styled_button("Export Current Code to MP4 (Ctrl+E)", color="#4CAF50", bold=True)
        self.export_btn.clicked.connect(lambda: self.start_export(batch=False))
        single_layout.addWidget(self.export_btn)
        self.cancel_export_btn = styled_button("Cancel Export", color="#F44336", bold=True)
        self.cancel_export_btn.clicked.connect(self.cancel_export)
        self.cancel_export_btn.setVisible(False)
        single_layout.addWidget(self.cancel_export_btn)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Idle")
        single_layout.addWidget(self.progress_bar)
        single_group.setLayout(single_layout)
        layout.addWidget(single_group)

        pipeline_test_group = QGroupBox("Pipeline Test")
        pt_layout = QVBoxLayout()
        self.test_video_btn = styled_button("Test Video Export (Short MP4)", color="#009688", bold=True)
        self.test_video_btn.clicked.connect(self.test_video_export)
        pt_layout.addWidget(self.test_video_btn)
        pt_help = QLabel("Renders a short hardcoded test file through the full video+audio pipeline to verify everything works, then plays it back.")
        pt_help.setWordWrap(True)
        pt_help.setStyleSheet("color: #888; font-size: 11px;")
        pt_layout.addWidget(pt_help)
        pipeline_test_group.setLayout(pt_layout)
        layout.addWidget(pipeline_test_group)
        
        batch_group = QGroupBox("Batch Rendering (from Input Folder)")
        batch_layout = QVBoxLayout()
        
        batch_ctrl_layout = QHBoxLayout()
        self.refresh_batch_btn = styled_button("Refresh")
        self.refresh_batch_btn.clicked.connect(self.refresh_batch_files)
        batch_ctrl_layout.addWidget(self.refresh_batch_btn)
        self.select_all_btn = styled_button("Select All")
        self.select_all_btn.clicked.connect(self.select_all_batch_files)
        batch_ctrl_layout.addWidget(self.select_all_btn)
        self.clear_sel_btn = styled_button("Clear Selection")
        self.clear_sel_btn.clicked.connect(self.clear_batch_selection)
        batch_ctrl_layout.addWidget(self.clear_sel_btn)
        batch_layout.addLayout(batch_ctrl_layout)
        
        self.batch_list_widget = QListWidget()
        self.batch_list_widget.setSelectionMode(QAbstractItemView.MultiSelection)
        self.batch_list_widget.setMaximumHeight(150)
        self.batch_list_widget.setStyleSheet("font-size: 11px;")
        batch_layout.addWidget(self.batch_list_widget)
        
        batch_out_layout = QHBoxLayout()
        self.output_folder_btn = styled_button("Output Folder")
        self.output_folder_btn.clicked.connect(self.select_output_folder)
        self.output_folder_label = QLabel(os.path.join(self.input_folder_path, "output"))
        self.output_folder_label.setWordWrap(True)
        self.output_folder_label.setStyleSheet("background-color: #2D2D30; color: #CCCCCC; padding: 4px; border-radius: 3px;")
        batch_out_layout.addWidget(self.output_folder_btn)
        batch_out_layout.addWidget(self.output_folder_label, stretch=1)
        batch_layout.addLayout(batch_out_layout)
        
        self.batch_render_btn = styled_button("Start Batch Render (Selected Files)", color="#2196F3", bold=True)
        self.batch_render_btn.clicked.connect(lambda: self.start_export(batch=True))
        batch_layout.addWidget(self.batch_render_btn)
        
        self.batch_progress_label = QLabel("File: N/A")
        self.batch_progress_bar = QProgressBar()
        self.batch_progress_bar.setFormat("Idle")
        batch_layout.addWidget(self.batch_progress_label)
        batch_layout.addWidget(self.batch_progress_bar)
        batch_group.setLayout(batch_layout)
        layout.addWidget(batch_group)
        layout.addStretch()
        
        scroll.setWidget(inner)
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)
        self.tab_widget.addTab(tab, "Export")

    # ----------------------------------------------------------------
    # FILE & FOLDER MANAGEMENT
    # ----------------------------------------------------------------
    def set_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Input Folder")
        if folder:
            self.input_folder_path = folder
            self.input_folder_label.setText(folder)
            # Default output folder to input/output
            out_dir = os.path.join(folder, "output")
            os.makedirs(out_dir, exist_ok=True)
            self.output_folder_label.setText(out_dir)
            self.refresh_all_files()

    def refresh_all_files(self):
        self.refresh_code_files()
        self.refresh_audio_files()
        self.refresh_batch_files()

    def refresh_code_files(self):
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        files = glob.glob(os.path.join(self.input_folder_path, "*.scd")) + glob.glob(os.path.join(self.input_folder_path, "*.txt"))
        if not files:
            self.file_combo.addItem("No files found")
        else:
            for f in files:
                self.file_combo.addItem(os.path.basename(f), f)
        self.file_combo.blockSignals(False)
        if files: self.load_selected_file(0)

    def load_selected_file(self, index):
        if index < 0: return
        file_path = self.file_combo.itemData(index)
        if file_path and os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                self.code_input.setPlainText(f.read())
            self.current_code_file = file_path
            self.status_label.setText(f"Loaded: {os.path.basename(file_path)}")

    def create_new_file(self):
        name, ok = QInputDialog.getText(self, "New File", "File name (e.g., synth.scd):")
        if ok and name:
            if not name.endswith('.scd') and not name.endswith('.txt'):
                name += '.scd'
            file_path = os.path.join(self.input_folder_path, name)
            if os.path.exists(file_path):
                QMessageBox.warning(self, "Exists", "File already exists.")
                return
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('"// New File"\n')
            self.refresh_code_files()
            idx = self.file_combo.findData(file_path)
            if idx >= 0: self.file_combo.setCurrentIndex(idx)

    def save_current_file(self):
        if not self.current_code_file:
            self.create_new_file()
            return
        with open(self.current_code_file, 'w', encoding='utf-8') as f:
            f.write(self.code_input.toPlainText())
        self.status_label.setText(f"Saved: {os.path.basename(self.current_code_file)}")

    def delete_current_file(self):
        if not self.current_code_file: return
        reply = QMessageBox.question(self, "Delete", f"Delete {os.path.basename(self.current_code_file)}?")
        if reply == QMessageBox.Yes:
            os.remove(self.current_code_file)
            self.current_code_file = None
            self.code_input.clear()
            self.refresh_code_files()

    def refresh_audio_files(self):
        self.audio_list_widget.clear()
        files = glob.glob(os.path.join(self.input_folder_path, "*.wav")) + \
                glob.glob(os.path.join(self.input_folder_path, "*.mp3")) + \
                glob.glob(os.path.join(self.input_folder_path, "*.aiff")) + \
                glob.glob(os.path.join(self.input_folder_path, "*.flac"))
        for f in files:
            item = QListWidgetItem(os.path.basename(f))
            item.setToolTip(f)
            item.setData(Qt.UserRole, f)
            item.setCheckState(Qt.Unchecked)
            self.audio_list_widget.addItem(item)

    def get_selected_audio_files(self):
        files = []
        for i in range(self.audio_list_widget.count()):
            item = self.audio_list_widget.item(i)
            if item.checkState() == Qt.Checked:
                files.append(item.data(Qt.UserRole))
        return files

    def refresh_batch_files(self):
        self.batch_list_widget.clear()
        files = glob.glob(os.path.join(self.input_folder_path, "*.scd")) + glob.glob(os.path.join(self.input_folder_path, "*.txt"))
        for f in files:
            item = QListWidgetItem(os.path.basename(f))
            item.setToolTip(f)
            item.setData(Qt.UserRole, f)
            self.batch_list_widget.addItem(item)

    def select_all_batch_files(self):
        self.batch_list_widget.clearSelection()
        for i in range(self.batch_list_widget.count()):
            item = self.batch_list_widget.item(i)
            item.setSelected(True)

    def clear_batch_selection(self):
        self.batch_list_widget.clearSelection()

    # ----------------------------------------------------------------
    # STATUS / EVENTS
    # ----------------------------------------------------------------
    def _check_sc_status(self):
        if self.sc_manager.process and self.sc_manager.process.poll() is None:
            self.sc_status_label.setText("sclang: running")
            self.sc_status_label.setStyleSheet("color: #4CAF50; padding: 0 8px;")
        else:
            self.sc_status_label.setText("sclang: not running")
            self.sc_status_label.setStyleSheet("color: #F44336; padding: 0 8px;")

    def closeEvent(self, event):
        log.info("Closing application, stopping SuperCollider process...")
        if self.export_thread and self.export_thread.isRunning():
            self.export_worker.stop()
            self.export_thread.quit()
            self.export_thread.wait(2000)
        self.sc_manager.stop()
        event.accept()

    def animator_theme_changed(self, text):
        self.animator.set_theme(text)
        self.highlighter.update_theme(text)

    def animator_font_changed(self):
        self.animator.set_font(self.font_combo.currentText(), self.size_spin.value())

    def update_animator_fps(self):
        self.animator.fps = self.get_fps()

    def load_code(self):
        typo = self.mode_combo.currentText() == "Typo Simulation"
        code = self.code_input.toPlainText()
        self.animator.set_code(code, typo_mode=typo, post_msg=self.post_input.text())
        self.progress_bar.setValue(0)
        self.status_label.setText("Code loaded to animator")

    def play_animation(self):
        self.save_current_file()  # Auto-save on preview
        self.load_code()
        self.next_char_delay()
        self.status_label.setText("Previewing animation...")

    def next_char_delay(self):
        mode = self.mode_combo.currentText()
        base_speed = self.speed_slider.value()
        if mode == "Constant Speed": interval = 1000 // base_speed
        elif mode == "Human (Random)": interval = random.randint(1000 // base_speed, (1000 // base_speed) * 3)
        elif mode == "Punctuation Delay":
            if self.animator.current_chars > 0:
                last_char = self.animator.target_code[self.animator.current_chars - 1]
                interval = 400 if last_char in ".,;({[" else 1000 // base_speed
            else: interval = 1000 // base_speed
        elif mode == "Typo Simulation":
            interval = 150 if self.animator.in_typo else random.randint(1000 // base_speed, (1000 // base_speed) * 2)
        else: interval = 50
        self.type_timer.start(interval)

    def type_step(self):
        code = self.code_input.toPlainText()
        if self.animator.current_chars < len(code):
            self.animator.display_string = code[:self.animator.current_chars + 1]
            self.animator.current_chars += 1
            self.animator.update()
            self.progress_bar.setValue(int((self.animator.current_chars / len(code)) * 100))
            self.next_char_delay()
        else:
            self.type_timer.stop()
            self.status_label.setText("Preview complete")

    def test_theme_cycle(self):
        self.test_themes_btn.setEnabled(False)
        self.theme_test_index = 0
        self.theme_test_timer.timeout.connect(self._theme_cycle_step)
        self.theme_test_timer.start(1000)

    def _theme_cycle_step(self):
        if self.theme_test_index >= len(THEMES) * 2:
            self.theme_test_timer.stop()
            self.test_themes_btn.setEnabled(True)
            self.status_label.setText("Theme test complete")
            return
        idx = self.theme_test_index % len(THEMES)
        self.theme_combo.setCurrentIndex(idx)
        self.theme_test_index += 1

    def test_exec_state(self):
        self.test_exec_btn.setEnabled(False)
        self.animator.set_code(self.code_input.toPlainText(), post_msg=self.post_input.text())
        self.animator.display_string = self.code_input.toPlainText()
        self.animator.current_chars = len(self.animator.display_string)
        self.animator.executing = True
        self.animator.post_message = "*** Welcome to SuperCollider 3.14. ***\n-> a Synth"
        self.animator.post_chars = 0
        self.exec_test_step_count = 0
        self.exec_test_timer.timeout.connect(self._exec_state_step)
        self.exec_test_timer.start(50)

    def _exec_state_step(self):
        self.exec_test_step_count += 1
        self.animator.frame_index += 1
        if self.animator.post_chars < len(self.animator.post_message):
            self.animator.post_chars += 1
        self.animator.update()
        if self.exec_test_step_count > 100:
            self.exec_test_timer.stop()
            self.test_exec_btn.setEnabled(True)
            self.animator.executing = False
            self.load_code()
            self.status_label.setText("Execution state test complete")

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_folder_label.setText(folder)

    def get_export_geometry(self):
        res_text = self.res_combo.currentText()
        if "1280x720" in res_text: return 1280, 720
        if "1920x1080" in res_text: return 1920, 1080
        if "1080x1920" in res_text: return 1080, 1920
        return 800, 600

    def get_fps(self):
        fps_text = self.fps_combo.currentText()
        if "24" in fps_text: return 24
        if "60" in fps_text: return 60
        return 30

    def check_installed(self, exe_name):
        if not shutil.which(exe_name):
            QMessageBox.warning(self, f"{exe_name} Not Found", f"{exe_name} not found in PATH.")
            return False
        return True

    def merge_audio_video(self, video_path, sc_audio_path, output_path, normalize=False):
        if not self.check_installed('ffmpeg'): return False
        try:
            cmd = ['ffmpeg', '-y', '-i', video_path]
            if sc_audio_path:
                cmd.extend(['-i', sc_audio_path, '-map', '0:v', '-map', '1:a'])
                if normalize: cmd.extend(['-af', 'loudnorm=I=-16:TP=-1.5:LRA=11'])
            else:
                cmd.extend(['-map', '0:v'])
            cmd.extend(['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest'])
            cmd.append(output_path)
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0: raise Exception(f"FFmpeg error: {result.stderr}")
            return True
        except Exception as e:
            raise Exception(f"Merge failed: {str(e)}")

    def test_audio_capture(self):
        if not self.check_installed('sclang'): return
        code = self.code_input.toPlainText()
        if not code.strip():
            QMessageBox.warning(self, "Empty Code", "Please enter some SuperCollider code to test.")
            return
        self.save_current_file()
        self.test_audio_btn.setEnabled(False)
        self.test_audio_btn.setText("Capturing...")
        self.status_label.setText("Starting audio capture test...")
        self.audio_test_thread = QThread()
        self.audio_test_worker = AudioTestWorker(self.sc_manager, code, input_files=self.get_selected_audio_files())
        self.audio_test_worker.moveToThread(self.audio_test_thread)
        self.audio_test_thread.started.connect(self.audio_test_worker.run_test)
        self.audio_test_worker.progress.connect(self.on_audio_test_progress)
        self.audio_test_worker.finished.connect(self.on_audio_test_finished)
        self.audio_test_worker.error.connect(self.on_audio_test_error)
        self.audio_test_worker.finished.connect(self.audio_test_thread.quit)
        self.audio_test_worker.error.connect(self.audio_test_thread.quit)
        self.audio_test_thread.start()

    def on_audio_test_progress(self, msg):
        self.status_label.setText(msg)
        self.test_audio_btn.setText(msg)

    def on_audio_test_finished(self, audio_path):
        self.test_audio_btn.setEnabled(True)
        self.test_audio_btn.setText("Test Audio Capture")
        self.status_label.setText("Audio test complete — playing...")
        if audio_path and os.path.exists(audio_path):
            if sys.platform == "win32": os.startfile(audio_path)
            elif sys.platform == "darwin": subprocess.run(['open', audio_path])
            else: subprocess.run(['xdg-open', audio_path])

    def on_audio_test_error(self, err_msg):
        self.test_audio_btn.setEnabled(True)
        self.test_audio_btn.setText("Test Audio Capture")
        self.status_label.setText("Audio test failed")
        QMessageBox.critical(self, "Audio Test Error", err_msg)

    def test_live_execution(self):
        if not self.check_installed('sclang'): return
        code = self.code_input.toPlainText()
        if not code.strip():
            QMessageBox.warning(self, "Empty Code", "Please enter some SuperCollider code to test.")
            return
        self.save_current_file()
        self.test_live_btn.setEnabled(False)
        self.test_live_btn.setText("Executing...")
        self.status_label.setText("Starting live execution test...")
        self.live_test_thread = QThread()
        self.live_test_worker = LiveCodeWorker(self.sc_manager, code)
        self.live_test_worker.moveToThread(self.live_test_thread)
        self.live_test_thread.started.connect(self.live_test_worker.run_test)
        self.live_test_worker.progress.connect(self.on_live_test_progress)
        self.live_test_worker.finished.connect(self.on_live_test_finished)
        self.live_test_worker.error.connect(self.on_live_test_error)
        self.live_test_worker.finished.connect(self.live_test_thread.quit)
        self.live_test_worker.error.connect(self.live_test_thread.quit)
        self.live_test_thread.start()

    def on_live_test_progress(self, msg):
        self.status_label.setText(msg)
        self.test_live_btn.setText(msg)

    def on_live_test_finished(self):
        self.test_live_btn.setEnabled(True)
        self.test_live_btn.setText("Test Live Execution")
        self.status_label.setText("Live execution test complete.")

    def on_live_test_error(self, err_msg):
        self.test_live_btn.setEnabled(True)
        self.test_live_btn.setText("Test Live Execution")
        self.status_label.setText("Live execution test failed")
        QMessageBox.critical(self, "Live Test Error", err_msg)

    def test_video_export(self):
        if not self.check_installed('ffmpeg'): return
        self.test_video_btn.setEnabled(False)
        self.test_video_btn.setText("Testing Pipeline...")
        self.status_label.setText("Running short video export test...")
        test_code = '"// Pipeline Test"\nSynth(\\sine, [\\freq, 440, \\amp, 0.4]);'
        base_temp_dir = os.path.join(os.getcwd(), "sc_temp")
        os.makedirs(base_temp_dir, exist_ok=True)
        test_output_path = os.path.abspath(os.path.join(base_temp_dir, "pipeline_test.mp4"))
        files_data = [(test_code, test_output_path)]
        self.tab_widget.setCurrentWidget(self.tab_widget.widget(4))
        self.export_btn.setEnabled(False)
        self.batch_render_btn.setEnabled(False)
        self.cancel_export_btn.setVisible(True)
        w, h = self.get_export_geometry()
        self.animator.setFixedSize(w, h)
        self.export_thread = QThread()
        self.export_worker = ExportWorker(self, files_data, input_files=self.get_selected_audio_files())
        self.export_worker.moveToThread(self.export_thread)
        self.export_thread.started.connect(self.export_worker.run_export)
        self.export_worker.request_frame.connect(self.grab_frame)
        self.export_worker.progress_update.connect(self.update_export_progress)
        self.export_worker.finished.connect(lambda: self.on_test_video_finished(test_output_path))
        self.export_worker.error.connect(self.on_test_video_error)
        self.export_worker.finished.connect(self.export_thread.quit)
        self.export_worker.error.connect(self.export_thread.quit)
        self.export_thread.start()

    def on_test_video_finished(self, file_path):
        self.animator.setMinimumSize(800, 600)
        self.animator.setMaximumSize(16777215, 16777215)
        self.export_btn.setEnabled(True)
        self.batch_render_btn.setEnabled(True)
        self.test_video_btn.setEnabled(True)
        self.test_video_btn.setText("Test Video Export (Short MP4)")
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("Test Complete")
        self.status_label.setText("Video pipeline test complete — playing...")
        self.cancel_export_btn.setVisible(False)
        self.load_code()
        if os.path.exists(file_path):
            if sys.platform == "win32": os.startfile(file_path)
            elif sys.platform == "darwin": subprocess.run(['open', file_path])
            else: subprocess.run(['xdg-open', file_path])

    def on_test_video_error(self, err_msg):
        self.animator.setMinimumSize(800, 600)
        self.animator.setMaximumSize(16777215, 16777215)
        self.export_btn.setEnabled(True)
        self.batch_render_btn.setEnabled(True)
        self.test_video_btn.setEnabled(True)
        self.test_video_btn.setText("Test Video Export (Short MP4)")
        self.progress_bar.setFormat("Test Failed")
        self.status_label.setText("Video pipeline test failed")
        self.cancel_export_btn.setVisible(False)
        QMessageBox.critical(self, "Pipeline Test Error", err_msg)

    def start_export(self, batch=False):
        self.save_current_file()
        files_data = []
        if batch:
            out_folder = self.output_folder_label.text()
            if out_folder == "None":
                QMessageBox.warning(self, "Folder Missing", "Please select an output folder.")
                return
            selected_items = self.batch_list_widget.selectedItems()
            if not selected_items:
                QMessageBox.warning(self, "No Files", "Please select at least one file to batch render.")
                return
            for item in selected_items:
                f = item.data(Qt.UserRole)
                with open(f, 'r', encoding='utf-8') as file:
                    code = file.read()
                out_path = os.path.join(out_folder, os.path.splitext(os.path.basename(f))[0] + ".mp4")
                files_data.append((code, out_path))
            self.batch_progress_bar.setMaximum(len(files_data))
        else:
            file_path, _ = QFileDialog.getSaveFileName(self, "Save Video", "sc_animation.mp4", "MP4 Files (*.mp4)")
            if not file_path: return
            files_data.append((self.code_input.toPlainText(), file_path))

        self.tab_widget.setCurrentWidget(self.tab_widget.widget(4))
        self.export_btn.setEnabled(False)
        self.batch_render_btn.setEnabled(False)
        self.cancel_export_btn.setVisible(True)
        w, h = self.get_export_geometry()
        self.animator.setFixedSize(w, h)
        self.export_thread = QThread()
        self.export_worker = ExportWorker(self, files_data, input_files=self.get_selected_audio_files())
        self.export_worker.moveToThread(self.export_thread)
        self.export_thread.started.connect(self.export_worker.run_export)
        self.export_worker.request_frame.connect(self.grab_frame)
        self.export_worker.progress_update.connect(self.update_export_progress)
        self.export_worker.finished.connect(self.on_export_finished)
        self.export_worker.error.connect(self.on_export_error)
        self.export_worker.finished.connect(self.export_thread.quit)
        self.export_worker.error.connect(self.export_thread.quit)
        self.export_thread.start()
        self.status_label.setText(f"Exporting {len(files_data)} file(s)...")

    def cancel_export(self):
        if self.export_worker and self.export_worker.is_running:
            self.export_worker.stop()
            self.status_label.setText("Cancelling export...")

    @Slot(dict)
    def grab_frame(self, state):
        self.animator.display_string = state['display_string']
        self.animator.current_chars = state['current_chars']
        self.animator.executing = state['executing']
        self.animator.post_message = state['post_message']
        self.animator.post_chars = state['post_chars']
        self.animator.frame_index = state['frame_index']
        self.animator.cursor_visible = state['cursor_visible']
        self.animator.repaint()
        pixmap = self.animator.grab()
        qimage = pixmap.toImage().convertToFormat(QImage.Format_RGBA8888)
        ptr = qimage.bits()
        ptr.setsize(qimage.byteCount())
        arr = np.frombuffer(ptr, dtype=np.uint8).copy()
        w, h = state['w'], state['h']
        bytes_per_line = qimage.bytesPerLine()
        if bytes_per_line != w * 4:
            arr = arr.reshape((h, bytes_per_line // 4, 4))
            arr = arr[:, :w, :]
        else:
            arr = arr.reshape((h, w, 4))
        arr_bgr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
        self.export_worker.receive_frame(arr_bgr)

    @Slot(int, int, str)
    def update_export_progress(self, file_idx, val, text):
        if file_idx == 0 and len(self.export_worker.files_data) == 1:
            if val >= 0: self.progress_bar.setValue(val)
            self.progress_bar.setFormat(text)
        else:
            self.batch_progress_bar.setValue(file_idx)
            self.batch_progress_label.setText(f"File {file_idx + 1}/{len(self.export_worker.files_data)}: {text}")
        self.status_label.setText(text)

    @Slot()
    def on_export_finished(self):
        self.animator.setMinimumSize(800, 600)
        self.animator.setMaximumSize(16777215, 16777215)
        self.export_btn.setEnabled(True)
        self.batch_render_btn.setEnabled(True)
        self.cancel_export_btn.setVisible(False)
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("Complete")
        self.batch_progress_label.setText("Batch Complete!")
        self.status_label.setText("Export finished successfully")
        self.load_code()
        QMessageBox.information(self, "Success", "Export process completed successfully!")

    @Slot(str)
    def on_export_error(self, err_msg):
        self.animator.setMinimumSize(800, 600)
        self.animator.setMaximumSize(16777215, 16777215)
        self.export_btn.setEnabled(True)
        self.batch_render_btn.setEnabled(True)
        self.cancel_export_btn.setVisible(False)
        self.progress_bar.setFormat("Failed")
        self.batch_progress_label.setText("Failed!")
        self.status_label.setText("Export failed")
        QMessageBox.critical(self, "Export Error", err_msg)

if __name__ == "__main__":
    log.info("Application launching (entry point)")
    try:
        app = QApplication(sys.argv)
        app.setStyleSheet("""
            QMainWindow { background-color: #1E1E1E; }
            QTabWidget::pane { border: 1px solid #3C3C3C; background: #252526; border-radius: 3px; }
            QTabBar::tab { background: #2D2D30; color: #969696; padding: 8px 14px; border: 1px solid #3C3C3C; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; }
            QTabBar::tab:selected { background: #007ACC; color: white; font-weight: bold; }
            QTabBar::tab:hover:!selected { background: #3E3E42; color: #CCCCCC; }
            QGroupBox { color: #CCCCCC; border: 1px solid #3C3C3C; border-radius: 4px; margin-top: 10px; padding-top: 10px; font-weight: bold; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QLabel { color: #D4D4D4; }
            QPushButton { background-color: #3A3D41; color: white; border: 1px solid #4A4D51; padding: 6px 12px; border-radius: 3px; }
            QPushButton:hover { background-color: #4A4D51; }
            QPushButton:pressed { background-color: #2D2F31; }
            QPushButton:disabled { background-color: #2D2D30; color: #707070; }
            QComboBox, QSpinBox, QLineEdit, QTextEdit { background-color: #2D2D30; color: #D4D4D4; border: 1px solid #3C3C3C; padding: 4px; border-radius: 3px; }
            QComboBox:hover, QSpinBox:hover, QLineEdit:hover, QTextEdit:hover { border: 1px solid #007ACC; }
            QComboBox QAbstractItemView { background-color: #2D2D30; color: #D4D4D4; selection-background-color: #007ACC; border: 1px solid #3C3C3C; }
            QCheckBox { color: #D4D4D4; }
            QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #4A4D51; background-color: #2D2D30; border-radius: 2px; }
            QCheckBox::indicator:checked { background-color: #007ACC; border: 1px solid #007ACC; }
            QProgressBar { background-color: #2D2D30; border: 1px solid #3C3C3C; border-radius: 3px; text-align: center; color: white; }
            QProgressBar::chunk { background-color: #007ACC; border-radius: 2px; }
            QSlider::groove:horizontal { height: 6px; background: #2D2D30; border-radius: 3px; }
            QSlider::handle:horizontal { background: #007ACC; width: 16px; margin: -6px 0; border-radius: 8px; }
            QStatusBar { background-color: #007ACC; color: white; }
            QStatusBar QLabel { color: white; }
            QScrollBar:vertical { background: #2D2D30; width: 10px; margin: 0; }
            QScrollBar::handle:vertical { background: #4A4D51; min-height: 20px; border-radius: 5px; }
            QScrollBar::handle:vertical:hover { background: #5A5D61; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QListWidget { background-color: #1E1E1E; color: #D4D4D4; border: 1px solid #3C3C3C; border-radius: 3px; }
            QListWidget::item:selected { background-color: #007ACC; color: white; }
        """)
        window = MainWindow()
        window.show()
        exit_code = app.exec()
        log.info("Application exited with code %d", exit_code)
        sys.exit(exit_code)
    except Exception as e:
        log.exception("Fatal error in main: %s", e)
        raise