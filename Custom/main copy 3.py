"""
SuperCollider NRT Visualizer (Enhanced UI, Layouts & Concurrent Pipeline)
================================================================
- Layout presets for YouTube Videos (16:9) and YouTube Shorts (9:16).
- Customizable typing animation styles, speeds, and audio visualizers.
- Typing animation duration matches the exact duration of the generated audio.
- Audio visuals render concurrently with the code typing animation.
- Audio Preview button to listen to the generated WAV.
- All logs and errors are routed exclusively to 'nrt_visualizer.log'.
- Resolution/Quality presets (720p, 1080p, 1440p, 4K).
- Encoding quality/bitrate presets (Standard, High, Maximum).
- Auto-scaling fonts and adaptive layout based on aspect ratio.
- Optional YouTube Shorts Safe-Zone overlay for previewing UI collision zones.
- Scrolling code animation: text clips horizontally (no wrapping) and scrolls up vertically.
- Customizable font family and base size for the code typing animation.
- Auto-fit font modes: Horizontal (no clip/scroll vert), Vertical (no scroll/clip horz), Directional (no clip/scroll).
- Multiple visual video themes (Midnight Blue, Pure Black, Synthwave, Matrix).
- Light/Dark UI themes for the application itself.
- Character Per Second (CPS) typing speed control with estimated time display (H:M:S).
- Advanced Audio Sync Behaviors: Loop/Cut, Stretch to Fill, Pause Tail, Trim, Independent.
- Robust __DURATION__ handling: Always replaces the placeholder so switching behaviors doesn't crash sclang.
- Live UI Preview: See the typing animation, layout, and theme loop instantly before rendering.
- Show Layout Bounds: Debug tool to draw colored boxes around all layout boundaries and text bounds.
- YouTube Compliant FFmpeg Output (48kHz Stereo Audio, High Profile H.264, Faststart).
- SYNTAX HIGHLIGHTING: Multiple themes for SuperCollider code (Dracula, Monokai, Solarized Light, etc.)
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
import re
from enum import Enum, auto
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QMessageBox, QProgressBar, QComboBox,
    QFileDialog, QSpinBox, QGroupBox, QLineEdit, QListWidget, QListWidgetItem,
    QFontComboBox
)
from PySide6.QtCore import (
    QThread, QObject, Signal, Slot, Qt, QRect, QRectF, QPointF, QSize, QSettings, QUrl, QTimer
)
from PySide6.QtGui import (
    QImage, QPainter, QColor, QFont, QPen, QBrush, QLinearGradient,
    QFontMetrics, QPixmap, QRadialGradient, QPalette,
    QTextLayout, QTextFormat, QTextCharFormat
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
import numpy as np

# ============================================================================
# Configuration & Logging
# ============================================================================
INPUT_FOLDER = os.path.join(os.getcwd(), "sc_input")
OUTPUT_FOLDER = os.path.join(os.getcwd(), "sc_output")
LOG_FILE = os.path.join(os.getcwd(), "nrt_visualizer.log")

# ----------------------------------------------------------------------------
# Layout / Quality configuration
# ----------------------------------------------------------------------------
QUALITY_PRESETS = {
    "720p (HD)":       (1280, 720),
    "1080p (Full HD)": (1920, 1080),
    "1440p (QHD)":     (2560, 1440),
    "4K (UHD)":        (3840, 2160),
}

BITRATE_PRESETS = {
    "Standard": {"crf": "23", "vbitrate": "6M",  "abitrate": "128k"},
    "High":     {"crf": "20", "vbitrate": "12M", "abitrate": "192k"},
    "Maximum":  {"crf": "18", "vbitrate": "24M", "abitrate": "256k"},
}

FPS_PRESETS = [24, 30, 60]

AUDIO_BEHAVIORS = [
    "Audio Matches Typing (Loop/Cut)",
    "Audio Matches Typing (SC Renders to Match)",
    "Typing Matches Audio (Stretch to Fill)",
    "Typing + Audio Tail (2s Pause)",
    "Trim Audio to Typing (No Loop)",
    "Independent (Use Longest, No Loop)",
]

AUDIO_TAIL_SEC = 2.0
AUDIO_FADE_OUT_SEC = 0.5

AUTOFIT_MODES = [
    "Off (Manual Size)",
    "Horizontal (No Horiz Overflow, Scroll Vert)",
    "Vertical (No Vert Scroll, Clip Horiz)",
    "Directional (No Clip/No Scroll)"
]

# Video Visual Themes
VIDEO_THEMES = {
    "Midnight Blue": {
        "bg_top": QColor(15, 18, 35), "bg_mid": QColor(10, 12, 25), "bg_bot": QColor(4, 5, 12),
        "accent1": QColor(0, 200, 255), "accent2": QColor(255, 100, 200),
        "code_text": QColor(0, 255, 150), "header_text": QColor(200, 220, 240),
        "time_text": QColor(0, 220, 255), "desc_text": QColor(255, 220, 130),
        "glow": QColor(0, 150, 255)
    },
    "Pure Black": {
        "bg_top": QColor(15, 15, 15), "bg_mid": QColor(5, 5, 5), "bg_bot": QColor(0, 0, 0),
        "accent1": QColor(255, 255, 255), "accent2": QColor(150, 150, 150),
        "code_text": QColor(255, 255, 255), "header_text": QColor(200, 200, 200),
        "time_text": QColor(255, 255, 255), "desc_text": QColor(200, 200, 200),
        "glow": QColor(80, 80, 80)
    },
    "Synthwave": {
        "bg_top": QColor(40, 10, 60), "bg_mid": QColor(20, 5, 40), "bg_bot": QColor(5, 0, 20),
        "accent1": QColor(255, 0, 150), "accent2": QColor(0, 255, 200),
        "code_text": QColor(0, 255, 200), "header_text": QColor(255, 100, 200),
        "time_text": QColor(255, 200, 0), "desc_text": QColor(255, 200, 0),
        "glow": QColor(255, 0, 150)
    },
    "Matrix": {
        "bg_top": QColor(0, 20, 0), "bg_mid": QColor(0, 10, 0), "bg_bot": QColor(0, 0, 0),
        "accent1": QColor(0, 255, 0), "accent2": QColor(0, 150, 0),
        "code_text": QColor(0, 255, 0), "header_text": QColor(0, 255, 0),
        "time_text": QColor(0, 255, 0), "desc_text": QColor(150, 255, 150),
        "glow": QColor(0, 255, 0)
    }
}

# ----------------------------------------------------------------------------
# SYNTAX HIGHLIGHTING THEMES
# ----------------------------------------------------------------------------
# Each theme maps token categories to QColor values.
# Categories: keyword, class, method, symbol, string, comment, number,
#             operator, envvar, default
# ----------------------------------------------------------------------------

def _rgb(hex_str):
    return QColor(hex_str)

SYNTAX_THEMES = {
    "Dracula": {
        "bg":          QColor(40, 42, 54),
        "keyword":     _rgb("#ff79c6"),
        "class":       _rgb("#8be9fd"),
        "method":      _rgb("#50fa7b"),
        "symbol":      _rgb("#ffb86c"),
        "string":      _rgb("#f1fa8c"),
        "comment":     _rgb("#6272a4"),
        "number":      _rgb("#bd93f9"),
        "operator":    _rgb("#ff79c6"),
        "envvar":      _rgb("#ffb86c"),
        "default":     _rgb("#f8f8f2"),
        "cursor":      _rgb("#ff79c6"),
    },
    "Monokai": {
        "bg":          QColor(39, 40, 34),
        "keyword":     _rgb("#f92672"),
        "class":       _rgb("#66d9ef"),
        "method":      _rgb("#a6e22e"),
        "symbol":      _rgb("#fd971f"),
        "string":      _rgb("#e6db74"),
        "comment":     _rgb("#75715e"),
        "number":      _rgb("#ae81ff"),
        "operator":    _rgb("#f92672"),
        "envvar":      _rgb("#fd971f"),
        "default":     _rgb("#f8f8f2"),
        "cursor":      _rgb("#f92672"),
    },
    "Solarized Light": {
        "bg":          QColor(253, 246, 227),
        "keyword":     _rgb("#859900"),
        "class":       _rgb("#268bd2"),
        "method":      _rgb("#2aa198"),
        "symbol":      _rgb("#b58900"),
        "string":      _rgb("#2aa198"),
        "comment":     _rgb("#93a1a1"),
        "number":      _rgb("#d33682"),
        "operator":    _rgb("#859900"),
        "envvar":      _rgb("#b58900"),
        "default":     _rgb("#586e75"),
        "cursor":      _rgb("#d33682"),
    },
    "GitHub Dark": {
        "bg":          QColor(13, 17, 23),
        "keyword":     _rgb("#ff7b72"),
        "class":       _rgb("#79c0ff"),
        "method":      _rgb("#d2a8ff"),
        "symbol":      _rgb("#ffa657"),
        "string":      _rgb("#a5d6ff"),
        "comment":     _rgb("#8b949e"),
        "number":      _rgb("#79c0ff"),
        "operator":    _rgb("#ff7b72"),
        "envvar":      _rgb("#ffa657"),
        "default":     _rgb("#c9d1d9"),
        "cursor":      _rgb("#58a6ff"),
    },
    "Gruvbox": {
        "bg":          QColor(40, 40, 40),
        "keyword":     _rgb("#fb4934"),
        "class":       _rgb("#fabd2f"),
        "method":      _rgb("#b8bb26"),
        "symbol":      _rgb("#fe8019"),
        "string":      _rgb("#b8bb26"),
        "comment":     _rgb("#928374"),
        "number":      _rgb("#d3869b"),
        "operator":    _rgb("#fb4934"),
        "envvar":      _rgb("#fe8019"),
        "default":     _rgb("#ebdbb2"),
        "cursor":      _rgb("#fb4934"),
    },
    "One Dark": {
        "bg":          QColor(40, 44, 52),
        "keyword":     _rgb("#c678dd"),
        "class":       _rgb("#56b6c2"),
        "method":      _rgb("#61afef"),
        "symbol":      _rgb("#d19a66"),
        "string":      _rgb("#98c379"),
        "comment":     _rgb("#5c6370"),
        "number":      _rgb("#d19a66"),
        "operator":    _rgb("#56b6c2"),
        "envvar":      _rgb("#e5c07b"),
        "default":     _rgb("#abb2bf"),
        "cursor":      _rgb("#c678dd"),
    },
}

# ----------------------------------------------------------------------------
# SuperCollider Tokenizer
# ----------------------------------------------------------------------------

# Order matters: comments/strings first to consume those ranges before
# individual tokens inside them are matched.
_SC_KEYWORDS = {
    "var", "arg", "const", "classvar", "this", "super", "true", "false", "nil",
    "if", "while", "for", "forBy", "loop", "case", "switch", "fork", "routine",
    "Task", "Routine", "Function", "Method", "Class", "Env", "Pseq", "Pbind",
    "Pwhite", "Pbrown", "Prand", "Pxrand", "Pfunc", "Pstream", "Pn", "Ppar",
    "Pspawner", "PSpawn", "Pfin", "Pfindur", "Pmono", "Pgroup", "Sym",
    "Synth", "SynthDef", "Group", "Bus", "Buffer", "Node", "Server", "Out",
    "In", "InFeedback", "ReplaceOut", "OffsetOut", "LocalIn", "LocalOut",
    "PlayBuf", "BufRd", "BufWr", "RecordBuf", "GrainIn", "GrainSin",
    "Sweep", "Phasor", "Line", "XLine", "EnvGen", "Linen", "Latch", "Hold",
    "Demand", "Duty", "TDuty", "Impulse", "Dust", "Dust2", "LFPulse",
    "LFSaw", "LFTri", "LFCub", "SinOsc", "Saw", "Pulse", "Blip", "Klang",
    "FSinOsc", "COsc", "Formant", "PMOsc", "VOsc", "Warp1", "FreeVerb",
    "GVerb", "PlateReverb", "CombN", "CombL", "CombC", "AllpassN",
    "AllpassL", "AllpassC", "DelayN", "DelayL", "DelayC", "LPF", "HPF",
    "BPF", "BRF", "MidEQ", "RLPF", "RHPF", "MoogFF", "Integrator",
    "LeakDC", "OnePole", "OneZero", "TwoPole", "TwoZero", "Median",
    "Ringz", "Formlet", "FOS", "SOS", "Decay", "Decay2", "Lag", "Lag2",
    "Lag3", "LagUD", "Slew", "Slope", "Ramp", "MFCC", "FFT", "IFFT",
    "PV_MagMul", "PV_BinScramble", "PV_RandWipe", "PV_BrickWall",
    "Done", "FreeSelfWhenDone", "FreeSelf", "PauseSelfWhenDone",
    "DetectSilence", "SendTrig", "SendReply", "Onsets", "Amplitude",
    "Compander", "CompanderD", "Limiter", "Normalizer", "Limiter",
    "InRange", "Clip", "Wrap", "Fold", "MantissaMask", "Ringz",
    "Select", "SelectX", "SelectXFocus", "Index", "WrapIndex", "FoldIndex",
    "IndexInBetween", "DetectIndex", "DegreeToKey", "T2A", "A2K", "K2A",
    "TExpRand", "TRand", "TIRand", "IRand", "Rand", "ExpRand", "LinRand",
    "NRand", "LinLin", "LinExp", "ExpExp", "Cubic", "Distort", "SoftClip",
    "Sacraficion", "Clip2", "Wrap2", "Fold2", "Excess", "Range", "MulAdd",
    "Sum3", "Sum4", "Mix", "Splay", "Pan2", "Pan4", "PanAz", "PanB",
    "DecodeB2", "EncodeB2", "Balance2", "XFade2", "LinXFade2", "BFEncode",
    "BFDecode", "BFMixer", "HoaEncoder", "HoaDecoder",
    "Score", "sclang", "scsynth", "Server", "TempoClock", "SystemClock",
    "AppClock", "Quant", "Beat", "Tuning", "Scale", "Event", "Pevent",
    "Stream", "Routine", "Thread", "Condition", "Semaphore",
    "AbstractFunction", "Pattern", "Plist", "Pseries", "Pgeom", "Ptuple",
    "Pcollect", "Pselect", "Preject", "Pclump", "Pflatten", "Pslide",
    "Pwalk", "Pconst", "Pdiff", "Pbindf", "Pchain", "Pfset", "Penvir",
    "Plazy", "Prout", "Psym", "Penvir", "Ppatmod", "Pdefn", "Pdef",
    "Pbindef", "PLbindef", "Tdef", "Ndef", "Pproto",
    "Tuning", "Info", "Plot", "Float", "Integer", "Number", "SimpleNumber",
    "SequenceableCollection", "Array", "List", "Set", "Dictionary",
    "IdentityDictionary", "Environment", "OrderedDictionary", "Stack",
    "SortedList", "LinkedList", "Pair", "Tuple", "String", "Symbol",
    "Boolean", "True", "False", "Char", "Color", "Point", "Rect", "Font",
    "Pen", "Window", "View", "CompositeView", "UserView", "StaticText",
    "Button", "Slider", "Knob", "RangeSlider", "NumberBox", "TextField",
    "TextView", "PopUpMenu", "ListView", "MultiSliderView", "EZSlider",
    "EZKnob", "EZNumber", "EZPopUpMenu", "EZList", "StaticText", "ScopeView",
    "FreqScopeView", "Stethoscope", "ServerScopeWindow", "Plotter",
    "SoundFile", "Buffer", "Pitch", "BeatTrack", "Onsets",
    "Routine", "Tdef", "Pdef", "Task", "Spawn", "Stream", "Pattern",
    "Pbindef", "Pbind", "Pseq", "Prand", "Pshuf", "Pwhite", "Pbrown",
    "Pwalk", "Ptuple", "Pdict", "Pkey", "Pif", "Psync", "PdurStutter",
    "Pstretch", "Pfindur", "Pfin", "Pclutch", "Pgpar", "Pgroup", "Pspawn",
    "Pspawner", "Pbindef", "PbindProxy", "Pdefn", "Pproto", "Ptpar",
    "Pbus", "Pgroup", "Pfx", "Pgpu", "Pbus", "Pbus", "Plambda", "Plet",
    "Pget", "Psym", "Pindex", "Pcollide",
    "play", "stop", "reset", "next", "embedInStream", "yield", "wait",
    "sleep", "until", "while", "loop", "fork", "routine", "asStream",
    "iter", "asInteger", "asFloat", "asString", "asSymbol", "asArray",
    "asList", "dup", "do", "collect", "select", "reject", "detect",
    "inject", "foldCollect", "any", "every", "count", "sum", "product",
    "max", "min", "mean", "median", "average", "sort", "sortBy", "sortBy",
    "reverse", "scramble", "mirror", "mirror1", "mirror2", "stutter",
    "rotate", "permute", "pyramid", "pyramidg", "pyramidm", "sieve",
    "differentiate", "integrate", "normalizeSum", "normalize", "linlin",
    "linexp", "explin", "expexp", "curvelin", "lincurve", "bilin", "biexp",
    "degrad", "raddeg", "rangex", "clip", "wrap", "fold", "clip2", "wrap2",
    "fold2", "excess", "mod", "div", "gcd", "lcm", "bitAnd", "bitOr",
    "bitXor", "bitNot", "bitHammingDistance", "asDigit", "digit", "digits",
    "thru", "within", "blend", "perform", "performList", "superPerform",
    "superPerformList", "performKeyValuePairs", "multiPerform", "objects",
    "respondsTo", "performMsg", "try", "protect", "catch", "finally",
    "if", "while", "for", "forBy", "case", "switch", "ifNil", "ifNotNil",
    "isKindOf", "isMemberOf", "respondsTo", "class", "isNil", "notNil",
    "isBoolean", "isNumber", "isInteger", "isFloat", "isSequenceableCollection",
    "isArray", "isCollection", "isString", "isSymbol", "isChar",
    "new", "newCopyArgs", "newClear", "copy", "deepCopy", "shallowCopy",
    "dup", "do", "collect", "select", "reject", "detect", "inject",
    "stop", "play", "reset", "next", "end", "start", "free", "release",
    "isPlaying", "isRunning", "isStopped", "isPaused",
    "spawn", "awake", "sustain", "delta", "nextTime", "embedInStream",
    "yield", "wait", "sleep", "until", "asStream", "asRoutine",
    "now", "elapsedTime", "cpuUsage", "avgCPU", "peakCPU", "sampleRate",
    "sampleDur", "controlRate", "blockSize", "numInputBusChannels",
    "numOutputBusChannels", "numAudioBusChannels", "numControlBusChannels",
    "defaultGroup", "name", "addr", "clientID", "isLocal", "boot",
    "quit", "reboot", "status", "notify", "unregister", "sync", "flush",
    "dumpOSC", "queryAllNodes", "scope", "freqscope", "meter", "plotTree",
    "makeWindow", "makeGui", "window", "scope", "freqscope", "meter",
    "volume", "mute", "unmute", "record", "pauseRecording", "resumeRecording",
    "stopRecording", "prepareForRecord", "recHeaderFormat", "recSampleFormat",
    "recChannels",
    "SynthDef", "add", "store", "send", "load", "writeDefFile", "play",
    "free", "release", "run", "head", "tail", "before", "after", "replace",
    "onFree", "onEnd", "onDone", "set", "setn", "get", "getn", "map",
    "mapn", "mapAudio", "unmap", "fill", "control", "controlsSet",
    "controlsGet", "nodeID", "isPlaying", "isRunning", "group", "synthDef",
    "name", "defName",
    "Score", "write", "play", "recordNRT", "sort", "add", "bundle", "list",
    "at", "put", "add", "addAll", "insert", "insertAll", "removeAt",
    "remove", "pop", "first", "last", "wrapAt", "foldAt", "clipAt", "putFirst",
    "putLast", "wrapPut", "foldPut", "clipPut", "indexOf", "indexOfEqual",
    "first", "last", "first", "last", "occurrencesOf", "includesEqual",
    "includes", "any", "every", "detect", "detectIndex", "collect",
    "select", "reject", "partition", "separate", "clump", "curdle", "flatten",
    "unflatten", "pyramid", "pyramidg", "pyramidm", "stutter", "rotate",
    "permute", "scramble", "mirror", "mirror1", "mirror2", "reverse",
    "sort", "sortBy", "mergeSort", "quickSort", "topologicalSort", "flop",
    "spread", "separate", "clump", "slide", "stutter", "rotate", "mirror",
    "mirror1", "mirror2", "pyramid", "pyramidg", "pyramidm",
    "var", "arg", "classvar", "const", "thisFunctionDef", "thisFunction",
    "thisMethod", "thisProcess", "thisThread", "this", "super",
    "true", "false", "nil", "inf", "pi", "nil", "topEnvironment",
    "currentEnvironment", "topEnvironment",
}

_SC_OPERATORS = {
    "+", "-", "*", "/", "%", "<", ">", "<=", ">=", "==", "!=", "===", "!==",
    "=", "+=", "-=", "*=", "/=", "&", "|", "^", "~", "<<", ">>", "&&", "||",
    "!", "??", "?", "<-", "<>", "->", "=>", "min", "max",
}

_SC_TOKEN_RE = re.compile(r'''
      (?P<comment>      //[^\n]* | /\*[\s\S]*?\*/ )
    | (?P<string>       "(?:\\.|[^"\\])*" | '(?:\\.|[^'\\])*' )
    | (?P<envvar>       ~[A-Za-z_][A-Za-z0-9_]* )
    | (?P<symbol>       \\[A-Za-z_][A-Za-z0-9_]* |\b['][A-Za-z_][A-Za-z0-9_]*' )
    | (?P<number>       \b\d+\.?\d*(?:[eE][+-]?\d+)?\b | \b0x[0-9A-Fa-f]+\b | \.\d+\b )
    | (?P<word>         [A-Za-z_][A-Za-z0-9_]* )
    | (?P<op>           -> | => | \?\? | == | != | <= | >= | [-+*/%=<>!&|^~] )
    | (?P<ws>           \s+ )
    | (?P<other>        . )
''', re.VERBOSE | re.MULTILINE | re.DOTALL)


class SyntaxHighlighter:
    """SuperCollider tokenizer + theme colorizer."""

    def __init__(self, theme_name="Dracula"):
        self.theme_name = theme_name
        self.theme = SYNTAX_THEMES.get(theme_name, SYNTAX_THEMES["Dracula"])

    @staticmethod
    def available_themes():
        return list(SYNTAX_THEMES.keys())

    def set_theme(self, theme_name):
        self.theme_name = theme_name
        self.theme = SYNTAX_THEMES.get(theme_name, SYNTAX_THEMES["Dracula"])

    def _classify(self, kind: str, text: str) -> str:
        """Map token kind to a syntax theme category name."""
        if kind == "comment":
            return "comment"
        if kind == "string":
            return "string"
        if kind == "envvar":
            return "envvar"
        if kind == "symbol":
            return "symbol"
        if kind == "number":
            return "number"
        if kind == "op":
            return "operator"
        if kind == "ws" or kind == "other":
            return "default"
        if kind == "word":
            # Class name: starts with uppercase
            if text[:1].isupper():
                return "class"
            # Keyword
            if text in _SC_KEYWORDS:
                return "keyword"
            # Method-like (camelCase heuristic: starts lowercase with internal uppercase)
            if any(c.isupper() for c in text[1:]) and not text.isupper():
                return "method"
            # Otherwise default
            return "default"
        return "default"

    def color_for(self, kind: str, text: str) -> QColor:
        category = self._classify(kind, text)
        return self.theme.get(category, self.theme["default"])

    def tokenize(self, code: str):
        """
        Yields tuples of (kind, text) covering the entire input string.
        kinds: comment, string, envvar, symbol, number, word, op, ws, other
        """
        pos = 0
        for m in _SC_TOKEN_RE.finditer(code):
            if m.start() != pos:
                # Unmatched gap (shouldn't usually happen) – emit as 'other'
                yield ("other", code[pos:m.start()])
            kind = m.lastgroup
            text = m.group()
            yield (kind, text)
            pos = m.end()
        if pos < len(code):
            yield ("other", code[pos:])


def dims_for(layout_text: str, quality_text: str):
    w, h = QUALITY_PRESETS[quality_text]
    if "9:16" in layout_text:
        return h, w
    return w, h


def format_time_duration(seconds):
    seconds = int(math.floor(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}h {m:02}m {s:02}s"
    elif m > 0:
        return f"{m}m {s:02}s"
    else:
        return f"{s}s"


def compute_audio_plan(behavior, typing_natural, audio_duration, tail_sec=AUDIO_TAIL_SEC):
    typing_natural = max(0.5, typing_natural)
    audio_duration = max(0.1, audio_duration)

    if "SC Renders to Match" in behavior:
        return typing_natural, typing_natural, False, typing_natural

    if "Audio Matches Typing" in behavior:
        total = typing_natural
        loop = audio_duration < (total - 0.1)
        return typing_natural, total, loop, total

    if "Typing Matches Audio" in behavior:
        return audio_duration, audio_duration, False, audio_duration

    if "Audio Tail" in behavior:
        total = typing_natural + tail_sec
        loop = audio_duration < (total - 0.1)
        return typing_natural, total, loop, total

    if "Trim Audio to Typing" in behavior:
        return typing_natural, typing_natural, False, typing_natural

    if "Independent" in behavior:
        total = max(typing_natural, audio_duration)
        return typing_natural, total, False, total

    return typing_natural, typing_natural, False, typing_natural


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
# Mock Audio Data
# ============================================================================
class MockAudioData:
    def __init__(self, duration):
        self.duration = max(1.0, duration)

    def get_envelope(self, n_bins):
        t = np.linspace(0, 1, n_bins)
        return (np.sin(t * 2 * np.pi) * 0.4 + 0.6) * np.random.uniform(0.6, 1.0, n_bins)

    def get_frame_amplitudes(self, fps, offset=0.0):
        n_frames = int(self.duration * fps) + 1
        t = np.linspace(0, self.duration, n_frames)
        return np.sin(t * 4) * 0.3 + 0.5


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
    def generate(sc_code, score_path, wav_path, temp_dir, log_fn, state_cb=None, target_duration=None):
        def _cb(state, msg, pct):
            if state_cb: state_cb(state, msg, pct)

        _cb(PipelineState.PREPARING_SCRIPT, "Preparing SC script...", 5)

        if "__SCORE_PATH__" not in sc_code:
            log_fn("  [WARNING] '__SCORE_PATH__' placeholder missing in SC code.")

        score_path_sc = score_path.replace('\\', '/')
        final_sc_code = sc_code.replace("__SCORE_PATH__", score_path_sc)

        if "__DURATION__" in final_sc_code:
            if target_duration is not None:
                final_sc_code = final_sc_code.replace("__DURATION__", f"{target_duration:.6f}")
                log_fn(f"  [SC Renders to Match] Instructing SC to render {target_duration:.3f}s of audio")
            else:
                default_dur = 10.0
                final_sc_code = final_sc_code.replace("__DURATION__", f"{default_dur:.6f}")
                log_fn(f"  [INFO] Replaced __DURATION__ with default {default_dur}s (SC Renders to Match not active)")

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
    def __init__(self, text, duration, style="Cubic Ease-Out"):
        self.text = text
        self.duration = duration
        self.typing_end = max(0.5, duration)
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
    def __init__(self, audio_data, sc_code, width=1920, height=1080, fps=30,
                 typing_style="Cubic Ease-Out", visual_style="Circular + Waveform",
                 show_safe_zones=False, typing_duration=5.0, total_duration=10.0,
                 code_font_family="Consolas", code_font_size=16, autofit_mode="Off (Manual Size)",
                 theme_name="Midnight Blue", show_bounds=False, loop_audio=False,
                 syntax_theme="Dracula"):
        self.audio = audio_data
        self.sc_code = sc_code
        self.width = width
        self.height = height
        self.fps = fps
        self.typing_style = typing_style
        self.visual_style = visual_style
        self.show_safe_zones = show_safe_zones
        self.show_bounds = show_bounds
        self.is_portrait = height > width
        self.theme = VIDEO_THEMES.get(theme_name, VIDEO_THEMES["Midnight Blue"])
        self.loop_audio = loop_audio
        self.syntax_highlighter = SyntaxHighlighter(syntax_theme)
        self.syntax_theme_name = syntax_theme

        self.audio_duration = audio_data.duration
        self.total_duration = total_duration

        self.code_typing = TypingAnimator(sc_code, typing_duration, typing_style)

        self.n_bars = 120
        self.envelope = audio_data.get_envelope(self.n_bars)
        self.frame_amps = audio_data.get_frame_amplitudes(fps)

        scale = self.height / 1080.0
        self.font_title = QFont("Consolas", max(10, int(14 * scale)), QFont.Bold)
        self.font_time  = QFont("Consolas", max(9,  int(12 * scale)))
        self.font_body  = QFont("Consolas", max(12, int(18 * scale)))
        self.font_label = QFont("Consolas", max(8,  int(10 * scale)))

        base_sz = code_font_size
        if self.is_portrait and code_font_size == 16:
            base_sz = 14

        target_sz = max(8, int(base_sz * scale))

        CODE_PAD = (20, 30, 20, 20)

        L = self._layout()
        text_area = L["code_rect"].adjusted(
            CODE_PAD[0], CODE_PAD[1], -CODE_PAD[2], -CODE_PAD[3]
        )

        if autofit_mode != "Off (Manual Size)":
            lines = self.sc_code.splitlines()
            longest_line = max(lines, key=len) if lines else ""
            n_lines = max(1, len(lines))

            def _fits(sz: int) -> bool:
                if sz < 8:
                    return False
                f = QFont(code_font_family, sz)
                f.setStyleHint(QFont.Monospace)
                fm = QFontMetrics(f)
                line_w  = fm.horizontalAdvance(longest_line)
                total_h = n_lines * fm.lineSpacing()
                fits_w = line_w <= text_area.width()
                fits_h = total_h <= text_area.height()

                if autofit_mode == "Horizontal (No Horiz Overflow, Scroll Vert)":
                    return fits_w
                if autofit_mode == "Vertical (No Vert Scroll, Clip Horiz)":
                    return fits_h
                if autofit_mode == "Directional (No Clip/No Scroll)":
                    return fits_w and fits_h
                return False

            lo, hi = 8, 256
            best   = 8
            while lo <= hi:
                mid = (lo + hi) // 2
                if _fits(mid):
                    best = mid
                    lo = mid + 1
                else:
                    hi = mid - 1
            target_sz = best

        self.font_code = QFont(code_font_family, target_sz)
        self.font_code.setStyleHint(QFont.Monospace)

        self._code_pad = CODE_PAD
        self.canvas = QImage(self.width, self.height, QImage.Format_RGBA8888)

    def _layout(self):
        W, H = self.width, self.height
        m = int(W * 0.04)
        if self.is_portrait:
            return {
                "code_rect": QRect(m, int(H * 0.05), W - 2 * m, int(H * 0.40)),
                "viz_cy":    int(H * 0.62),
                "wf_rect":   QRect(int(W * 0.10), int(H * 0.82), int(W * 0.80), int(H * 0.08)),
            }
        else:
            return {
                "code_rect": QRect(m, int(H * 0.04), W - 2 * m, int(H * 0.62)),
                "viz_cy":    int(H * 0.80),
                "wf_rect":   QRect(int(W * 0.05), int(H * 0.89), int(W * 0.90), int(H * 0.06)),
            }

    def render_frame_to_canvas(self, frame_idx):
        t = frame_idx / self.fps
        self.canvas.fill(Qt.transparent)
        p = QPainter(self.canvas)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        if self.loop_audio:
            safe_len = max(1, len(self.frame_amps))
            amp_idx = frame_idx % safe_len
            amp = float(self.frame_amps[amp_idx]) if amp_idx < safe_len else 0.0
            audio_t = t % max(0.001, self.audio_duration)
        else:
            if t < self.audio_duration:
                amp_idx = min(frame_idx, len(self.frame_amps) - 1)
                amp = float(self.frame_amps[amp_idx]) if amp_idx >= 0 else 0.0
                audio_t = t
            else:
                amp = 0.0
                audio_t = self.audio_duration

        L = self._layout()

        self._draw_background(p, amp)
        self._draw_code_phase(p, t, L)

        if self.visual_style == "Bars Only":
            self._draw_waveform(p, audio_t, L["wf_rect"])
        elif self.visual_style == "Minimal Waveform":
            self._draw_waveform(p, audio_t, L["wf_rect"], alpha=200)
        else:
            self._draw_circular_viz(p, audio_t, amp, L["viz_cy"])
            self._draw_waveform(p, audio_t, L["wf_rect"])

        if self.show_safe_zones and self.is_portrait:
            self._draw_shorts_safe_zones(p)

        if self.show_bounds:
            self._draw_layout_bounds(p, t, L)

        p.end()
        return self.canvas

    def _draw_background(self, p, amp):
        grad = QLinearGradient(0, 0, 0, self.height)
        grad.setColorAt(0.0, self.theme["bg_top"])
        grad.setColorAt(0.5, self.theme["bg_mid"])
        grad.setColorAt(1.0, self.theme["bg_bot"])
        p.fillRect(0, 0, self.width, self.height, QBrush(grad))

        glow_color = QColor(self.theme["glow"])
        glow_color.setAlpha(int(60 * amp))
        glow = QRadialGradient(self.width / 2, self.height / 2, self.width / 2)
        glow.setColorAt(0, glow_color)
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, self.width, self.height, QBrush(glow))

        grid_color = QColor(self.theme["accent1"])
        grid_color.setAlpha(22)
        p.setPen(QPen(grid_color, 1))
        for x in range(0, self.width, 40): p.drawLine(x, 0, x, self.height)
        for y in range(0, self.height, 40): p.drawLine(0, y, self.width, y)

    def _draw_code_phase(self, p, t, L):
        rect = L["code_rect"]
        border_color = QColor(self.theme["accent1"])
        border_color.setAlpha(150)
        p.setPen(QPen(border_color, 2))

        # Use syntax theme bg for the code panel if available, else default
        code_panel_bg = self.syntax_highlighter.theme.get("bg", QColor(20, 22, 30, 230))
        code_panel_bg = QColor(code_panel_bg)
        code_panel_bg.setAlpha(230)
        p.setBrush(code_panel_bg)
        p.drawRoundedRect(rect, 10, 10)

        p.setPen(QColor(255, 100, 100)); p.drawEllipse(rect.left() + 20, rect.top() + 15, 8, 8)
        p.setPen(QColor(255, 200, 100)); p.drawEllipse(rect.left() + 35, rect.top() + 15, 8, 8)
        p.setPen(QColor(100, 255, 100)); p.drawEllipse(rect.left() + 50, rect.top() + 15, 8, 8)

        visible_code = self.code_typing.visible_text(t)
        show_cursor = self.code_typing.cursor_visible(t)
        if show_cursor:
            visible_code += "█"

        p.setPen(self.theme["code_text"])
        p.setFont(self.font_code)

        pl, pt, pr, pb = self._code_pad
        text_area = rect.adjusted(pl, pt, -pr, -pb)

        fm = p.fontMetrics()
        text_flags = Qt.AlignTop | Qt.AlignLeft | Qt.TextExpandTabs
        text_rect = fm.boundingRect(QRect(0, 0, text_area.width(), 999999),
                                    text_flags,
                                    visible_code)

        y_offset = 0
        if text_rect.height() > text_area.height():
            y_offset = text_area.height() - text_rect.height()

        p.save()
        p.setClipRect(text_area)

        # ------------------------------------------------------------------
        # SYNTAX HIGHLIGHTED RENDERING via QTextLayout
        # ------------------------------------------------------------------
        # We tokenize the full visible_code (including the cursor block) and
        # build QTextLayout line-by-line so the existing scroll/clip layout
        # is preserved exactly.
        default_color = self.syntax_highlighter.theme.get("default", QColor(220, 220, 220))
        cursor_color  = self.syntax_highlighter.theme.get("cursor", QColor(255, 255, 255))

        # Build a list of (char_index -> color) using tokenizer offsets.
        char_colors = [default_color] * len(visible_code)
        offset = 0
        for kind, text in self.syntax_highlighter.tokenize(visible_code):
            if kind == "other" and text == "█":
                # Cursor block character
                for i in range(offset, offset + len(text)):
                    if 0 <= i < len(char_colors):
                        char_colors[i] = cursor_color
            else:
                color = self.syntax_highlighter.color_for(kind, text)
                for i in range(offset, offset + len(text)):
                    if 0 <= i < len(char_colors):
                        char_colors[i] = color
            offset += len(text)

        # Split visible_code into lines and tokenize per line for QTextLayout.
        # (visible_code may end mid-line due to typing animation.)
        lines = visible_code.split('\n')
        fm_line = QFontMetrics(self.font_code)
        line_height = fm_line.lineSpacing()

        # Build QTextLayout for the entire text block, then position each line.
        layout = QTextLayout(visible_code, self.font_code, p.device())
        layout.setCacheEnabled(True)
        layout.beginLayout()

        # Pre-compute line starts (character offsets) so we can map token colors
        line_starts = []
        cumulative = 0
        for line_text in lines:
            line_starts.append(cumulative)
            cumulative += len(line_text)
            # Account for the newline character that was consumed by split,
            # EXCEPT for the last line (no trailing newline).
            if cumulative < len(visible_code):
                cumulative += 1

        line_formats = []
        # Build QTextCharFormat ranges for each color run.
        # We iterate char-by-char and group consecutive equal colors.
        if char_colors:
            current_color = char_colors[0]
            run_start = 0
            for i in range(1, len(char_colors)):
                if char_colors[i] != current_color:
                    fmt = QTextCharFormat()
                    fmt.setForeground(current_color)
                    line_formats.append((run_start, i, fmt))
                    current_color = char_colors[i]
                    run_start = i
            fmt = QTextCharFormat()
            fmt.setForeground(current_color)
            line_formats.append((run_start, len(char_colors), fmt))

        # Apply additional formats
        layout.setFormats(line_formats)

        # Create line positions
        y = y_offset  # start at scrolled y
        for i, line_text in enumerate(lines):
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(max(1, text_area.width()))
            line.setPosition(QPointF(0, y))
            y += line_height

        layout.endLayout()

        # Translate painter so the layout draws within text_area
        p.translate(text_area.x(), text_area.y())
        layout.draw(p, QPointF(0, 0))
        p.restore()

    def _draw_circular_viz(self, p, t, amp, cy):
        cx = self.width // 2
        base_r = int(min(self.width, self.height) * 0.07)
        circ_color = QColor(255, 255, 255, 30)
        p.setPen(QPen(circ_color, 1)); p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), base_r, base_r)

        playhead_progress = t / max(0.001, self.audio_duration)
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
                color = self._lerp_color(self.theme["accent1"], self.theme["accent2"], seg_progress)
                color.setAlpha(220)
            else:
                color = QColor(70, 90, 130, 80)
            p.setPen(QPen(color, 2))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _draw_waveform(self, p, t, rect, alpha=230):
        wf_x, wf_y = rect.x(), rect.y()
        wf_w, wf_h = rect.width(), rect.height()
        mid_y = wf_y + wf_h // 2

        p.fillRect(wf_x, wf_y, wf_w, wf_h, QColor(0, 0, 0, 110))
        p.setPen(QPen(QColor(100, 130, 170, 110), 1)); p.setBrush(Qt.NoBrush)
        p.drawRect(wf_x, wf_y, wf_w, wf_h)

        bar_w = wf_w / self.n_bars
        playhead_progress = t / max(0.001, self.audio_duration)

        p.setPen(Qt.NoPen)
        for i, amp_val in enumerate(self.envelope):
            x = wf_x + i * bar_w
            h = amp_val * (wf_h / 2) * 0.95
            if (i / self.n_bars) <= playhead_progress:
                color = self._lerp_color(self.theme["accent1"], self.theme["accent2"], i / self.n_bars)
                color.setAlpha(alpha)
            else:
                color = QColor(70, 90, 130, 100)
            p.setBrush(color)
            p.drawRect(QRectF(x, mid_y - h, max(1.0, bar_w - 1.0), 2.0 * h))

        ph_x = wf_x + playhead_progress * wf_w
        p.setPen(QPen(QColor(255, 255, 255, 230), 2))
        p.drawLine(QPointF(ph_x, wf_y - 6), QPointF(ph_x, wf_y + wf_h + 6))

    def _draw_shorts_safe_zones(self, p):
        W, H = self.width, self.height
        p.setPen(QPen(QColor(255, 80, 80, 180), 2, Qt.DashLine))
        p.setBrush(QColor(255, 80, 80, 18))
        p.drawRect(0, 0, W, int(H * 0.08))
        p.drawRect(0, int(H * 0.78), W, int(H * 0.22))
        p.drawRect(int(W * 0.82), int(H * 0.45), int(W * 0.18), int(H * 0.35))

    def _draw_layout_bounds(self, p, t, L):
        p.setBrush(QColor(255, 0, 0, 30))
        p.setPen(QPen(QColor(255, 0, 0, 200), 2))
        p.drawRect(L["code_rect"])

        pl, pt, pr, pb = self._code_pad
        text_area = L["code_rect"].adjusted(pl, pt, -pr, -pb)

        p.setBrush(QColor(255, 255, 0, 30))
        p.setPen(QPen(QColor(255, 255, 0, 200), 2))
        p.drawRect(text_area)

        visible_code = self.code_typing.visible_text(t)
        if self.code_typing.cursor_visible(t): visible_code += "█"

        fm = QFontMetrics(self.font_code)
        text_flags = Qt.AlignTop | Qt.AlignLeft | Qt.TextExpandTabs
        text_rect = fm.boundingRect(QRect(0, 0, text_area.width(), 999999), text_flags, visible_code)

        y_offset = 0
        if text_rect.height() > text_area.height():
            y_offset = text_area.height() - text_rect.height()

        draw_rect = text_area.adjusted(0, y_offset, 0, 0)
        actual_text_box = QRect(draw_rect.x(), draw_rect.y(), text_rect.width(), text_rect.height())

        p.setBrush(QColor(0, 255, 255, 60))
        p.setPen(QPen(QColor(0, 255, 255, 255), 2))
        p.drawRect(actual_text_box)

        p.setBrush(QColor(0, 255, 0, 30))
        p.setPen(QPen(QColor(0, 255, 0, 200), 2))
        p.drawRect(L["wf_rect"])

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
    def start_ffmpeg_process(wav_path, output_mp4, fps, width, height, log_fn,
                             bitrate_preset="High", max_duration=None,
                             loop_audio=False, fade_out_sec=0.5):
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg: raise Exception("ffmpeg not found on PATH")

        bp = BITRATE_PRESETS.get(bitrate_preset, BITRATE_PRESETS["High"])
        vbitrate_num = int(bp['vbitrate'].rstrip('M'))

        cmd = [
            ffmpeg, '-y',
            '-f', 'rawvideo', '-vcodec', 'rawvideo',
            '-s', f'{width}x{height}', '-pix_fmt', 'rgba',
            '-r', str(fps), '-i', 'pipe:0',
        ]

        if loop_audio:
            cmd.extend(['-stream_loop', '-1', '-i', wav_path])
        else:
            cmd.extend(['-i', wav_path])

        audio_filters = []

        if not loop_audio and max_duration is not None:
            audio_filters.append(f"apad=whole_dur={max_duration:.3f}")

        if max_duration is not None and fade_out_sec > 0:
            fade_start = max(0.0, max_duration - fade_out_sec)
            audio_filters.append(f"afade=t=out:st={fade_start:.3f}:d={fade_out_sec:.3f}")

        cmd.extend([
            '-c:v', 'libx264', '-preset', 'veryfast',
            '-profile:v', 'high',
            '-crf', bp['crf'],
            '-maxrate', bp['vbitrate'], '-bufsize', f'{vbitrate_num * 2}M',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac',
            '-b:a', bp['abitrate'],
            '-ar', '48000',
            '-ac', '2'
        ])

        if audio_filters:
            cmd.extend(['-af', ','.join(audio_filters)])

        if max_duration is not None:
            cmd.extend(['-t', f'{max_duration:.3f}'])

        cmd.extend(['-movflags', '+faststart', output_mp4])

        log_fn("  Starting FFmpeg process...")
        log_fn(f"  ffmpeg cmd: {' '.join(cmd)}")
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        def drain_stderr():
            while True:
                line = proc.stderr.readline()
                if not line: break
                log_fn(f"  ffmpeg: {line.decode('utf-8', errors='replace').strip()}")
            proc.stderr.close()

        th = threading.Thread(target=drain_stderr, daemon=True)
        th.start()
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

    def __init__(self, sc_code, output_mp4, fps=30, width=1920, height=1080,
                 typing_style="Cubic Ease-Out", visual_style="Circular + Waveform",
                 bitrate_preset="High", show_safe_zones=False, cps=20,
                 code_font_family="Consolas", code_font_size=16, autofit_mode="Off (Manual Size)",
                 video_theme="Midnight Blue", audio_behavior="Audio Matches Typing (Loop/Cut)", show_bounds=False,
                 syntax_theme="Dracula"):
        super().__init__()
        self.sc_code = sc_code
        self.output_mp4 = output_mp4
        self.fps = fps
        self.width = width
        self.height = height
        self.typing_style = typing_style
        self.visual_style = visual_style
        self.bitrate_preset = bitrate_preset
        self.show_safe_zones = show_safe_zones
        self.show_bounds = show_bounds
        self.cps = max(1, cps)
        self.code_font_family = code_font_family
        self.code_font_size = code_font_size
        self.autofit_mode = autofit_mode
        self.video_theme = video_theme
        self.audio_behavior = audio_behavior
        self.syntax_theme = syntax_theme
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

            typing_natural = max(1.0, len(self.sc_code) / self.cps)
            target_duration = None
            if "SC Renders to Match" in self.audio_behavior:
                target_duration = typing_natural

            audio_error = [None]
            def generate_audio_async():
                try:
                    AudioGenerator.generate(
                        self.sc_code, score_path, wav_path, self.temp_dir,
                        self.log.emit, self._set_state,
                        target_duration=target_duration
                    )
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

            raw_audio_duration = audio_data.duration

            typing_duration, total_duration, loop_audio, max_dur = compute_audio_plan(
                self.audio_behavior, typing_natural, raw_audio_duration
            )

            n_frames = int(total_duration * self.fps) + 1
            self.duration_ready.emit(total_duration, n_frames)
            self.log.emit(
                f"  [AUDIO PLAN] behavior='{self.audio_behavior}'  "
                f"typing_natural={typing_natural:.2f}s  "
                f"audio={raw_audio_duration:.2f}s  "
                f"typing_dur={typing_duration:.2f}s  "
                f"total={total_duration:.2f}s  "
                f"loop={loop_audio}  max={max_dur}"
            )

            self._set_state(PipelineState.INITIALIZING_RENDERER, "Initializing renderer...", 28)
            renderer = FrameRenderer(audio_data, self.sc_code, self.width, self.height,
                                     self.fps, self.typing_style, self.visual_style,
                                     show_safe_zones=self.show_safe_zones,
                                     typing_duration=typing_duration, total_duration=total_duration,
                                     code_font_family=self.code_font_family, code_font_size=self.code_font_size,
                                     autofit_mode=self.autofit_mode, theme_name=self.video_theme,
                                     show_bounds=self.show_bounds, loop_audio=loop_audio,
                                     syntax_theme=self.syntax_theme)

            self._set_state(PipelineState.STARTING_ENCODER, "Starting FFmpeg process...", 30)
            proc = VideoEncoder.start_ffmpeg_process(
                wav_path, self.output_mp4, self.fps,
                self.width, self.height, self.log.emit,
                bitrate_preset=self.bitrate_preset,
                max_duration=max_dur,
                loop_audio=loop_audio,
                fade_out_sec=AUDIO_FADE_OUT_SEC,
            )

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
        self.resize(1200, 880)
        log.info("UI initializing...")

        os.makedirs(INPUT_FOLDER, exist_ok=True)
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)

        self.settings = QSettings("SCNRT_Viz", "AppSettings")

        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.8)
        self.current_wav_path = ""

        self.worker_thread = None
        self.worker = None
        self.queue = []

        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self.update_preview_frame)
        self.preview_frame_idx = 0
        self.preview_renderer = None

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
        self.file_list.itemSelectionChanged.connect(self.setup_preview_renderer)
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

        # Layout + Quality + Video Theme + UI Theme
        opts_row1 = QHBoxLayout()
        opts_row1.addWidget(QLabel("Layout:"))
        self.layout_combo = QComboBox()
        self.layout_combo.addItems(["YouTube Video (16:9)", "YouTube Short (9:16)"])
        self.layout_combo.setCurrentText(self.settings.value("layout", "YouTube Video (16:9)"))
        self.layout_combo.currentTextChanged.connect(self.on_layout_or_quality_changed)
        opts_row1.addWidget(self.layout_combo)

        opts_row1.addWidget(QLabel("Quality:"))
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(list(QUALITY_PRESETS.keys()))
        self.quality_combo.setCurrentText(self.settings.value("quality", "1080p (Full HD)"))
        self.quality_combo.currentTextChanged.connect(self.on_layout_or_quality_changed)
        opts_row1.addWidget(self.quality_combo)

        opts_row1.addWidget(QLabel("Video Theme:"))
        self.video_theme_combo = QComboBox()
        self.video_theme_combo.addItems(list(VIDEO_THEMES.keys()))
        self.video_theme_combo.setCurrentText(self.settings.value("video_theme", "Midnight Blue"))
        self.video_theme_combo.currentTextChanged.connect(self.setup_preview_renderer)
        opts_row1.addWidget(self.video_theme_combo)

        opts_row1.addWidget(QLabel("Syntax Theme:"))
        self.syntax_theme_combo = QComboBox()
        self.syntax_theme_combo.addItems(SyntaxHighlighter.available_themes())
        self.syntax_theme_combo.setCurrentText(self.settings.value("syntax_theme", "Dracula"))
        self.syntax_theme_combo.setToolTip(
            "Color theme used for syntax highlighting of SuperCollider code.\n"
            "Includes keyword, class, method, string, comment, number, and operator coloring."
        )
        self.syntax_theme_combo.currentTextChanged.connect(self.setup_preview_renderer)
        opts_row1.addWidget(self.syntax_theme_combo)

        opts_row1.addWidget(QLabel("UI Theme:"))
        self.ui_theme_combo = QComboBox()
        self.ui_theme_combo.addItems(["Dark", "Light"])
        self.ui_theme_combo.setCurrentText(self.settings.value("ui_theme", "Dark"))
        self.ui_theme_combo.currentTextChanged.connect(self.apply_ui_theme)
        opts_row1.addWidget(self.ui_theme_combo)
        opts_row1.addStretch()
        out_layout.addLayout(opts_row1)

        # Typing + Visual Style + Audio Behavior
        opts_row2 = QHBoxLayout()
        opts_row2.addWidget(QLabel("Typing Style:"))
        self.type_style_combo = QComboBox()
        self.type_style_combo.addItems(["Cubic Ease-Out", "Linear", "Typewriter", "Bursts"])
        self.type_style_combo.setCurrentText(self.settings.value("typing_style", "Cubic Ease-Out"))
        self.type_style_combo.currentTextChanged.connect(self.setup_preview_renderer)
        opts_row2.addWidget(self.type_style_combo)

        opts_row2.addWidget(QLabel("Typing Speed (CPS):"))
        self.cps_spin = QSpinBox()
        self.cps_spin.setRange(1, 200)
        self.cps_spin.setValue(int(self.settings.value("cps", 20)))
        self.cps_spin.setToolTip("Characters Per Second. Controls exactly how fast the code types.")
        self.cps_spin.valueChanged.connect(self.setup_preview_renderer)
        opts_row2.addWidget(self.cps_spin)

        opts_row2.addWidget(QLabel("Est. Typing Time:"))
        self.est_time_label = QLabel("0s")
        self.est_time_label.setStyleSheet("font-weight: bold; color: #4CAF50; padding: 2px 6px;")
        opts_row2.addWidget(self.est_time_label)

        opts_row2.addWidget(QLabel("Audio Behavior:"))
        self.audio_behavior_combo = QComboBox()
        self.audio_behavior_combo.addItems(AUDIO_BEHAVIORS)
        self.audio_behavior_combo.setCurrentText(self.settings.value("audio_behavior", AUDIO_BEHAVIORS[0]))
        self.audio_behavior_combo.currentTextChanged.connect(self.setup_preview_renderer)
        self.audio_behavior_combo.setToolTip(
            "Audio Matches Typing (Loop/Cut): video = typing length, audio loops/cuts.\n"
            "Audio Matches Typing (SC Renders to Match): SC generates audio for exactly the typing duration (use __DURATION__ in .scd).\n"
            "Typing Matches Audio: typing stretches to fill the entire audio.\n"
            "Typing + Audio Tail: video = typing + 2s, audio loops/cuts.\n"
            "Trim Audio to Typing: audio is cut to typing length (no loop).\n"
            "Independent: video = max(typing, audio), audio plays once."
        )
        opts_row2.addWidget(self.audio_behavior_combo)

        opts_row2.addWidget(QLabel("Visual Style:"))
        self.viz_style_combo = QComboBox()
        self.viz_style_combo.addItems(["Circular + Waveform", "Bars Only", "Minimal Waveform"])
        self.viz_style_combo.setCurrentText(self.settings.value("visual_style", "Circular + Waveform"))
        self.viz_style_combo.currentTextChanged.connect(self.setup_preview_renderer)
        opts_row2.addWidget(self.viz_style_combo)
        opts_row2.addStretch()
        out_layout.addLayout(opts_row2)

        # Code Font Options
        opts_row_fonts = QHBoxLayout()
        opts_row_fonts.addWidget(QLabel("Code Font:"))
        self.code_font_combo = QFontComboBox()
        self.code_font_combo.setFontFilters(QFontComboBox.MonospacedFonts)
        saved_font_family = self.settings.value("code_font_family", "Consolas")
        self.code_font_combo.setCurrentFont(QFont(saved_font_family))
        self.code_font_combo.currentFontChanged.connect(self.setup_preview_renderer)
        opts_row_fonts.addWidget(self.code_font_combo)

        opts_row_fonts.addWidget(QLabel("Size:"))
        self.code_font_size_spin = QSpinBox()
        self.code_font_size_spin.setRange(8, 36)
        self.code_font_size_spin.setValue(int(self.settings.value("code_font_size", 16)))
        self.code_font_size_spin.valueChanged.connect(self.setup_preview_renderer)
        opts_row_fonts.addWidget(self.code_font_size_spin)

        opts_row_fonts.addWidget(QLabel("Auto-fit Mode:"))
        self.autofit_combo = QComboBox()
        self.autofit_combo.addItems(AUTOFIT_MODES)
        self.autofit_combo.setCurrentText(self.settings.value("autofit_mode", AUTOFIT_MODES[0]))
        self.autofit_combo.currentTextChanged.connect(self.on_autofit_changed)
        self.autofit_combo.currentTextChanged.connect(self.setup_preview_renderer)
        opts_row_fonts.addWidget(self.autofit_combo)
        opts_row_fonts.addStretch()
        out_layout.addLayout(opts_row_fonts)

        # FPS + Bitrate + Safe Zone + Layout Bounds
        opts_row3 = QHBoxLayout()
        opts_row3.addWidget(QLabel("FPS:"))
        self.fps_combo = QComboBox()
        self.fps_combo.addItems([str(f) for f in FPS_PRESETS])
        self.fps_combo.setCurrentText(str(self.settings.value("fps", 30)))
        opts_row3.addWidget(self.fps_combo)

        opts_row3.addWidget(QLabel("Encoding Quality:"))
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems(list(BITRATE_PRESETS.keys()))
        self.bitrate_combo.setCurrentText(self.settings.value("bitrate_preset", "High"))
        opts_row3.addWidget(self.bitrate_combo)

        self.safe_zone_cb = QPushButton("Safe Zones (Shorts)")
        self.safe_zone_cb.setCheckable(True)
        self.safe_zone_cb.setChecked(self.settings.value("safe_zones", False, type=bool))
        self.safe_zone_cb.setToolTip("Overlay YouTube UI safe-zone guides (useful when designing Shorts).")
        self.safe_zone_cb.clicked.connect(self.setup_preview_renderer)
        opts_row3.addWidget(self.safe_zone_cb)

        self.show_bounds_cb = QPushButton("Show Layout Bounds")
        self.show_bounds_cb.setCheckable(True)
        self.show_bounds_cb.setChecked(False)
        self.show_bounds_cb.setToolTip("Draw colored boxes around all layout elements for debugging.")
        self.show_bounds_cb.clicked.connect(self.setup_preview_renderer)
        opts_row3.addWidget(self.show_bounds_cb)

        opts_row3.addStretch()
        out_layout.addLayout(opts_row3)

        # Read-only resolution display
        opts_row4 = QHBoxLayout()
        opts_row4.addWidget(QLabel("Resolution:"))
        self.res_label = QLabel("--")
        self.res_label.setStyleSheet("font-weight: bold; color: #007ACC; padding: 2px 6px;")
        opts_row4.addWidget(self.res_label)
        opts_row4.addStretch()
        out_layout.addLayout(opts_row4)

        self._width, self._height = dims_for(self.layout_combo.currentText(),
                                             self.quality_combo.currentText())

        root.addWidget(out_group)
        self.on_layout_or_quality_changed()

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
        self.preview_label.setText("Select a file to preview typing...")
        root.addWidget(self.preview_label, 1)

        self.apply_ui_theme(self.ui_theme_combo.currentText())

        self.on_autofit_changed(self.autofit_combo.currentText())

        self.load_files_from_folder()

    def on_autofit_changed(self, mode):
        self.code_font_size_spin.setEnabled(mode == "Off (Manual Size)")

    def apply_ui_theme(self, theme_name):
        if theme_name == "Light":
            pal = QApplication.style().standardPalette()
            pal.setColor(QPalette.Window, QColor(240, 240, 240))
            pal.setColor(QPalette.WindowText, Qt.black)
            pal.setColor(QPalette.Base, Qt.white)
            pal.setColor(QPalette.AlternateBase, QColor(233, 233, 233))
            pal.setColor(QPalette.ToolTipBase, Qt.white)
            pal.setColor(QPalette.ToolTipText, Qt.black)
            pal.setColor(QPalette.Text, Qt.black)
            pal.setColor(QPalette.Button, QColor(240, 240, 240))
            pal.setColor(QPalette.ButtonText, Qt.black)
            pal.setColor(QPalette.BrightText, Qt.red)
            pal.setColor(QPalette.Link, QColor(0, 120, 200))
            pal.setColor(QPalette.Highlight, QColor(0, 120, 200))
            pal.setColor(QPalette.HighlightedText, Qt.white)
            QApplication.instance().setPalette(pal)
            self.preview_label.setStyleSheet("background-color: #DDDDDD; border: 1px solid #AAAAAA;")
        else:
            pal = QPalette()
            pal.setColor(QPalette.Window, QColor(45, 45, 45))
            pal.setColor(QPalette.WindowText, Qt.white)
            pal.setColor(QPalette.Base, QColor(30, 30, 30))
            pal.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            pal.setColor(QPalette.ToolTipBase, Qt.white)
            pal.setColor(QPalette.ToolTipText, Qt.white)
            pal.setColor(QPalette.Text, Qt.white)
            pal.setColor(QPalette.Button, QColor(53, 53, 53))
            pal.setColor(QPalette.ButtonText, Qt.white)
            pal.setColor(QPalette.BrightText, Qt.red)
            pal.setColor(QPalette.Link, QColor(42, 130, 218))
            pal.setColor(QPalette.Highlight, QColor(42, 130, 218))
            pal.setColor(QPalette.HighlightedText, Qt.black)
            QApplication.instance().setPalette(pal)
            self.preview_label.setStyleSheet("background-color: #111122; border: 1px solid #2A2A40;")

    def on_layout_or_quality_changed(self, *_):
        layout = self.layout_combo.currentText()
        quality = self.quality_combo.currentText()
        w, h = dims_for(layout, quality)
        self._width, self._height = w, h
        self.res_label.setText(f"{w} × {h}  ({'16:9 Landscape' if w > h else '9:16 Portrait'})")

        self.safe_zone_cb.setEnabled("9:16" in layout)
        if "9:16" not in layout:
            self.safe_zone_cb.setChecked(False)

        self.setup_preview_renderer()

    def setup_preview_renderer(self):
        if not hasattr(self, 'preview_label'): return

        if self.worker_thread is not None and self.worker_thread.isRunning():
            self.preview_timer.stop()
            return

        selected_items = self.file_list.selectedItems()
        if not selected_items or not selected_items[0].text().endswith(".scd"):
            self.preview_timer.stop()
            self.preview_label.setText("Select a file to preview typing...")
            self.est_time_label.setText("0s")
            return

        filepath = selected_items[0].text()
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                sc_code = f.read()
        except:
            return

        cps = max(1, self.cps_spin.value())
        typing_natural = max(1.0, len(sc_code) / cps)

        behavior = self.audio_behavior_combo.currentText()
        mock_audio_dur = typing_natural
        typing_duration, total_duration, loop_audio, _ = compute_audio_plan(
            behavior, typing_natural, mock_audio_dur
        )

        self.est_time_label.setText(format_time_duration(total_duration))

        w, h = self._width, self._height
        mock_audio = MockAudioData(total_duration)

        self.preview_renderer = FrameRenderer(
            mock_audio, sc_code, w, h, 30,
            self.type_style_combo.currentText(), self.viz_style_combo.currentText(),
            self.safe_zone_cb.isChecked(), typing_duration, total_duration,
            self.code_font_combo.currentFont().family(), self.code_font_size_spin.value(),
            self.autofit_combo.currentText(), self.video_theme_combo.currentText(),
            self.show_bounds_cb.isChecked(), loop_audio=loop_audio,
            syntax_theme=self.syntax_theme_combo.currentText()
        )

        self.preview_frame_idx = 0
        if not self.preview_timer.isActive():
            self.preview_timer.start(33)

    def update_preview_frame(self):
        if not self.preview_renderer:
            return

        img = self.preview_renderer.render_frame_to_canvas(self.preview_frame_idx)
        scaled = img.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(QPixmap.fromImage(scaled))

        self.preview_frame_idx += 1
        total_frames = int(self.preview_renderer.total_duration * self.preview_renderer.fps) + 1
        if self.preview_frame_idx >= total_frames:
            self.preview_frame_idx = 0

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

        self.preview_timer.stop()

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

        base_name = os.path.splitext(filename)[0]
        out_mp4 = os.path.join(self.out_dir_edit.text().strip(), f"{base_name}_viz.mp4")

        fps = int(self.fps_combo.currentText())
        w, h = self._width, self._height
        cps = self.cps_spin.value()
        code_font_family = self.code_font_combo.currentFont().family()
        code_font_size = self.code_font_size_spin.value()
        autofit_mode = self.autofit_combo.currentText()
        v_theme = self.video_theme_combo.currentText()
        audio_behavior = self.audio_behavior_combo.currentText()
        syntax_theme = self.syntax_theme_combo.currentText()

        self.worker_thread = QThread()
        self.worker = PipelineWorker(
            sc_code, out_mp4, fps=fps, width=w, height=h,
            typing_style=self.type_style_combo.currentText(),
            visual_style=self.viz_style_combo.currentText(),
            bitrate_preset=self.bitrate_combo.currentText(),
            show_safe_zones=self.safe_zone_cb.isChecked(),
            cps=cps,
            code_font_family=code_font_family,
            code_font_size=code_font_size,
            autofit_mode=autofit_mode,
            video_theme=v_theme,
            audio_behavior=audio_behavior,
            show_bounds=self.show_bounds_cb.isChecked(),
            syntax_theme=syntax_theme
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
        self.duration_label.setText(f"Estimated Duration: {format_time_duration(duration)} ({frames} frames)")

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
        self.setup_preview_renderer()

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
        self.settings.setValue("quality", self.quality_combo.currentText())
        self.settings.setValue("typing_style", self.type_style_combo.currentText())
        self.settings.setValue("cps", self.cps_spin.value())
        self.settings.setValue("audio_behavior", self.audio_behavior_combo.currentText())
        self.settings.setValue("visual_style", self.viz_style_combo.currentText())
        self.settings.setValue("fps", int(self.fps_combo.currentText()))
        self.settings.setValue("bitrate_preset", self.bitrate_combo.currentText())
        self.settings.setValue("safe_zones", self.safe_zone_cb.isChecked())
        self.settings.setValue("code_font_family", self.code_font_combo.currentFont().family())
        self.settings.setValue("code_font_size", self.code_font_size_spin.value())
        self.settings.setValue("autofit_mode", self.autofit_combo.currentText())
        self.settings.setValue("video_theme", self.video_theme_combo.currentText())
        self.settings.setValue("ui_theme", self.ui_theme_combo.currentText())
        self.settings.setValue("syntax_theme", self.syntax_theme_combo.currentText())
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