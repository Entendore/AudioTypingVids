import sys
import os
import subprocess
import tempfile
import shutil
import logging
import time
from enum import Enum, auto
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLabel, QMessageBox, QProgressBar, QComboBox
)
from PySide6.QtCore import QThread, QObject, Signal, Slot

# --- Logging Setup ---
LOG_FILE = os.path.join(os.getcwd(), "nrt_test.log")

def setup_logging():
    logger = logging.getLogger("NRTTester")
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

# --- State Machine Definition ---
class ProcessState(Enum):
    IDLE = auto()
    CHECKING_DEPS = auto()
    PREPARING_SCRIPT = auto()
    COMPILING_SCORE = auto()
    RENDERING_AUDIO = auto()
    VALIDATING_OUTPUT = auto()
    CLEANUP = auto()
    COMPLETE = auto()
    ERROR = auto()

# --- Built-in NRT Test Scripts ---
# We manually write the binary OSC file with 4-byte big-endian size prefixes.
# This avoids any potential hangs from the `Score` class and bypasses the need for `0.exit`.
NRT_TESTS = {
    "1. Simple Sine Wave (3 sec)": """// NRT Test: Simple Sine Wave
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
""",
    "2. Major Chord (3 sec)": """// NRT Test: Major Chord (C-E-G)
(
var def = SynthDef(\\nrt_chord, { arg out=0, freq=440;
    var sig = SinOsc.ar(freq) * 0.15 * EnvGen.ar(Env.linen(0.5, 2.0, 0.5), doneAction: 2);
    Out.ar(out, sig ! 2);
}).asBytes;

var bundles = [
    [0.0, [\\d_recv, def]],
    [0.01, [\\s_new, \\nrt_chord, 1001, 0, 0, \\freq, 261.63]], // C4
    [0.01, [\\s_new, \\nrt_chord, 1002, 0, 0, \\freq, 329.63]], // E4
    [0.01, [\\s_new, \\nrt_chord, 1003, 0, 0, \\freq, 392.00]], // G4
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
""",
    "3. Frequency Sweep (5 sec)": """// NRT Test: Frequency Sweep
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
""",
    "4. FM Synthesis Bell (4 sec)": """// NRT Test: FM Synthesis Bell
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
""",
    "5. Stereo Pan Sweep (5 sec)": """// NRT Test: Stereo Pan Sweep
(
var def = SynthDef(\\nrt_pan, { arg out=0, freq=220;
    var sig = Saw.ar(freq) * 0.2;
    var pan = Line.kr(-1, 1, 4.8, doneAction: 2);
    Out.ar(out, Pan2.ar(sig, pan));
}).asBytes;

var bundles = [
    [0.0, [\\d_recv, def]],
    [0.01, [\\s_new, \\nrt_pan, 1001, 0, 0, \\freq, 220]],
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
""",
    "6. Arpeggiated Sequence (4 sec)": """// NRT Test: Arpeggiated Sequence
(
var def = SynthDef(\\nrt_seq, { arg out=0, freq=440;
    var sig = Pulse.ar(freq) * 0.2 * EnvGen.ar(Env.perc(0.01, 0.3), doneAction: 2);
    Out.ar(out, sig ! 2);
}).asBytes;

var notes = [60, 64, 67, 72, 67, 64].midicps;
var noteBundles = notes.collect({ |freq, i|
    [0.1 + (i * 0.5), [\\s_new, \\nrt_seq, 1001 + i, 0, 0, \\freq, freq]]
});

var bundles = [[0.0, [\\d_recv, def]]] ++ noteBundles ++ [
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
""",
    "7. Filtered Noise Sweep (4 sec)": """// NRT Test: Filtered Noise Sweep
(
var def = SynthDef(\\nrt_noise, { arg out=0;
    var sig = WhiteNoise.ar(0.5);
    var freq = XLine.kr(100, 8000, 4);
    sig = LPF.ar(sig, freq);
    sig = sig * EnvGen.ar(Env.linen(0.1, 3.8, 0.1), doneAction: 2);
    Out.ar(out, sig ! 2);
}).asBytes;

var bundles = [
    [0.0, [\\d_recv, def]],
    [0.01, [\\s_new, \\nrt_noise, 1001, 0, 0]],
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

class NRTWorker(QObject):
    log = Signal(str)
    progress = Signal(int, str)
    finished = Signal(str)
    error = Signal(str)
    state_changed = Signal(str)

    def __init__(self, sc_code):
        super().__init__()
        self.sc_code = sc_code
        self.temp_dir = tempfile.mkdtemp(prefix="sc_nrt_test_")
        self.wav_path = ""
        self.current_state = ProcessState.IDLE

    def transition_to(self, new_state, message="", progress_val=-1):
        self.current_state = new_state
        state_name = new_state.name
        log.info(f"STATE TRANSITION: -> {state_name}. {message}")
        self.state_changed.emit(state_name)
        
        if message:
            self.log.emit(f"[{state_name}] {message}")
        if progress_val >= 0:
            self.progress.emit(progress_val, message if message else state_name)

    def cleanup_temp_files(self):
        """Deletes the temporary directory to prevent disk space bloat."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                log.info(f"Cleaned up temp directory: {self.temp_dir}")
            except Exception as e:
                log.warning(f"Failed to clean up temp directory: {e}")

    @Slot()
    def run_test(self):
        try:
            # STATE: CHECKING_DEPS
            self.transition_to(ProcessState.CHECKING_DEPS, "Checking dependencies...", 10)
            sclang_path = shutil.which('sclang')
            scsynth_path = shutil.which('scsynth')
            if not sclang_path or not scsynth_path:
                raise Exception("Could not find 'sclang' or 'scsynth' in system PATH.")

            # STATE: PREPARING_SCRIPT
            self.transition_to(ProcessState.PREPARING_SCRIPT, "Preparing SC script...", 20)
            score_path = os.path.join(self.temp_dir, "score.osc").replace('\\', '/')
            self.wav_path = os.path.join(self.temp_dir, "nrt_output.wav").replace('\\', '/')
            final_sc_code = self.sc_code.replace("__SCORE_PATH__", score_path)
            script_path = os.path.join(self.temp_dir, "gen_score.scd")
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(final_sc_code)

            # STATE: COMPILING_SCORE
            self.transition_to(ProcessState.COMPILING_SCORE, "Running sclang to compile OSC score...", 30)
            process = subprocess.Popen(
                [sclang_path, '-D', script_path],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                text=True, encoding='utf-8', errors='replace'
            )
            output_lines = []
            success = False
            start_time = time.time()
            while True:
                if time.time() - start_time > 30:
                    process.kill()
                    process.wait()
                    raise Exception("sclang timed out after 30 seconds.")
                line = process.stdout.readline()
                if not line:
                    if process.poll() is not None: break
                    time.sleep(0.1); continue
                output_lines.append(line)
                log.debug(f"sclang: {line.strip()}")
                if "SCORE_WRITTEN" in line:
                    success = True
                    # Give it a moment to finish writing the file
                    time.sleep(0.5)
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    break
            
            if not success:
                full_output = "".join(output_lines)
                raise Exception(f"sclang failed to write score.\nOutput:\n{full_output}")

            # STATE: RENDERING_AUDIO
            self.transition_to(ProcessState.RENDERING_AUDIO, "Running scsynth -N (NRT)...", 50)
            cmd = [scsynth_path, '-o', '2', '-N', score_path, '_', self.wav_path, '44100', 'WAV', 'int16']
            nrt_result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                text=True, encoding='utf-8', errors='replace', timeout=30
            )
            nrt_output = nrt_result.stdout + "\n" + nrt_result.stderr
            log.debug(f"scsynth output:\n{nrt_output}")
            if nrt_result.returncode != 0 and not os.path.exists(self.wav_path):
                raise Exception(f"scsynth failed.\nOutput:\n{nrt_output}")

            # STATE: VALIDATING_OUTPUT
            self.transition_to(ProcessState.VALIDATING_OUTPUT, "Validating WAV file...", 90)
            if not os.path.exists(self.wav_path):
                raise Exception("scsynth finished but did not generate the WAV file.")
            
            file_size = os.path.getsize(self.wav_path)
            if file_size < 1024:
                raise Exception(f"Generated WAV file is invalid or empty (Size: {file_size} bytes).")

            # Copy WAV to a permanent location before temp is deleted
            permanent_wav = os.path.join(os.getcwd(), "nrt_output.wav")
            shutil.copy2(self.wav_path, permanent_wav)
            log.info(f"Copied final WAV to: {permanent_wav}")

            # STATE: COMPLETE
            self.transition_to(ProcessState.COMPLETE, "Complete!", 100)
            self.finished.emit(permanent_wav)

        except subprocess.TimeoutExpired:
            self.transition_to(ProcessState.ERROR, "Process timed out.", 0)
            self.error.emit("A process (sclang or scsynth) timed out.")
        except Exception as e:
            self.transition_to(ProcessState.ERROR, str(e), 0)
            log.exception("NRT Test failed with exception:")
            self.error.emit(str(e))
        finally:
            # STATE: CLEANUP - Always run this, even if it fails
            self.transition_to(ProcessState.CLEANUP, "Cleaning up temporary files...", -1)
            self.cleanup_temp_files()

class NRTTestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SuperCollider NRT Tester (Robust Edition)")
        self.resize(800, 650)
        log.info("Application UI initializing...")
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # Test Selector
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Select Built-in Test:"))
        self.test_combo = QComboBox()
        self.test_combo.addItems(NRT_TESTS.keys())
        self.test_combo.currentTextChanged.connect(self.load_selected_test)
        selector_layout.addWidget(self.test_combo, stretch=1)
        layout.addLayout(selector_layout)
        
        # State Machine Indicator
        state_layout = QHBoxLayout()
        state_layout.addWidget(QLabel("Current State:"))
        self.state_label = QLabel("IDLE")
        self.state_label.setStyleSheet("font-weight: bold; color: #007ACC; padding: 2px;")
        state_layout.addWidget(self.state_label, stretch=1)
        layout.addLayout(state_layout)
        
        # Code Viewer
        layout.addWidget(QLabel("SuperCollider NRT Code:"))
        self.code_edit = QTextEdit()
        self.code_edit.setReadOnly(True)
        self.code_edit.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4; font-family: Consolas; font-size: 14px;")
        layout.addWidget(self.code_edit, stretch=1)
        
        # Run Controls
        run_layout = QHBoxLayout()
        self.run_btn = QPushButton("Run NRT Audio Test")
        self.run_btn.setStyleSheet("background-color: #007ACC; color: white; font-weight: bold; padding: 10px; font-size: 14px;")
        self.run_btn.clicked.connect(self.start_test)
        run_layout.addWidget(self.run_btn)
        layout.addLayout(run_layout)
        
        # Progress Bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Idle")
        self.progress.setTextVisible(True)
        self.progress.setFixedHeight(25)
        layout.addWidget(self.progress)
        
        # Log Console Header & Clear Button
        log_header_layout = QHBoxLayout()
        log_header_layout.addWidget(QLabel("Console Log:"))
        log_header_layout.addStretch()
        self.clear_log_btn = QPushButton("Clear Log")
        self.clear_log_btn.setStyleSheet("padding: 2px 8px;")
        self.clear_log_btn.clicked.connect(self.log_edit.clear if hasattr(self, 'log_edit') else lambda: None)
        log_header_layout.addWidget(self.clear_log_btn)
        layout.addLayout(log_header_layout)
        
        # Log Console
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(150)
        self.log_edit.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4; font-family: Consolas;")
        layout.addWidget(self.log_edit)
        
        # Connect the clear button now that log_edit exists
        self.clear_log_btn.clicked.connect(self.log_edit.clear)
        
        self.worker_thread = None
        self.worker = None
        self.load_selected_test(self.test_combo.currentText())

    def load_selected_test(self, test_name):
        code = NRT_TESTS.get(test_name, "")
        self.code_edit.setPlainText(code)
        log.info(f"Loaded test: {test_name}")

    def start_test(self):
        self.run_btn.setEnabled(False)
        self.test_combo.setEnabled(False) # Prevent changing test mid-render
        self.progress.setValue(0)
        self.progress.setFormat("Starting...")
        self.state_label.setText("STARTING")
        self.state_label.setStyleSheet("font-weight: bold; color: #007ACC; padding: 2px;")
        self.log_edit.clear()
        self.log("Starting NRT test...")
        log.info("Start button clicked by user.")
        
        sc_code = self.code_edit.toPlainText()
        
        self.worker_thread = QThread()
        self.worker = NRTWorker(sc_code)
        self.worker.moveToThread(self.worker_thread)
        
        self.worker_thread.started.connect(self.worker.run_test)
        self.worker.log.connect(self.log)
        self.worker.progress.connect(self.update_progress)
        self.worker.state_changed.connect(self.update_state)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.error.connect(self.worker_thread.quit)
        
        self.worker_thread.start()

    @Slot(str)
    def update_state(self, state_name):
        self.state_label.setText(state_name)
        if state_name == "ERROR":
            self.state_label.setStyleSheet("font-weight: bold; color: #F44336; padding: 2px;")
        elif state_name == "COMPLETE":
            self.state_label.setStyleSheet("font-weight: bold; color: #4CAF50; padding: 2px;")
        else:
            self.state_label.setStyleSheet("font-weight: bold; color: #007ACC; padding: 2px;")

    @Slot(int, str)
    def update_progress(self, val, text):
        self.progress.setValue(val)
        self.progress.setFormat(text)

    def log(self, message):
        self.log_edit.append(message)
        # Auto-scroll to bottom
        scrollbar = self.log_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def on_finished(self, wav_path):
        self.run_btn.setEnabled(True)
        self.test_combo.setEnabled(True)
        self.log("\nSUCCESS: The audio file was generated successfully using NRT mode!")
        self.log(f"Saved to: {wav_path}")
        log.info("Test finished successfully.")
        
        reply = QMessageBox.information(self, "Test Passed", "NRT Audio rendering passed! Would you like to play the audio file?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            log.info("User chose to play the audio file.")
            if sys.platform == "win32": os.startfile(wav_path)
            elif sys.platform == "darwin": subprocess.run(['open', wav_path])
            else: subprocess.run(['xdg-open', wav_path])

    def on_error(self, err_msg):
        self.run_btn.setEnabled(True)
        self.test_combo.setEnabled(True)
        self.progress.setValue(0)
        self.progress.setFormat("Failed")
        self.log(f"\nERROR: {err_msg}")
        log.error(f"Test failed: {err_msg}")
        QMessageBox.critical(self, "Test Failed", f"An error occurred:\n{err_msg}")

if __name__ == "__main__":
    log.info("Application launching (entry point)")
    try:
        app = QApplication(sys.argv)
        window = NRTTestWindow()
        window.show()
        exit_code = app.exec()
        log.info("Application exited with code %d", exit_code)
        sys.exit(exit_code)
    except Exception as e:
        log.exception("Fatal error in main: %s", e)
        raise