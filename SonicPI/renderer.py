from __future__ import annotations
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
            a = self._rng.uniform(0, 2 * math.pi)
            s = self._rng.uniform(0.5, 3.0) * (0.5 + strength)
            self.particles.append(Particle(cx, cy, math.cos(a)*s, math.sin(a)*s, self._rng.uniform(0.3, 0.8), self._rng.uniform(2, 6), self._rng.choice(colors)))
    def update(self, dt):
        surv = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0: continue
            p.x += p.vx; p.y += p.vy; p.vy += 0.05; p.vx *= 0.98
            surv.append(p)
        self.particles = surv
    def draw(self, p: QPainter, colors):
        p.setPen(Qt.PenStyle.NoPen)
        for prt in self.particles:
            a = prt.life / prt.max_life
            c = colors[prt.color_idx % len(colors)]
            r = prt.size * a
            if r < 0.5: continue
            grad = QRadialGradient(QPointF(prt.x, prt.y), r * 2)
            grad.setColorAt(0, QColor(c[0], c[1], c[2], int(200 * a)))
            grad.setColorAt(1, QColor(c[0], c[1], c[2], 0))
            p.setBrush(QBrush(grad)); p.drawEllipse(QPointF(prt.x, prt.y), r * 2, r * 2)

class FrameRenderer:
    def __init__(self):
        self.frames: List[FrameState] = []
        self.cf: int = 0
        self.code: str = ""
        self.vw: int = 1920; self.vh: int = 1080
        self.theme: Theme = None; self.preset: Preset = None; self.cfg: AudioEngineConfig = None
        self.total_time: float = 0.0
        self.particles = ParticleSystem()
        self._token_cache: Dict[str, List[Token]] = {}

    def apply_config(self, cfg: AudioEngineConfig):
        from core import ThemeRegistry, PresetRegistry
        self.cfg = cfg
        self.theme = ThemeRegistry.get(cfg.theme_name)
        self.preset = PresetRegistry.get(cfg.preset_name)
        self.vw, self.vh = self.preset.width, self.preset.height

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
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        img.fill(self.theme.color("bg1"))
        if self.frames:
            self.cf = min(fi, len(self.frames) - 1)
            self._draw(p, img.width(), img.height())
        p.end()

    def _draw(self, p: QPainter, w: int, h: int):
        if not self.frames or not self.cfg: p.fillRect(0, 0, w, h, self.theme.color("bg1")); return
        v = self.frames[min(self.cf, len(self.frames) - 1)]
        
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0, self.theme.color("bg1")); grad.setColorAt(1, self.theme.color("bg2"))
        p.fillRect(0, 0, w, h, grad)

        if self.cfg.particles_enabled:
            if v.beat_on:
                self.particles.emit_burst(w//2, h//2, 10, v.beat_strength, colors=(self.theme.w1, self.theme.w2))
            self.particles.update(1.0 / 30.0)
            self.particles.draw(p, [self.theme.w1, self.theme.w2, self.theme.accent])

        if self.cfg.beat_flash and v.beat_on:
            p.fillRect(0, 0, w, h, QColor(255, 255, 255, int(50 * v.beat_strength)))

        if self.preset.layout == LayoutMode.HORIZONTAL:
            cw = int(w * self.preset.split)
            code_rect, wave_rect = QRectF(0, 0, cw, h), QRectF(cw, 0, w - cw, h)
        else:
            ch = int(h * self.preset.split)
            code_rect, wave_rect = QRectF(0, 0, w, ch), QRectF(0, ch, w, h - ch)

        self._draw_code(p, code_rect, v)
        self._draw_wave(p, wave_rect, v)
        
        if self.cfg.show_progress_bar and self.total_time > 0:
            progress = v.time / self.total_time
            p.fillRect(0, h - 5, int(w * progress), 5, self.theme.color("accent"))

    def _draw_code(self, p: QPainter, rect: QRectF, v: FrameState):
        x, y, pw, ph = int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())
        p.fillRect(x, y, pw, ph, QColor(self.theme.bg1[0]+5, self.theme.bg1[1]+5, self.theme.bg1[2]+5, 230))
        
        fnt_size = self.cfg.font_size_override if self.cfg.font_size_override > 0 else 14
        fnt = QFont("Consolas", fnt_size); fnt.setStyleHint(QFont.StyleHint.Monospace); p.setFont(fnt)
        fm = QFontMetrics(fnt); lh = fm.height() + 4
        
        vis = self.code[:v.char_index]
        lines = vis.split("\n")
        for i, line in enumerate(lines):
            ly = y + 20 + i * lh
            if ly > y + ph - lh: break
            tokens = self._token_cache.get(line) or (self._token_cache.setdefault(line, tokenize_ruby_line(line)))
            tx = x + 40
            
            if self.cfg.show_code_glow:
                p.setPen(QPen(self.theme.color("accent", 80)))
                for tok in tokens:
                    p.drawText(tx + 1, ly + fm.ascent() + 3, tok.text)
                    tx += fm.horizontalAdvance(tok.text)
                tx = x + 40
                
            for tok in tokens:
                p.setPen(self.theme.color(TOKEN_COLOR_MAP.get(tok.kind, "txt")))
                p.drawText(tx, ly + fm.ascent() + 2, tok.text)
                tx += fm.horizontalAdvance(tok.text)

    def _draw_wave(self, p: QPainter, rect: QRectF, v: FrameState):
        vx, vy, vw, vh = int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())
        p.fillRect(vx, vy, vw, vh, QColor(self.theme.bg2[0]+2, self.theme.bg2[1]+2, self.theme.bg2[2]+2, 200))
        cy = vy + vh // 2
        
        if self.cfg.show_spectrum:
            bars = v.spectrum
            n = len(bars)
            if n > 0:
                bw = vw / n
                for i, b in enumerate(bars):
                    bh = b * (vh * 0.3)
                    p.fillRect(vx + i * bw, vy + vh - bh, bw - 2, bh, self.theme.color("accent", 150))

        path = QPainterPath()
        wf = v.waveform
        n = len(wf)
        if n == 0: return
        for i in range(n):
            px = vx + (i / max(1, n - 1)) * vw
            py = cy - wf[i] * (vh * 0.4) * self.cfg.wave_amplitude
            if i == 0: path.moveTo(px, py)
            else: path.lineTo(px, py)
            
        if self.cfg.mirror_waveform:
            mirror_path = QPainterPath()
            for i in range(n):
                px = vx + (i / max(1, n - 1)) * vw
                py = cy + wf[i] * (vh * 0.4) * self.cfg.wave_amplitude
                if i == 0: mirror_path.moveTo(px, py)
                else: mirror_path.lineTo(px, py)
            p.setPen(QPen(self.theme.color("w2"), 2))
            p.drawPath(mirror_path)

        if self.cfg.fill_waveform:
            fill_path = QPainterPath(path)
            fill_path.lineTo(vx + vw, cy)
            fill_path.lineTo(vx, cy)
            grad = QLinearGradient(vx, vy, vx, vy + vh)
            grad.setColorAt(0, self.theme.color("w1", 100))
            grad.setColorAt(1, self.theme.color("w1", 0))
            p.fillPath(fill_path, QBrush(grad))

        p.setPen(QPen(self.theme.color("w1"), 2))
        p.drawPath(path)
        
        if self.cfg.vu_meter:
            lh = v.peak_l * (vh * 0.45)
            p.fillRect(vx + 10, cy - lh, 6, lh * 2, self.theme.color("accent"))
            rh = v.peak_r * (vh * 0.45)
            p.fillRect(vx + vw - 16, cy - rh, 6, rh * 2, self.theme.color("accent"))