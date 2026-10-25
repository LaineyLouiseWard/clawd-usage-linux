"""Themed scenes Clawd walks on: a static backdrop plus a 12-second loop of moving
things (bats, snow, aurora...). Logical pixels; the ground is the last GROUND rows.

Port of art/Pix.kt and art/Scenes.kt from Pinch (https://github.com/YoussefAbdelkawy/Pinch,
MIT, see LICENSE-pinch), whose Halloween scene follows clawd-usage-winwidget.
"""

import math
import random
import zlib
from array import array

from PyQt6.QtGui import QImage

H = 30
GROUND = 3
LOOP = 120        # frames per loop
FRAME_S = 0.1     # seconds per frame


def c(h):
    """'#RRGGBB' or '#AARRGGBB' -> ARGB int."""
    h = h.lstrip('#')
    return int(h, 16) | 0xFF000000 if len(h) == 6 else int(h, 16)


def m(**kw):
    return {k: c(v) for k, v in kw.items()}


def with_alpha(argb, a):
    return (max(0, min(255, int(255 * a))) << 24) | (argb & 0xFFFFFF)


def mix(a, b, t):
    out = 0
    for sh in (24, 16, 8, 0):
        out |= int(((a >> sh) & 0xFF) * (1 - t) + ((b >> sh) & 0xFF) * t) << sh
    return out


def blend(dst, src):
    sa = (src >> 24) / 255.0
    da = (dst >> 24) / 255.0
    oa = sa + da * (1 - sa)
    if oa <= 0:
        return 0
    out = int(oa * 255) << 24
    for sh in (16, 8, 0):
        s = (src >> sh) & 0xFF
        d = (dst >> sh) & 0xFF
        out |= max(0, min(255, int((s * sa + d * da * (1 - sa)) / oa))) << sh
    return out


def kround(x):
    """Kotlin's roundToInt: half rounds up."""
    return int(math.floor(x + 0.5))


def noise(a, b):
    """Pinch's cheap deterministic noise, in 32-bit integer arithmetic."""
    def i32(v):
        v &= 0xFFFFFFFF
        return v - (1 << 32) if v & 0x80000000 else v
    h = i32(a * 374761393 + b * 668265263)
    h = i32((h ^ ((h & 0xFFFFFFFF) >> 13)) * 1274126177)
    return (h ^ ((h & 0xFFFFFFFF) >> 16)) & 0x7FFFFFFF


