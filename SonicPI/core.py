from __future__ import annotations
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
    typing_speed: float = 28.0
    wave_amplitude: float = 0.42
    particles_enabled: bool = True
    line_highlight: bool = True
    vu_meter: bool = True
    beat_sensitivity: float = 0.5
    normalize_audio: bool = True
    mirror_waveform: bool = True
    fill_waveform: bool = True
    beat_flash: bool = True
    show_spectrum: bool = False
    show_progress_bar: bool = True
    show_code_glow: bool = True
    font_size_override: int = 0
    particle_count: int = 80
    theme_name: str = "Midnight Blue"
    preset_name: str = "YouTube (1920x1080)"
    match_typing_to_music: bool = True

    def to_dict(self) -> Dict[str, Any]: return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AudioEngineConfig":
        valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid)

KEYWORDS = frozenset({'use_bpm', 'use_synth', 'live_loop', 'with_fx', 'play', 'sample', 'sleep', 'do', 'end', 'chord', 'scale', 'release', 'amp', 'attack', 'decay', 'sustain', 'cutoff', 'pan', 'if', 'else', 'elsif', 'unless', 'while', 'until', 'def', 'return', 'true', 'false', 'nil'})
SYNTH_SET = frozenset({'prophet', 'pluck', 'tb303', 'dsaw', 'fm', 'piano', 'blade', 'saw', 'sine', 'square', 'noise'})
FX_SET = frozenset({'reverb', 'echo', 'flanger', 'distortion', 'compressor', 'lpf', 'hpf', 'wobble'})
SAMPLE_SET = frozenset({'bd_haus', 'drum_cymbal_closed', 'drum_heavy_kick', 'drum_snare_soft', 'elec_hi_snare', 'elec_lo_snare', 'perc_snap', 'perc_bell'})

class ThemeRegistry:
    _themes: Dict[str, Theme] = {}
    @classmethod
    def register(cls, t: Theme) -> None: cls._themes[t.name] = t
    @classmethod
    def get(cls, name: str) -> Theme: return cls._themes[name]
    @classmethod
    def names(cls) -> List[str]: return list(cls._themes.keys())
    @classmethod
    def default(cls) -> Theme: return next(iter(cls._themes.values()))

ThemeRegistry.register(Theme("Midnight Blue", (15,15,28), (10,10,20), (0,255,180), (140,110,255), (0,200,255), (198,120,221), (219,191,130), (209,154,102), (98,114,164), (171,178,191), (152,195,121), (0,255,180)))

class PresetRegistry:
    _presets: Dict[str, Preset] = {}
    @classmethod
    def register(cls, p: Preset) -> None: cls._presets[p.name] = p
    @classmethod
    def get(cls, name: str) -> Preset: return cls._presets[name]
    @classmethod
    def names(cls) -> List[str]: return list(cls._presets.keys())
    @classmethod
    def default(cls) -> Preset: return next(iter(cls._presets.values()))

PresetRegistry.register(Preset("YouTube (1920x1080)", 1920, 1080, LayoutMode.HORIZONTAL, 0.48))
PresetRegistry.register(Preset("TikTok (1080x1920)", 1080, 1920, LayoutMode.VERTICAL, 0.55))

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