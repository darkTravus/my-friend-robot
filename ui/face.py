"""Visage du robot dessiné avec Pillow (une image par appel de render()).
Pillow plutôt que pygame : les pilotes d'écrans SPI du Raspberry Pi (st7789, luma.lcd...) acceptent directement
des images Pillow. Le même code servira donc sur PC (fenêtre) et sur l'écran du robot.

Coût de calcul : quelques formes simples par image (< 1 ms) ; aucune IA locale.
Modes : idle (veille) | listening (3 barres) | thinking | speaking (yeux qui rebondissent avec la voix)
Émotions : neutre, joie, amusement, surprise, curiosite, tristesse, doute, sommeil."""
import math
import random
import time

from PIL import Image, ImageDraw

W, H = 320, 240                      # taille logique de l'écran (écran SPI 2,4" typique)
BG = (10, 16, 30)
CYAN = (70, 215, 255)
CYAN_DIM = (28, 80, 110)
WHITE = (246, 248, 252)
WHITE_DIM = (150, 165, 190)
INK = (16, 20, 36)
PINK = (255, 130, 150)
TEAR = (120, 190, 255)
EYE_CX = (98, 222)
EYE_CY = 112
EYE_W, EYE_H = 78, 104

# Paramètres continus (lissés d'une image à l'autre) et indicateurs (arc, laugh, tear) par émotion
_BASE = dict(size=1.0, pupil=1.0, lid=0.0, slant=0.0, brow_y=0.0, brow_tilt=0.0, cheek=0.0, asym=0.0)
PRESETS = {
    "neutre":    dict(),
    "joie":      dict(cheek=1.0, brow_y=-3, arc=True),
    "amusement": dict(cheek=0.6, laugh=True),
    "surprise":  dict(size=1.22, pupil=0.5, brow_y=-16),
    "curiosite": dict(asym=1.0, brow_y=-4, gaze=(0.7, -0.6)),
    "tristesse": dict(lid=0.34, slant=1.0, brow_tilt=1.0, brow_y=4, pupil=0.9, tear=True, gaze=(0.0, 0.85)),
    "doute":     dict(lid=0.28, slant=-0.4, brow_tilt=-0.6, brow_y=2, pupil=0.8, gaze=(0.85, 0.15)),
}
CONTINUOUS = tuple(_BASE)


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Face:
    def __init__(self, scale: int = 2):
        self.k = scale                       # facteur de suréchantillonnage (anti-crénelage) ; 1 = plus rapide
        self.bars = [0.0, 0.0, 0.0]
        self.p = dict(_BASE)                 # paramètres d'expression actuels (lissés)
        self.mode_size = 0.75
        self.bounce = 0.0
        self.gaze = [0.0, 0.0]
        self._gaze_target = [0.0, 0.0]
        self._gaze_change = 0.0
        self._blink_start = None
        self._next_blink = time.time() + 2.5
        self._last = time.time()

    # ------------------------------------------------------------------ utilitaires
    @staticmethod
    def _approach(cur, target, rate_up, rate_down, dt):
        rate = rate_up if target > cur else rate_down
        return cur + (target - cur) * (1 - math.exp(-rate * dt))

    def _blink(self, now):
        """1 = yeux ouverts, ~0 = fermés."""
        if self._blink_start is None:
            if now >= self._next_blink:
                self._blink_start = now
            return 1.0
        p = (now - self._blink_start) / 0.18
        if p >= 1.0:
            self._blink_start = None
            self._next_blink = now + random.uniform(2.5, 5.5)
            return 1.0
        return max(0.08, 1.0 - math.sin(math.pi * p))

    def _wander(self, now, amount):
        if now >= self._gaze_change:
            self._gaze_target = [random.uniform(-1, 1) * amount, random.uniform(-0.6, 0.6) * amount]
            self._gaze_change = now + random.uniform(1.2, 3.0)

    # ------------------------------------------------------------------ dessin
    def render(self, mode: str, bands, out_level: float = 0.0, emotion: str = "neutre") -> Image.Image:
        now = time.time()
        dt = min(0.2, max(0.001, now - self._last))
        self._last = now
        k = self.k
        img = Image.new("RGB", (W * k, H * k), BG)
        d = ImageDraw.Draw(img)

        if mode == "listening":
            self._draw_bars(d, bands, dt)
            return img
        if emotion == "sommeil":
            self._draw_sleep(d, now)
            return img

        preset = PRESETS.get(emotion, PRESETS["neutre"]) if mode != "thinking" else PRESETS["neutre"]
        target = {**_BASE, **{key: preset[key] for key in CONTINUOUS if key in preset}}
        for key in CONTINUOUS:
            self.p[key] = self._approach(self.p[key], target[key], 9, 9, dt)

        if mode == "thinking":
            self._gaze_target = [0.7, -0.8]
        elif preset.get("gaze"):
            self._gaze_target = list(preset["gaze"])
        else:
            self._wander(now, 0.5 if mode == "idle" else 0.35)
        for i in (0, 1):
            self.gaze[i] = self._approach(self.gaze[i], self._gaze_target[i], 6, 6, dt)

        base = {"idle": 0.75, "thinking": 0.9, "speaking": 1.0}.get(mode, 0.8)
        self.mode_size = self._approach(self.mode_size, base, 8, 8, dt)
        self.bounce = self._approach(self.bounce, out_level if mode == "speaking" else 0.0, 30, 10, dt)
        self._draw_eyes(d, now, mode, emotion if mode != "thinking" else "neutre", preset)
        if mode == "thinking":
            self._draw_dots(d, now)
        return img

    def _draw_bars(self, d, bands, dt):
        k = self.k
        xs, bw, min_h, max_h, cy = (110, 160, 210), 38, 26, 170, 120
        for i in range(3):
            level = bands[i] if i < len(bands) else 0.0
            self.bars[i] = self._approach(self.bars[i], level, 22, 7, dt)     # monte vite, retombe doucement
            h = min_h + self.bars[i] * (max_h - min_h)
            color = _mix(CYAN_DIM, CYAN, self.bars[i])
            d.rounded_rectangle([(xs[i] - bw / 2) * k, (cy - h / 2) * k, (xs[i] + bw / 2) * k, (cy + h / 2) * k],
                                radius=bw / 2 * k, fill=color)

    def _draw_eyes(self, d, now, mode, emotion, preset):
        k, p = self.k, self.p
        openness = self._blink(now)
        white = WHITE if mode != "idle" else _mix(WHITE_DIM, WHITE, 0.4)
        arc, laugh, tear = preset.get("arc"), preset.get("laugh"), preset.get("tear")
        size = self.mode_size * p["size"]
        sx = size * (1 - 0.05 * self.bounce)
        sy = size * (1 + 0.14 * self.bounce)
        shake = math.sin(now * 32) * 2.5 if (laugh and mode == "speaking") else 0.0
        lw = max(1, int(9 * k * size))

        for idx, cx in enumerate(EYE_CX):
            s = 1 if idx == 0 else -1                     # +1 œil gauche, -1 œil droit (symétrie)
            grow = 1 + 0.18 * p["asym"] * (idx == 1)      # curiosité : un œil plus grand
            w, h = EYE_W * sx * grow, EYE_H * sy * grow
            cy = EYE_CY - self.bounce * 6 + shake
            if arc:                                       # joie : yeux en "^"
                d.arc([(cx - w * 0.42) * k, (cy - h * 0.18) * k, (cx + w * 0.42) * k, (cy + h * 0.32) * k],
                      205, 335, fill=white, width=lw)
            elif laugh:                                   # amusement : yeux en "> <"
                a, b = w * 0.34, h * 0.2
                pts = [(cx - s * a, cy - b), (cx + s * a * 0.7, cy), (cx - s * a, cy + b)]
                d.line([(x * k, y * k) for x, y in pts], fill=white, width=lw, joint="curve")
            else:
                hh = h * openness
                box = [(cx - w / 2) * k, (cy - hh / 2) * k, (cx + w / 2) * k, (cy + hh / 2) * k]
                d.ellipse(box, fill=white)
                if openness > 0.35:                       # grande pupille de dessin animé + reflet
                    pw, ph = w * 0.56 * p["pupil"], hh * 0.6 * p["pupil"]
                    px = cx + self.gaze[0] * (w - pw) * 0.42
                    py = cy + self.gaze[1] * (hh - ph) * 0.42
                    d.ellipse([(px - pw / 2) * k, (py - ph / 2) * k, (px + pw / 2) * k, (py + ph / 2) * k], fill=INK)
                    r = max(1.0, pw * 0.17)
                    d.ellipse([(px - pw * 0.18 - r) * k, (py - ph * 0.2 - r) * k,
                               (px - pw * 0.18 + r) * k, (py - ph * 0.2 + r) * k], fill=WHITE)
                if p["lid"] > 0.02:                       # paupière : triste (bords extérieurs bas) ou dubitative
                    y0 = cy - hh / 2
                    yl = y0 + hh * p["lid"] + s * p["slant"] * hh * 0.18
                    yr = y0 + hh * p["lid"] - s * p["slant"] * hh * 0.18
                    d.polygon([((cx - w / 2 - 2) * k, (y0 - 3) * k), ((cx + w / 2 + 2) * k, (y0 - 3) * k),
                               ((cx + w / 2 + 2) * k, yr * k), ((cx - w / 2 - 2) * k, yl * k)], fill=BG)
                if tear and idx == 0:                     # larme qui glisse
                    t = (now * 0.6) % 1.0
                    ty = cy + hh / 2 - 4 + t * 34
                    d.ellipse([(cx + w * 0.2 - 5) * k, (ty - 7) * k, (cx + w * 0.2 + 5) * k, (ty + 7) * k], fill=TEAR)
            if p["cheek"] > 0.05:                         # joues roses
                cc = _mix(BG, PINK, 0.55 * p["cheek"])
                d.ellipse([(cx - 22) * k, (EYE_CY + 34) * k, (cx + 22) * k, (EYE_CY + 52) * k], fill=cc)
            if mode == "speaking" or emotion != "neutre":  # sourcils (bout intérieur plus haut si tilt > 0)
                by = EYE_CY - EYE_H * sy / 2 - 14 + p["brow_y"] - self.bounce * 8 - (8 * p["asym"] if idx == 1 else 0)
                tilt = 3 + 7 * p["brow_tilt"]
                d.line([((cx - w * 0.42) * k, (by + s * tilt) * k), ((cx + w * 0.42) * k, (by - s * tilt) * k)],
                       fill=WHITE_DIM, width=max(1, int(4 * k)))

    def _draw_sleep(self, d, now):
        k = self.k
        for cx in EYE_CX:                                  # yeux fermés "‿"
            d.arc([(cx - 32) * k, (EYE_CY - 16) * k, (cx + 32) * k, (EYE_CY + 22) * k], 25, 155,
                  fill=WHITE_DIM, width=int(6 * k))
        for i in range(3):                                 # "z" qui montent et s'estompent
            ph = (now * 0.3 + i / 3) % 1.0
            s = 8 + 12 * ph
            x, y = 236 + ph * 28, 92 - ph * 58
            col = _mix(CYAN, BG, ph)
            d.line([(x * k, y * k), ((x + s) * k, y * k), (x * k, (y + s) * k), ((x + s) * k, (y + s) * k)],
                   fill=col, width=max(1, int(2.5 * k)))

    def _draw_dots(self, d, now):
        k = self.k
        for i in range(3):
            pulse = (math.sin(now * 5 - i * 0.9) + 1) / 2
            r = 5 + 3 * pulse
            x = 160 + (i - 1) * 24
            d.ellipse([(x - r) * k, (205 - r) * k, (x + r) * k, (205 + r) * k], fill=_mix(CYAN_DIM, CYAN, pulse))