class Pix:
    """A tiny canvas of ARGB logical pixels."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.px = [0] * (w * h)

    def set(self, x, y, argb):
        if x < 0 or y < 0 or x >= self.w or y >= self.h:
            return
        a = argb >> 24
        if a == 0:
            return
        i = y * self.w + x
        self.px[i] = argb if a == 255 else blend(self.px[i], argb)

    def rect(self, x, y, rw, rh, argb):
        for yy in range(y, y + rh):
            for xx in range(x, x + rw):
                self.set(xx, yy, argb)

    def fill(self, argb):
        self.px = [argb] * (self.w * self.h)

    def vgradient(self, y0, y1, top, bottom):
        n = max(1, y1 - y0)
        for y in range(y0, y1):
            col = mix(top, bottom, (y - y0) / n)
            for x in range(self.w):
                self.set(x, y, col)

    def art(self, rows, colors, x, y, flip_x=False):
        for ry, row in enumerate(rows):
            for rx, ch in enumerate(row):
                col = colors.get(ch)
                if col is None:
                    continue
                dx = len(row) - 1 - rx if flip_x else rx
                self.set(x + dx, y + ry, col)

    def glow(self, cx, cy, r, argb):
        a0 = argb >> 24
        for y in range(cy - r, cy + r + 1):
            for x in range(cx - r, cx + r + 1):
                d = math.hypot(x - cx, y - cy) / r
                if d >= 1:
                    continue
                a = int(a0 * (1 - d) * (1 - d))
                self.set(x, y, (a << 24) | (argb & 0xFFFFFF))

    def copy(self):
        p = Pix(self.w, self.h)
        p.px = list(self.px)
        return p

    def draw_into(self, dst, x, y):
        for yy in range(self.h):
            for xx in range(self.w):
                v = self.px[yy * self.w + xx]
                if v:
                    dst.set(x + xx, y + yy, v)

    def to_qimage(self):
        data = array('I', self.px).tobytes()
        return QImage(data, self.w, self.h, self.w * 4, QImage.Format.Format_ARGB32).copy()


# ------------------------------------------------------------------ sprites ----
MOON = ['...mmmmm...', '..mmmmmmm..', '.mmmmmmcmm.', 'mmccmmmmmmm', 'mmccmmmmmmm',
        'mmmmmmmmccm', 'mmmmmmmmccm', '.mmmcmmmmm.', '..mmmmmmm..', '...mmmmm...']
SUN = ['..ssss..', '.ssssss.', 'ssssssss', 'ssssssss', 'ssssssss', 'ssssssss', '.ssssss.', '..ssss..']
TREE_DEAD = ['.t.....t....', '..t...t..t..', 't..t.t..t...', '.t..tt.t....', '..t.tttt....',
             '...ttt......', '....tt......', '....tt......', '....tt......', '...tttt.....']
TOMB = ['..sss..', '.sssss.', 'sssdsss', 'ssdddss', 'sssdsss', 'sssdsss', 'sssssss', 'sssssss']
CROSS = ['..c..', 'ccccc', '..c..', '..c..', '..c..', '..c..']
PUMPKIN = ['....g....', '.ooogooo.', 'oyyoooyyo', 'ooyoooyoo', 'ooooooooo', 'oyoyyyoyo', '.oyyyyyo.']
BAT_UP = ['b.........b', 'bb..b.b..bb', '.bbbrbrbbb.', '....bbb....']
BAT_DOWN = ['....b.b....', '..bbrbrbb..', '.bbbbbbbbb.', 'bb.......bb']
GHOST = ['..www..', '.wwwww.', 'wkwwkww', 'wwwwwww', 'wwwwwww', 'w.w.w.w']
XMAS_TREE = ['....y....', '...ggg...', '..ggggg..', '...ggg...', '..ggggg..', '.ggggggg.',
             '..ggggg..', '.ggggggg.', 'ggggggggg', '....b....', '....b....']
SNOWMAN = ['..kkk..', '..kkk..', '.kkkkk.', '..www..', '..wkw..', '..wow..', '.wwwww.',
           'wwwkwww', 'wwwwwww', 'wwwkwww', '.wwwww.']
PRESENT = ['..r.r..', '...r...', 'ggrrrgg', 'ggrrrgg', 'rrrrrrr', 'ggrrrgg', 'ggrrrgg']
HEART = ['.hh.hh.', 'hhhhhhh', 'hhhhhhh', '.hhhhh.', '..hhh..', '...h...']
HEART_S = ['h.h', 'hhh', '.h.']
TULIP = ['p.p.p', 'ppppp', '.ppp.', '..g..', 'g.g..', '.gg..', '..g..']
DAISY = ['.w.', 'wyw', '.w.', '.g.', '.g.']
BFLY_A = ['pp.pp', 'ppkpp', '.pkp.', 'pp.pp']
BFLY_B = ['.....', 'ppkpp', 'ppkpp', '.....']
PALM = ['..gg.gg..', '.g..g..g.', 'g..ggg..g', '....t....', '....t....', '...t.....',
        '...t.....', '...t.....', '..t......', '..t......', '..tt.....']
GULL_A = ['w...w', '.w.w.', '..w..']
GULL_B = ['.....', 'ww.ww', '..w..']
PLANET = ['......pppp......', '....pppppppp....', 'rr.pppppqqpppp.r', '.rrrrrrrrrrrrrr.',
          '...pppppppppp...', '....pppppppp....', '......pppp......']
CORAL = ['p.p.p', 'p.p.p', '.ppp.', '..p..', '..p..']
FISH = ['.oo.o', 'ooooo', '.oo.o']
SKYLINE = [
    '......bbb.............bbbb...........bbb......',
    '......bbb....bbbbb....bbbb...bbb.....bbb......',
    '..bb..bbb....bbbbb....bbbb...bbb..bb.bbb..bb..',
    '..bb..bbbbb..bbbbb.bbbbbbb...bbbbbbb.bbbbbbb..',
    'bbbbbbbbbbb..bbbbbbbbbbbbbbb.bbbbbbbbbbbbbbbbb',
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
]


def sand(scene):
    """Colour of the mound when Clawd burrows."""
    return {'christmas': '#E2E8F0', 'halloween': '#3F2F52', 'space': '#6B7280',
            'cyberpunk': '#334155', 'spring': '#65A30D', 'oled': '#27272A',
            'midnight': '#1E3A5F', 'valentine': '#DB2777'}.get(scene, '#D6B98C')


def seed(scene, k=1, b=0):
    return random.Random(zlib.crc32(scene.encode()) * k + b)


def stars(p, r, max_y, color, density=0.03):
    n = int(p.w * max_y * density / 3)
    for _ in range(n):
        x = r.randrange(p.w)
        y = r.randrange(max(1, max_y))
        p.set(x, y, with_alpha(color, 0.35 + r.random() * 0.5))


def ground(p, r, base, speck, top=0):
    gy = H - GROUND + top
    p.rect(0, gy, p.w, H - gy, base)
    for x in range(p.w):
        if r.randrange(4) == 0:
            p.set(x, gy + 1 + r.randrange(GROUND - 1 - top), speck)
        if top == 0 and r.randrange(6) == 0:
            p.set(x, gy, speck)


# ----------------------------------------------------------------- backdrop ----

def background(scene, w, hour):
    p = Pix(w, H)
    r = seed(scene)
    night = hour < 7 or hour >= 19
    gy = H - GROUND
    if scene == 'halloween':
        p.vgradient(0, gy, c('#120B1C'), c('#2A1D38'))
        stars(p, r, gy - 8, c('#C4B5FD'))
        p.glow(w - 22, 8, 12, c('#80FDBA74'))
        p.art(MOON, m(m='#FDE68A', c='#F5C66B'), w - 28, 3)
        p.art(TREE_DEAD, m(t='#5B4A66'), int(w * 0.08), gy - 10)
        p.art(TOMB, m(s='#6B6478', d='#453E52'), int(w * 0.31), gy - 8)
        p.art(CROSS, m(c='#6B6478'), int(w * 0.40), gy - 6)
        p.art(['.sssss.', 'sssssss', 'sdsdsds', 'sssssss', 'sssssss'], m(s='#6B6478', d='#453E52'),
              int(w * 0.66), gy - 5)
        for fx in (0.22, 0.56, 0.86):
            x = int(w * fx)
            p.glow(x + 4, gy - 4, 8, c('#70FB923C'))
            p.art(PUMPKIN, m(o='#EA580C', g='#4D7C0F', y='#7C2D12'), x, gy - 7)
        ground(p, r, c('#2E1F3D'), c('#3F2F52'))
    elif scene == 'christmas':
        p.vgradient(0, gy, c('#081226'), c('#1E3A5F'))
        stars(p, r, gy - 10, c('#E0F2FE'))
        p.glow(w - 20, 7, 9, c('#60E0F2FE'))
        p.art(MOON, m(m='#F1F5F9', c='#CBD5E1'), w - 26, 2)
        p.art(XMAS_TREE, m(g='#15803D', y='#FDE047', b='#78350F'), int(w * 0.12), gy - 11)
        p.art(PRESENT, m(r='#DC2626', g='#16A34A'), int(w * 0.12) + 9, gy - 7)
        p.art(SNOWMAN, m(k='#111827', w='#F8FAFC', o='#F97316'), int(w * 0.72), gy - 11)
        p.art(PRESENT, m(r='#2563EB', g='#FBBF24'), int(w * 0.84), gy - 7)
        ground(p, r, c('#E2E8F0'), c('#CBD5E1'))
    elif scene == 'valentine':
        p.vgradient(0, gy, c('#2A0A1F'), c('#6B1D45'))
        stars(p, r, gy - 8, c('#FBCFE8'))
        p.glow(w - 20, 9, 11, c('#70F472B6'))
        p.art(HEART, m(h='#F43F5E'), w - 24, 5)
        for fx in (0.1, 0.35, 0.62, 0.9):
            p.art(DAISY, m(w='#FBCFE8', y='#F43F5E', g='#65A30D'), int(w * fx), gy - 5)
        ground(p, r, c('#9D174D'), c('#BE185D'))
    elif scene == 'spring':
        if night:
            p.vgradient(0, gy, c('#0F1B2D'), c('#1F3B4D'))
            stars(p, r, gy - 8, c('#E0F2FE'))
        else:
            p.vgradient(0, gy, c('#3B6E99'), c('#9CC8E0'))
            p.glow(w - 18, 8, 10, c('#80FDE68A'))
            p.art(SUN, m(s='#FDE047'), w - 22, 4)
        for fx in (0.06, 0.24, 0.48, 0.7, 0.92):
            col = ('#F472B6', '#FB7185', '#C084FC')[int(fx * 10) % 3]
            p.art(TULIP, m(p=col, g='#16A34A'), int(w * fx), gy - 7)
        for fx in (0.15, 0.38, 0.6, 0.82):
            p.art(DAISY, m(w='#F8FAFC', y='#FDE047', g='#16A34A'), int(w * fx), gy - 5)
        ground(p, r, c('#4D7C0F'), c('#65A30D'))
    elif scene == 'summer':
        if night:
            p.vgradient(0, gy - 5, c('#0B1530'), c('#3B2A55'))
            stars(p, r, gy - 12, c('#FEF3C7'))
            p.art(MOON, m(m='#FDE68A', c='#F5C66B'), w - 26, 3)
        else:
            p.vgradient(0, gy - 5, c('#F59E0B'), c('#FDBA74'))
            p.glow(w // 2, gy - 6, 14, c('#90FDE047'))
            p.art(SUN, m(s='#FEF08A'), w // 2 - 4, gy - 11)
        p.rect(0, gy - 5, w, 5, c('#1E3A5F' if night else '#0E7490'))
        p.art(PALM, m(g='#15803D', t='#92400E'), int(w * 0.08), gy - 11)
        p.art(PALM, m(g='#166534', t='#78350F'), int(w * 0.82), gy - 11, flip_x=True)
        ground(p, r, c('#E8C98E'), c('#D6B07A'))
    elif scene == 'space':
        p.vgradient(0, gy, c('#06030F'), c('#1C1436'))
        stars(p, r, gy - 2, c('#FFFFFF'), 0.06)
        p.art(PLANET, m(p='#A78BFA', q='#C4B5FD', r='#F9A8D4'), w - 28, 4)
        ground(p, r, c('#4B5563'), c('#6B7280'))
        for _ in range(w // 18):
            p.rect(r.randrange(w), H - GROUND, 3, 1, c('#374151'))
    elif scene == 'ocean':
        p.vgradient(0, gy, c('#0E4A6E'), c('#06263D'))
        for i in range(0, w, 9):
            p.set(i + r.randrange(5), 1, c('#4022D3EE'))
        for fx in (0.17, 0.66, 0.93):
            p.art(CORAL, m(p='#F472B6'), int(w * fx), gy - 5)
        ground(p, r, c('#C2A878'), c('#A88F63'))
    elif scene == 'cyberpunk':
        p.vgradient(0, gy, c('#05040A'), c('#1A1033'))
        x = 0
        while x < w:
            p.art(SKYLINE, m(b='#141024'), x, gy - len(SKYLINE))
            x += len(SKYLINE[0])
        for _ in range(w // 3):
            wx = r.randrange(w)
            wy = gy - 1 - r.randrange(5)
            if wy >= gy - 5:
                p.set(wx, wy, c('#FF00E5FF') if r.random() < 0.5 else c('#FFF0ABFC'))
        p.rect(0, gy, w, 1, c('#00E5FF'))
        ground(p, r, c('#0F172A'), c('#1E293B'), top=1)
    elif scene == 'oled':
        p.fill(c('#000000'))
        stars(p, r, gy - 4, c('#9CA3AF'), 0.012)
        p.art(['..mm', '.m..', 'm...', 'm...', 'm...', '.m..', '..mm'], m(m='#E5E7EB'), w - 16, 4)
        p.rect(0, gy, w, 1, c('#27272A'))
    elif scene == 'midnight':
        p.vgradient(0, gy, c('#020617'), c('#172554'))
        stars(p, r, gy - 8, c('#BFDBFE'), 0.04)
        p.glow(w - 20, 7, 9, c('#50BFDBFE'))
        p.art(MOON, m(m='#E0E7FF', c='#C7D2FE'), w - 26, 2)
        for x in range(w):
            far = kround(8 + 3.5 * math.sin(x / 9.0) + 2 * math.sin(x / 4.3 + 1))
            for y in range(gy - far, gy):
                p.set(x, y, c('#1E3A8A'))
            near = kround(4 + 2 * math.sin(x / 6.5 + 2) + 1.2 * math.sin(x / 3.1))
            for y in range(gy - near, gy):
                p.set(x, y, c('#0F1E4A'))
        ground(p, r, c('#0B1530'), c('#1E3A5F'))
    return p


# ---------------------------------------------------------------- animation ----

def fx(scene, w, hour, t, n=LOOP):
    """What moves at frame t of a loop of n frames, on a transparent canvas. Everything
    is periodic in n, so the loop has no seam."""
    p = Pix(w, H)
    r = seed(scene, 31, 7)
    gy = H - GROUND
    night = hour < 7 or hour >= 19
    u = t / n

    def across(x0, span, laps):
        return (x0 + u * span * laps) % span

    def wave(cycles, ph=0.0):
        return math.sin(2 * math.pi * (u * cycles + ph))

    def flap(period, offset=0):
        return ((t + offset) // period) % 2 == 0

    if scene == 'halloween':
        bat = m(b='#7353A0', r='#F87171')
        for i, (x0, y0, laps) in enumerate(((0.1, 4, 1), (0.55, 9, 1))):
            x = int(across(x0 * (w + 22), w + 22.0, laps)) - 11
            y = y0 + kround(2 * wave(2, i * 0.3))
            p.art(BAT_UP if flap(3, i) else BAT_DOWN, bat, x, y)
        gx = (w + 8) - int(across(0.3 * (w + 8), w + 16.0, 1))
        p.art(GHOST, m(w='#C8F5F3FF', k='#1C1326'), gx, 3 + kround(1.5 * wave(2)))
        for i, f in enumerate((0.22, 0.56, 0.86)):
            dim = noise(t // 4, i) % 7 == 0
            p.art(PUMPKIN, m(y='#FB923C' if dim else '#FDE047'), int(w * f), gy - 7)
        for i in range(4):
            cx = w * (0.15 + 0.23 * i)
            x = int(cx + 6 * wave(1, i * 0.27))
            y = int(gy - 9 + 3 * wave(2, i * 0.41))
            a = 0.35 + 0.35 * ((wave(2, i * 0.5) + 1) / 2)
            p.glow(x, y, 3, with_alpha(c('#4ADE80'), a * 0.6))
            p.set(x, y, with_alpha(c('#BBF7D0'), a + 0.2))
    elif scene == 'christmas':
        for i in range(w // 3):
            y = int(across(r.random() * gy, float(gy), 1))
            x = int(r.random() * w + 1.5 * wave(2, r.random()))
            p.set(x, y, c('#F8FAFC' if i % 2 == 0 else '#B0E2E8F0'))
        tx = int(w * 0.12)
        lights = ((3, 2), (5, 4), (2, 5), (6, 7), (1, 8), (4, 7), (7, 8))
        cols = ('#EF4444', '#FDE047', '#60A5FA', '#F472B6')
        for i, (lx, ly) in enumerate(lights):
            p.set(tx + lx, gy - 11 + ly, c(cols[(i + t // 6) % len(cols)]))
        p.glow(tx + 4, gy - 11, 3, with_alpha(c('#FDE047'), 0.4 + 0.3 * wave(3)))
    elif scene == 'valentine':
        for i in range(7):
            y = gy - 3 - across(r.random() * gy, float(gy), 1)
            x = int(r.random() * w + 2 * wave(2, r.random()))
            a = max(0.15, min(1.0, y / gy))
            p.art(HEART_S, {'h': with_alpha(c('#F9A8D4' if i % 2 == 0 else '#FB7185'), a)}, x, int(y))
    elif scene == 'spring':
        for i in range(3):
            cx = w * (0.2 + 0.3 * i)
            x = int(cx + 10 * wave(1, i * 0.33))
            y = int(8 + 3 * i + 3 * wave(2, i * 0.33))
            col = ('#F9A8D4', '#FDE047', '#C4B5FD')[i]
            p.art(BFLY_A if flap(3, i) else BFLY_B, m(p=col, k='#1F2937'), x, y)
        for _ in range(6):
            x = int(across(r.random() * w, float(w), 1))
            y = int(across(r.random() * gy, float(gy), 1))
            p.set(x, y, c('#D0FBCFE8'))
    elif scene == 'summer':
        for x in range(w):
            if (x + t // 2) % 9 == 0:
                p.set(x, gy - 5 + (x // 9) % 2, c('#6093C5FD' if night else '#C0E0F2FE'))
        if not night:
            for i in range(2):
                x = int(across(i * 0.5 * (w + 10), w + 10.0, 1)) - 5
                p.art(GULL_A if flap(4, i) else GULL_B, m(w='#F8FAFC'), x, 4 + i * 4 + kround(wave(2, i * 0.5)))
    elif scene == 'space':
        for i in range(w // 7):
            x = r.randrange(w)
            y = r.randrange(gy - 2)
            if wave(1 + i % 3, r.random()) > 0.6:
                p.set(x, y, c('#FFFFFFFF'))
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    p.set(x + dx, y + dy, c('#70FFFFFF'))
        rx = int(across(0.2 * (w + 10), w + 10.0, 1)) - 5
        ry = 7 + kround(wave(2))
        p.art(['..w..', '.www.', 'wwbww', '.www.', 'r...r'], m(w='#E5E7EB', b='#60A5FA', r='#F97316'), rx, ry)
        p.set(rx - 1, ry + 2, c('#FDE047' if flap(2) else '#F97316'))
        p.set(rx - 2, ry + 2, c('#80F97316'))
        s = t - n // 3
        if 0 <= s <= 7:
            for k in range(4):
                p.set(w // 2 + (s - k) * 3, 2 + (s - k), with_alpha(c('#FFFFFF'), 1 - k * 0.25))
    elif scene == 'ocean':
        for i, f in enumerate((0.05, 0.3, 0.55, 0.78)):
            bx = int(w * f)
            for k in range(8):
                sway = kround(1.2 * wave(2, i * 0.25 + k * 0.06) * k / 8)
                p.set(bx + sway + (k % 2), gy - 1 - k, c('#15803D'))
        for _ in range(7):
            y = gy - 2 - int(across(r.random() * gy, float(gy), 1))
            x = int(r.random() * w + wave(2, r.random()))
            p.art(['.b.', 'b.b', '.b.'], m(b='#B0E0F2FE'), x, y)
        p.art(FISH, m(o='#FB923C'), int(across(0.0, w + 8.0, 1)) - 4, 8 + kround(wave(2)), flip_x=True)
        p.art(FISH, m(o='#FDE047'), w + 4 - int(across(0.5 * w, w + 8.0, 1)), 14 + kround(wave(3, 0.5)))
    elif scene == 'cyberpunk':
        for _ in range(w // 3):
            x0 = r.random() * w
            y = int(across(r.random() * gy, float(gy), 2))
            x = int((x0 - y * 0.3) % w)
            p.set(x, y, c('#507DF9FF'))
            p.set(x, y + 1, c('#307DF9FF'))
        off = noise(t // 2, 9) % 11 == 0 or noise(t // 2, 3) % 13 == 0
        if not off:
            p.art(['.c..ccc', 'c.c..c.', 'ccc..c.', 'c.c..c.', 'c.c.ccc'], m(c='#F0ABFC'), int(w * 0.62), 3)
        cx = int(across(0.0, w + 12.0, 1)) - 6
        p.art(['.cccc.', 'cyccyc', '.k..k.'], m(c='#334155', y='#FDE047', k='#00E5FF'), cx, 10)
    elif scene == 'oled':
        for i in range(w // 14):
            x = r.randrange(w)
            y = r.randrange(gy - 4)
            if wave(1 + i % 3, r.random()) > 0.5:
                p.set(x, y, c('#FFFFFFFF'))
        s = t - n // 2
        if 0 <= s <= 6:
            for k in range(3):
                p.set(w // 4 + (s - k) * 3, 2 + (s - k), with_alpha(c('#FFFFFF'), 1 - k * 0.3))
    elif scene == 'midnight':
        for x in range(w):
            y = kround(5 + 2.5 * math.sin(2 * math.pi * (x / 40.0 + u)) + 1.5 * wave(1, x / 90.0))
            a = 0.35 + 0.25 * math.sin(2 * math.pi * (x / 25.0 - u * 2))
            for k in range(4):
                p.set(x, y + k, with_alpha(c('#34D399' if k < 2 else '#22D3EE'), a * (1 - k * 0.22)))
        for i in range(w // 10):
            x = r.randrange(w)
            y = 10 + r.randrange(gy - 18)
            if wave(1 + i % 3, r.random()) > 0.65:
                p.set(x, y, c('#FFFFFFFF'))
        for i in range(3):
            x = int(w * (0.2 + 0.3 * i) + 8 * wave(1, i * 0.3))
            y = int(gy - 3 + 1.5 * wave(2, i * 0.4))
            p.set(x, y, with_alpha(c('#FDE047'), max(0.15, 0.5 + 0.5 * wave(3, i * 0.2))))
    return p


class SceneCache:
    """Finished frames (backdrop + moving things) as QImages, rebuilt when the scene,
    width or hour changes."""

    def __init__(self):
        self.key = None
        self.bg = None
        self.frames = {}

    def frame(self, scene, w, hour, t):
        key = (scene, w, hour)
        if key != self.key:
            self.key = key
            self.bg = background(scene, w, hour)
            self.frames = {}
        img = self.frames.get(t)
        if img is None:
            p = self.bg.copy()
            fx(scene, w, hour, t).draw_into(p, 0, 0)
            img = self.frames[t] = p.to_qimage()
        return img
