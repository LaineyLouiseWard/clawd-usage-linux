"""Clawd's outfits, the props some of them hold, and those outfits' routines.

Port of art/Skins.kt, art/Props.kt and the routines in art/Stage.kt from Pinch
(https://github.com/YoussefAbdelkawy/Pinch, MIT, see LICENSE-pinch). The outfit files in
skins/ are Pinch's, in the same text format as clawd-usage-winwidget:

    ---
    name: Top hat
    body: #D77757      (optional)
    eyes: #141416      (optional)
    top: -5            first art row, counted from Clawd's top row (optional)
    k: #18181B         a colour for each letter of the art
    ---
    .......kkkkkk.....

Coordinates are in Clawd's 18 x 12 pixel grid; rows above his head are negative.
"""

import math
import os
import re
from collections import namedtuple

from scenes import c, kround, with_alpha

GW = 18
SKIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'skins')

Skin = namedtuple('Skin', 'id name body eyes layers')
CLASSIC = Skin('classic', 'None', '#D77757', '#141416', [])

_HEAD = re.compile(r'(?s)^\s*---\s*\r?\n(.*?)\r?\n---\s*\r?\n?(.*)$')
_KV = re.compile(r'^\s*(\w+)\s*:\s*(.*?)\s*$')
_HEX = re.compile(r'^#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$')


def parse(sid, raw):
    mt = _HEAD.match(raw.lstrip('﻿'))
    if not mt:
        return None
    name, body, eyes, top, colors = sid, CLASSIC.body, CLASSIC.eyes, None, {}
    for line in mt.group(1).splitlines():
        kv = _KV.match(line)
        if not kv:
            continue
        k, v = kv.groups()
        ok = bool(_HEX.match(v))
        if k == 'name':
            name = v
        elif k == 'body' and ok:
            body = v
        elif k == 'eyes' and ok:
            eyes = v
        elif k == 'top':
            try:
                top = int(v)
            except ValueError:
                pass
        elif len(k) == 1 and ok:
            colors[k] = v
    rows = [r.rstrip() for r in mt.group(2).splitlines()]
    while rows and not rows[-1]:
        rows.pop()
    start = top if top is not None else -len(rows)
    by_color = {}
    for y, row in enumerate(rows):
        for x, ch in enumerate(row[:GW]):
            if ch in colors:
                by_color.setdefault(ch, []).append((x, start + y))
    return Skin(sid, name, body, eyes, [(colors[ch], pts) for ch, pts in by_color.items()])


def load_all():
    out = {'classic': CLASSIC}
    try:
        files = sorted(os.listdir(SKIN_DIR))
    except OSError:
        files = []
    for fn in files:
        if not fn.endswith('.txt'):
            continue
        try:
            with open(os.path.join(SKIN_DIR, fn), encoding='utf-8') as fh:
                s = parse(fn[:-4], fh.read())
        except OSError:
            s = None
        if s:
            out[s.id] = s
    return out


# -------------------------------------------------------------------- props ----

ROUTINES = ('chef', 'programmer', 'wizard', 'detective')

TOSS = (2, 4, 6, 7, 8, 8, 7, 6, 4, 2, 1)   # pancake height above the pan, per toss step
WAVE = (1, 2, 3, 4, 3, 2, 1, 2, 3)         # wand-wave steps before the spell goes off
CAST = 8
WAND_ANGLE = (45, 0, 30, 70, 100)          # resting, up, up-forward, forward, down-forward
LENS_DOWN, LENS_EYE, LENS_GROUND = 0, 1, 2

PAN_RIM, PAN, HANDLE = c('#52525B'), c('#27272A'), c('#3F3F46')
PANCAKE, PANCAKE_TOP, PANCAKE_UNDER, STEAM = c('#F59E0B'), c('#FCD34D'), c('#B45309'), c('#E4E4E7')
LID, LID_EDGE, LOGO = c('#1F1F23'), c('#3F3F46'), c('#E5E7EB')
BASE, BASE_TOP, SCREEN_GLOW = c('#71717A'), c('#A1A1AA'), c('#60A5FA')
WAND, SPARK, SPARK_HI, MAGIC = c('#5B3A29'), c('#FDE047'), c('#FFFBEB'), c('#C4B5FD')
LENS_RIM, LENS, GLINT, LENS_HANDLE = c('#27272A'), c('#B3E0F2FE'), c('#FFFFFF'), c('#3F342D')
PIPE, PIPE_STEM, SMOKE, PUPIL = c('#7C4A2D'), c('#3F2A1D'), c('#D4D4D8'), c('#141416')
RING = ['.rrr.', 'r...r', 'r...r', 'r...r', '.rrr.']
PLUS = ((-1, 0), (1, 0), (0, -1), (0, 1))


class Dots:
    """Collects (x, y, argb) pixels; the widget paints them as rects."""

    def __init__(self):
        self.px = []

    def set(self, x, y, argb):
        if argb >> 24:
            self.px.append((x, y, argb))

    def rect(self, x, y, w, h, argb):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.set(xx, yy, argb)

    def art(self, rows, colors, x, y):
        for ry, row in enumerate(rows):
            for rx, ch in enumerate(row):
                if ch in colors:
                    self.set(x + rx, y + ry, colors[ch])


def props(skin_id, f, t, x, y, rest):
    """What the outfit holds, as pixels. x, y: Clawd's grid top-left as drawn (after
    crouching or lifting); rest: the grid top when standing, for things on the ground."""
    p = Dots()
    if skin_id == 'chef':
        _chef(p, f, t, x, y)
    elif skin_id == 'programmer':
        _programmer(p, f, t, x, rest)
    elif skin_id == 'wizard':
        _wizard(p, f, t, x, y)
    elif skin_id == 'detective':
        _detective(p, f, t, x, y)
    return p.px


def _chef(p, f, t, x, y):
    py = y - (1 if f['arms'] == 'up' else 0)    # the pan comes up a row as he tosses
    p.set(x + 18, py + 5, HANDLE)
    p.set(x + 19, py + 5, HANDLE)
    p.rect(x + 20, py + 4, 7, 1, PAN_RIM)
    p.rect(x + 21, py + 5, 5, 1, PAN)
    step = f.get('prop', 0)
    if step <= 0 or step > len(TOSS):
        # Cooking: the pancake sits in the pan, steam curls up, the odd sizzle.
        p.rect(x + 21, py + 3, 5, 1, PANCAKE)
        p.rect(x + 22, py + 3, 3, 1, PANCAKE_TOP)
        for i in (0, 1):
            s = (t // 4 + i * 4) % 8
            p.set(x + 22 + i * 2 + (s // 3) % 2, py + 2 - s, with_alpha(STEAM, 0.75 - s * 0.09))
        if (t // 3) % 7 == 0:
            p.set(x + 26, py + 3, PANCAKE_TOP)
    else:
        # In the air: it turns over on the way up and comes down the other way round.
        cy = py + 3 - TOSS[step - 1]
        k = step % 4
        if k in (1, 3):
            p.set(x + 23, cy - 1, PANCAKE)
            p.set(x + 23, cy, PANCAKE_UNDER)
        elif k == 2:
            p.rect(x + 21, cy, 5, 1, PANCAKE_UNDER)
        else:
            p.rect(x + 21, cy, 5, 1, PANCAKE)
            p.rect(x + 22, cy, 3, 1, PANCAKE_TOP)


def _programmer(p, f, t, x, rest):
    # He sits on the ground behind an open laptop; we see the back of its lid.
    gy = rest + 9
    p.rect(x + 12, gy, 12, 1, BASE)
    p.rect(x + 12, gy - 1, 6, 1, BASE_TOP)
    p.rect(x + 17, gy - 7, 7, 7, LID)
    p.rect(x + 17, gy - 7, 1, 7, LID_EDGE)
    p.rect(x + 17, gy - 7, 7, 1, LID_EDGE)
    p.set(x + 20, gy - 4, LOGO)
    p.set(x + 21, gy - 4, LOGO)
    p.set(x + 21, gy - 3, LOGO)
    if f['arms'] == 'right':
        p.set(x + 13 + (t * 3) % 4, gy - 1, LOGO)
    glow = 0.18 + 0.12 * ((t // 3) % 3)
    for dy in range(2, 6):
        p.set(x + 15, rest + 4 + dy, with_alpha(SCREEN_GLOW, glow))


def _wand_tip(x, y, angle):
    a = math.radians(angle)
    return kround(x + 17 + 4 * math.sin(a)), kround(y + 5 - 4 * math.cos(a))


def _wizard(p, f, t, x, y):
    prop = f.get('prop', 0)
    waving = 1 <= prop <= len(WAVE)
    casting = prop > len(WAVE)
    angle = WAND_ANGLE[WAVE[prop - 1]] if waving else (WAND_ANGLE[3] if casting else WAND_ANGLE[0])
    a = math.radians(angle)
    for k in (1, 2, 3):
        p.set(kround(x + 17 + k * math.sin(a)), kround(y + 5 - k * math.cos(a)), WAND)
    tx, ty = _wand_tip(x, y, angle)
    p.set(tx, ty, SPARK_HI)
    if waving:
        # A trail of sparks where the tip has just been.
        for back in (1, 2, 3):
            prev = prop - back
            if prev < 1:
                break
            sx, sy = _wand_tip(x, y, WAND_ANGLE[WAVE[prev - 1]])
            p.set(sx, sy, with_alpha(SPARK if back == 1 else MAGIC, 1 - back * 0.28))
    elif casting:
        # The spell: a ring of stars bursting out from the tip.
        k = prop - len(WAVE)
        r = 1 + k
        fade = 1 - k / (CAST + 1.0)
        for i in range(10):
            ang = math.pi * 2 * i / 10 + k * 0.2
            col = MAGIC if i % 3 == 0 else (SPARK_HI if i % 2 == 0 else SPARK)
            p.set(tx + kround(r * math.cos(ang)), ty + kround(r * 0.7 * math.sin(ang)), with_alpha(col, fade))
        if k < 3:
            for ax, ay in PLUS:
                p.set(tx + ax, ty + ay, SPARK_HI)
    else:
        # Resting: the tip twinkles now and then.
        if (t // 3) % 8 < 2:
            for ax, ay in PLUS:
                p.set(tx + ax, ty + ay, with_alpha(SPARK, 0.7))
        if (t // 5) % 6 == 0:
            p.set(tx + 1, ty - 2, MAGIC)


def _lens(p, lx, ly, t):
    p.rect(lx + 1, ly + 1, 3, 3, LENS)
    p.art(RING, {'r': LENS_RIM}, lx, ly)
    g = (t // 6) % 8
    if g < 3:
        p.set(lx + 1 + g // 2, ly + 1 + g // 2, GLINT)


def _detective(p, f, t, x, y):
    # The pipe in the corner of his mouth, smoke curling up slowly.
    p.set(x + 6, y + 5, PIPE_STEM)
    p.set(x + 5, y + 6, PIPE_STEM)
    p.rect(x + 2, y + 6, 3, 2, PIPE)
    p.set(x + 2, y + 5, PIPE)
    for i in range(3):
        s = (t // 4 + i * 5) % 14
        sx = x + 3 - (s // 4) + (0 if (s // 2) % 2 == 0 else 1)
        p.set(sx, y + 4 - s, with_alpha(SMOKE, max(0.0, 0.7 - s * 0.05)))
    prop = f.get('prop', 0)
    if prop == LENS_EYE:
        # Up to his right eye: we see the eye through it, big, looking where he looks.
        lx, ly = x + 11, y
        p.set(x + 16, y + 5, LENS_HANDLE)
        p.set(x + 17, y + 6, LENS_HANDLE)
        _lens(p, lx, ly, t)
        px = lx + 1 + max(0, min(2, f['look'] + 1)) // 2
        p.rect(px, ly + 2, 2, 2, PUPIL)
    elif prop == LENS_GROUND:
        # Held out low, over something on the ground in front of him.
        p.set(x + 18, y + 6, LENS_HANDLE)
        p.set(x + 19, y + 6, LENS_HANDLE)
        _lens(p, x + 20, y + 5, t)
    else:
        p.set(x + 18, y + 6, LENS_HANDLE)
        p.set(x + 19, y + 5, LENS_HANDLE)
        _lens(p, x + 19, y + 1, t)


# ----------------------------------------------------------------- routines ----

STRIDE = ('both', 'left', 'both', 'right')   # a lifted leg never stays up two frames


def fr(**kw):
    f = {'eyes': 'open', 'arms': 'down', 'feet': 'both', 'look': 0, 'off': 0, 'lift': 0, 'prop': 0}
    f.update(kw)
    return f


class _Builder:
    def __init__(self, start, max_x):
        self.out = []
        self.x = start
        self.max_x = max_x

    def hold(self, k, f):
        for _ in range(k):
            self.out.append((self.x, f))

    def hold_fn(self, k, fn):
        for _ in range(k):
            self.out.append((self.x, fn(len(self.out))))

    def walk(self, dx, every, base):
        d = (dx > 0) - (dx < 0)
        for s in range(abs(dx) * every):
            if s % every == every - 1:
                self.x += d
            f = dict(base(len(self.out)))
            f['look'], f['feet'] = d, STRIDE[s % len(STRIDE)]
            self.out.append((self.x, f))

    def fill(self, n, fn):
        while len(self.out) < n:
            self.out.append((self.x, fn(len(self.out))))

    def room(self, d):
        return self.max_x - self.x if d > 0 else self.x

    def roomy_dir(self):
        return 1 if self.max_x - self.x >= self.x else -1


def routine(skin_id, tired, start, max_x, n=120):
    """The outfit's own loop (cooking, typing, spell-casting, investigating) as a list of
    (grid x in pixels, frame). It ends where and how it began. lift is in pixels."""
    b = _Builder(start, max_x)

    def eyes(e):
        return 'focus' if tired and e == 'open' else e

    if skin_id == 'chef':
        # Watches the pan, then tosses: the pan comes up, the pancake flips, he catches it.
        while len(b.out) + 40 <= n:
            b.hold_fn(8, lambda t: fr(eyes=eyes('open'), look=1))
            b.hold(1, fr(eyes='blink', look=1))
            b.hold_fn(9, lambda t: fr(eyes=eyes('open'), look=1))
            b.hold(2, fr(eyes='focus', look=1))
            for step in range(1, len(TOSS) + 1):
                b.hold(1, fr(eyes='wide' if 4 <= step <= 7 else 'focus', look=1,
                             arms='up' if step <= 2 else 'right', prop=step))
            b.hold(9, fr(eyes='happy', arms='right'))
        b.fill(n, lambda t: fr(eyes=eyes('open'), look=1))
    elif skin_id == 'programmer':
        # Sitting on the ground at his laptop: typing, glancing away to think, the odd stretch.
        for t in range(n):
            k = t % 60
            if 50 <= k <= 55:
                f = fr(arms='up', eyes='closed')
            elif k % 23 == 11:
                f = fr(eyes='blink', look=1)
            elif 30 <= k <= 35:
                f = fr(eyes=eyes('open'), look=-1)
            else:
                f = fr(eyes='focus' if tired else 'happy', look=1, arms='down' if (t // 2) % 2 == 0 else 'right')
            f.update(feet='tucked', lift=-2)
            b.hold(1, f)
    elif skin_id == 'wizard':
        # Strolls, waves the wand in an arc, and casts; twice per loop.
        d_ = b.roomy_dir()
        d = min(10, b.room(d_))

        def cast():
            for step in range(1, len(WAVE) + 1):
                b.hold(1, fr(eyes='focus', arms='up' if WAVE[step - 1] == 1 else 'right', prop=step))
            for k in range(1, CAST + 1):
                b.hold(1, fr(eyes='happy', arms='right', prop=len(WAVE) + k))
        b.hold_fn(8, lambda t: fr(eyes=eyes('open')))
        cast()
        b.hold(4, fr(look=d_))
        b.walk(d_ * d, 1, lambda t: fr())
        b.hold(3, fr(eyes='blink'))
        cast()
        b.walk(-d_ * d, 1, lambda t: fr())
        b.fill(n, lambda t: fr(eyes='blink' if t % 13 == 6 else eyes('open')))
    elif skin_id == 'detective':
        # Paces slowly, studies the ground, then holds the glass up to his eye.
        d_ = b.roomy_dir()
        d = min(8, b.room(d_))

        def pace(t):
            return fr(eyes=eyes('open'))
        b.hold_fn(6, pace)
        b.walk(d_ * d, 2, pace)
        b.hold(14, fr(eyes='focus', look=d_, prop=LENS_GROUND))
        b.hold(3, fr(look=d_))
        for k in range(18):
            b.hold(1, fr(look=0 if k < 6 else (-1 if k < 12 else 1), prop=LENS_EYE))
        b.hold(3, fr(eyes='wide'))
        b.walk(-d_ * d, 2, pace)
        b.fill(n, lambda t: fr(eyes='blink' if t % 17 == 8 else eyes('open')))
    return b.out[:n]
