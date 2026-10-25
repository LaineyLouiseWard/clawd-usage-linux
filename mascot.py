"""Clawd, the crab from the Claude Code welcome screen.

Port of lib/mascot.ps1, lib/mascot-step.ps1 and lib/hearts.ps1 from
clawd-usage-winwidget (MIT). Clawd is 9 cells by 3 rows of terminal block
glyphs; each cell is split into 2x4 pixels so quadrant glyphs map losslessly.
All coordinates here are in "units" (WPF DIPs in the original); the widget
scales them when painting.
"""

import math
import random
import time

from skins import ROUTINES, routine

COLS, ROWS = 9, 3
PX, PY = 2.0, 2.2
GW, GH = 2 * COLS, 4 * ROWS          # pixel grid 18 x 12
MASCOT_W = GW * PX
MASCOT_H = GH * PY
SINK = 2 * PY                         # empty lower half of the legs row
FRAME_MS = 60                         # Claude Code animations
STEP_MS = 90                          # everything else
BURROW_DIG = 4

BODY = "#D77757"
EYE = "#141416"
FX = "#6B7280"
SAND = "#B8955E"

QUAD = {' ': 0, '█': 15, '▀': 3, '▄': 12, '▌': 5, '▐': 10, '▘': 1, '▝': 2,
        '▖': 4, '▗': 8, '▛': 7, '▜': 11, '▙': 13, '▟': 14}

ARMS = {
    'down':  {'r1L': ' ▐', 'r1R': '',  'r2L': '▝▜', 'r2R': '█▀'},
    'up':    {'r1L': '▗▟', 'r1R': '▄', 'r2L': ' ▜', 'r2R': '█▘'},
    'right': {'r1L': ' ▐', 'r1R': '▄', 'r2L': '▝▜', 'r2R': '█▘'},
    'left':  {'r1L': '▗▟', 'r1R': '',  'r2L': ' ▜', 'r2R': '█▀'},
}
FEET = {'both': ' ▝▝   ▝▝ ', 'left': ' ▝▝      ', 'right': '      ▝▝ ',
        'tucked': '         '}   # sitting: legs folded under him

FACING = {
    'right-12': [(' ▐█▜██▛█ ', 2, 8), ('▝▜██████▀', 2, 7), (' ▝▝   ▝▝ ', 0, 0)],
    'right-30': [('  █▛██▛▌ ', 2, 7), (' ▝█████▛ ', 2, 7), ('  ▘▘  ▘▘ ', 0, 0)],
    'right-55': [('  ▐█▛█▜  ', 3, 7), ('  ▐████  ', 3, 7), ('  ▝▝ ▝▝  ', 0, 0)],
    'right-75': [('   ██▛▌  ', 3, 6), ('   ███▌  ', 3, 6), ('   ▘  ▘  ', 0, 0)],
    'edge':     [('   ▐██   ', 4, 6), ('   ▐██   ', 4, 6), ('   ▝ ▝   ', 0, 0)],
    'back-105': [('   ███▌  ', 3, 6), ('   ███▌  ', 3, 6), ('   ▘  ▘  ', 0, 0)],
    'back-125': [('  ▐████  ', 3, 7), ('  ▐████  ', 3, 7), ('  ▝▝ ▝▝  ', 0, 0)],
    'back-150': [('  █████▌ ', 2, 7), (' ▝█████▛ ', 2, 7), ('  ▘▘  ▘▘ ', 0, 0)],
    'back':     [(' ▐██████ ', 2, 8), ('▝▜██████▀', 2, 7), (' ▝▝   ▝▝ ', 0, 0)],
    'left-75':  [('   ▛██▌  ', 3, 6), ('   ███▌  ', 3, 6), ('   ▘  ▘  ', 0, 0)],
    'left-55':  [('  ▐▜▛██  ', 3, 7), ('  ▐████  ', 3, 7), ('  ▝▝ ▝▝  ', 0, 0)],
    'left-30':  [('  ▛██▛█▌ ', 2, 7), (' ▝█████▛ ', 2, 7), ('  ▘▘  ▘▘ ', 0, 0)],
    'left-12':  [(' ▐▛███▜█ ', 2, 8), ('▝▜██████▀', 2, 7), (' ▝▝   ▝▝ ', 0, 0)],
}

EYES = {
    'open': '1,2 1,3', 'left': '0,0 0,1', 'right': '2,0 2,1',
    'closed': '0,3 1,3', 'blink': '0,3 1,3', 'wink': '1,2 1,3;0,3 1,3',
    'happy': '0,3 1,2 2,3', 'focus': '1,3', 'wide': '0,1 1,1 0,2 1,2 0,3 1,3',
    'x': '0,1 2,1 1,2 0,3 2,3', 'yawn': '0,3 1,3', 'gasp': '0,1 2,1 1,2 0,3 2,3',
}

POSES = {'default': 'open/down/both', 'arms-up': 'open/up/both',
         'look-left': 'left/down/both', 'look-right': 'right/down/both'}


# ------------------------------------------------ Claude Code animations ----

def F(pose, n=1, off=0, x=0, poof='', shadow=''):
    fr = {'off': off, 'x': x, 'poof': poof, 'shadow': shadow, 'facing': ''}
    if pose.startswith('face:'):
        fr.update(facing=pose[5:], eyes='open', arms='down', feet='both')
    else:
        pose = POSES.get(pose, pose)
        fr['eyes'], fr['arms'], fr['feet'] = pose.split('/')
    return [dict(fr) for _ in range(n)]


def turn(names, shadow=''):
    out = []
    for p in names:
        out += F('face:' + p, 1, shadow=shadow)
    return out


_cr = F('default', 1, off=1, poof='dot') + F('default', 1, off=1, poof='wave')
_bo = F('default')
_ts = F('closed/down/both') + _bo
_jump = _cr + F('arms-up', 3) + _bo + _cr + F('arms-up', 3) + _bo
_waddle = F('look-right', 1, x=-9)
for _u in range(-6, 0):
    _waddle += F('right/down/' + ('left' if _u % 2 == 0 else 'right'), 2, x=_u)

SEQS = {
    'jump': _jump,
    'look': F('look-right', 5) + F('look-left', 5) + _bo,
    'celebrate': _jump + F('default', 3, off=1),
    'skip': (F('default', 1, off=1, x=-9) + F('arms-up', 2, x=-6) + F('default', 1, x=-6) +
             F('default', 1, off=1, x=-6) + F('arms-up', 2, x=-3) + F('default', 1, x=-3) +
             F('default', 1, off=1, x=-3) + F('arms-up', 2) + _cr + _bo),
    'spin': F('look-left', 2) + F('look-right', 2) + F('look-left', 2) + F('arms-up', 3) + _bo,
    'peekaboo': (F('default', 1, off=3) + F('default', 3, off=2) + F('look-right', 3, off=2) +
                 F('look-left', 3, off=2) + F('default', 2, off=2) + F('default', 1, off=1) +
                 F('arms-up', 4) + F('default', 2) + _ts),
    'drop': (F('arms-up', 1, off=-3) + F('arms-up', 2, off=-2) + F('arms-up', 2, off=-1) +
             F('arms-up', 1) + _cr + F('default', 3) + _ts),
    'waddle': _waddle + F('look-right', 2) + F('default', 2) + _ts,
    'peek': (F('look-right', 1, x=-9) + F('look-right', 5, x=-6) + F('look-right', 3, x=-9) +
             F('look-right', 4, x=-5) + F('arms-up', 2, x=-3) + F('arms-up', 2) + _cr + _bo),
    'wink': F('wink/down/both', 5) + _bo,
    'boop': (F('closed/down/both', 1, off=1, poof='dot') + F('closed/down/both', 2, off=1, poof='wave') +
             F('look-left', 4) + F('default', 2) + _ts),
    'tap': (F('open/down/left', 2) + F('open/down/right', 2) + F('open/down/left', 2) +
            F('open/down/right', 2) + F('open/down/left', 1) + F('open/down/right', 1) +
            F('arms-up', 3) + _bo),
    'sneeze': (F('closed/up/both', 4) + F('closed/down/both', 2, off=1, poof='wave') +
               F('closed/down/both', 2) + F('default', 2) + _ts),
    'turn': (turn(['right-12', 'right-30', 'right-55', 'right-75', 'edge']) +
             turn(['back-105', 'back-125', 'back-150', 'back', 'back']) +
             turn(['back-150', 'back-125', 'back-105', 'edge']) +
             turn(['left-75', 'left-55', 'left-30', 'left-12']) + _bo),
    'coin-hop': (F('default', 2, off=1) + F('arms-up', 1, shadow='wide') +
                 turn(['right-55', 'edge', 'back-125', 'back'], 'narrow') +
                 turn(['back-125', 'edge', 'left-55'], 'narrow') +
                 F('arms-up', 1, shadow='wide') + _cr + _bo),
}

CLICK_ACTS = [k for k, v in SEQS.items() if v[0]['x'] == 0 and k != 'celebrate']
ENTRANCE_ACTS = [k for k in SEQS if k != 'celebrate']

ACT_LEN = {k: len(v) for k, v in SEQS.items()}
ACT_LEN.update(wave=24, stretch=22, yawn=22, stumble=20, soul=66,
               burrow=30, unburrow=28, stir=22)
# Shown in the "Play animation" menu.
DEMO_ACTS = [k for k in ACT_LEN if k not in ('burrow', 'unburrow', 'stir')]

# Health by heart halves: speed, yawns, tired eyes, sweat, staggering.
HEALTH = {
    6: {'speed': 1.25, 'hop': 300},
    5: {'speed': 1.0},
    4: {'speed': 0.9, 'yawn': 350},
    3: {'speed': 0.75, 'yawn': 200, 'eyes': 'focus'},
    2: {'speed': 0.55, 'yawn': 160, 'eyes': 'focus', 'sweat': True},
    1: {'speed': 0.35, 'eyes': 'blink', 'sweat': True, 'stagger': True, 'stumble': 220},
    0: {'speed': 0.0},
}
HEALTH_NAMES = {6: 'full of energy', 5: 'fine', 4: 'a bit tired', 3: 'tired',
                2: 'exhausted', 1: 'barely alive', 0: 'out of strength'}

HEART_ROWS = ['.##.##.', '#######', '#######', '.#####.', '..###..', '...#...']
HEART_PX = 1.4

SOUL_UP, SOUL_BACK, SOUL_TOP, SOUL_PX = 26, 48, 20.0, 1.4
SOUL_ART = ['..########..', '..#.####.#..', '############', '..########..',
            '...######...', '....####....', '.....##.....']

CONFETTI_COLORS = ['#F87171', '#FBBF24', '#4ADE80', '#60A5FA', '#A78BFA', '#D77757']


def heart_rects(max_col=6):
    """Heart pixels as (x, y, w, h) rects; max_col=3 gives the left half."""
    out = []
    for y, row in enumerate(HEART_ROWS):
        for x in range(max_col + 1):
            if row[x] == '#':
                out.append((x * HEART_PX, y * HEART_PX, HEART_PX, HEART_PX))
    return out


# ------------------------------------------------------------- geometry ----

_geo_cache = {}


def geometry(f):
    """Frame -> {'body','eyes','fx','sand': [(x, y, w, h) in units]} relative to the
    top-left of the 36 x 26.4 mascot box."""
    key = tuple(f.get(k) for k in ('eyes', 'arms', 'feet', 'look', 'flip', 'off', 'x',
                                    'facing', 'poof', 'shadow', 'dig', 'spray'))
    if key in _geo_cache:
        return _geo_cache[key]

    g = [[0] * GH for _ in range(GW)]   # 0 empty, 1 body, 2 black

    def paint(glyphs, col, row, mode):
        fg = 2 if mode == 'lid' else 1
        bg = {'eyes': 2, 'lid': 1}.get(mode, 0)
        for i, c in enumerate(glyphs):
            for sy in range(4):
                for sx in range(2):
                    if c == '▂':
                        on = sy == 3
                    else:
                        bit = (1 if sy < 2 else 4) * (2 if sx else 1)
                        on = bool(QUAD.get(c, 0) & bit)
                    v = fg if on else bg
                    if v:
                        g[2 * (col + i) + sx][4 * row + sy] = v

    if f['facing']:
        for r in range(3):
            s, a, b = FACING[f['facing']][r]
            paint(s[:a], 0, r, '')
            paint(s[a:b], a, r, 'eyes')
            paint(s[b:], b, r, '')
    else:
        a = ARMS[f['arms']]
        paint(a['r1L'], 0, 0, '')
        paint('██████', 2, 0, 'eyes')
        paint(a['r1R'], 8, 0, '')
        paint(a['r2L'], 0, 1, '')
        paint('█████', 2, 1, 'eyes')
        paint(a['r2R'], 7, 1, '')
        paint(FEET[f['feet']], 0, 2, '')

        eyes, shift = f['eyes'], 0
        look = int(f['look'])
        if eyes == 'open' and look < 0:
            eyes = 'left'
        elif eyes == 'open' and look > 0:
            eyes = 'right'
        elif eyes not in ('open', 'left', 'right', 'wink'):
            shift = look
        sh = EYES[eyes].split(';')
        for k, ex in enumerate((4, 12)):
            for pt in sh[min(k, len(sh) - 1)].split(' '):
                dx, dy = pt.split(',')
                g[ex + int(dx) + shift][int(dy)] = 2
        if eyes in ('yawn', 'gasp'):
            for x in range(8, 11):
                g[x][4] = 2
                g[x][5] = 2

    body, eye, fx, sand = [], [], [], []
    dig = int(f['dig'])
    oy = 4 * int(f['off']) + dig
    ox = 2 * int(f['x'])
    lim = GH - 2 if dig > 0 else GH
    for y in range(GH):
        sy = y
        if f['flip']:
            if y >= GH - 2:
                continue
            sy = GH - 3 - y
        yy = sy + oy
        if yy < 0 or yy >= lim:
            continue
        x = 0
        while x < GW:
            c = g[x][y]
            if not c:
                x += 1
                continue
            x0 = x
            while x < GW and g[x][y] == c:
                x += 1
            l, rr = max(0, x0 + ox), min(GW, x + ox)
            if rr <= l:
                continue
            rect = (l * PX, yy * PY, (rr - l) * PX, PY)
            (eye if c == 2 else body).append(rect)

    if f['poof'] and f['off'] > 0:
        for cx in (0, GW - 2):
            pts = ([(0.6, 9.4, 0.8, 0.9)] if f['poof'] == 'dot'
                   else [(0.0, 9.6, 0.7, 0.6), (0.7, 9.1, 0.6, 0.6), (1.3, 9.6, 0.7, 0.6)])
            for p in pts:
                fx.append(((cx + p[0]) * PX, p[1] * PY, p[2] * PX, p[3] * PY))
    if f['shadow']:
        sc, sw = (6, 6) if f['shadow'] == 'wide' else (8, 2)
        fx.append((sc * PX, (GH - 0.5) * PY, sw * PX, 0.5 * PY))

    def pxr(x, y, w, h):
        sand.append((x * PX, y * PY, w * PX, h * PY))
    if dig >= 1:
        pxr(-2, GH - 3, GW + 4, 1)
    if dig >= 2:
        pxr(-1, GH - 4, GW + 2, 1)
    if dig >= 3:
        pxr(-1, GH - 5, 2, 1)
        pxr(GW - 1, GH - 5, 2, 1)
    spray = int(f['spray'])
    if spray > 0:
        for k in (0, 1):
            d = spray + 2 * k
            sx = 1.5 + 0.9 * d
            sy = (GH - 4) - 0.9 * d * (5 - d) / 2
            pxr(-sx, sy, 0.8, 0.8)
            pxr(GW - 0.8 + sx, sy, 0.8, 0.8)

    geo = {'body': body, 'eyes': eye, 'fx': fx, 'sand': sand}
    _geo_cache[key] = geo
    return geo


def soul_rects(h, t):
    """Soul with its thread; origin at the mouth, negative y is up."""
    out = []
    p = SOUL_PX
    sway = 2.5 * math.sin(t / 4.0)
    n = int(h // p)
    for i in range(n):
        k = i / max(1, n)
        dx = sway * k + 1.2 * math.sin(t / 2.0 + i * 0.7) * math.sin(k * math.pi)
        out.append((round(dx / p) * p - p / 2, -(i + 1) * p, p, p))
    top = -h - len(SOUL_ART) * p
    x0 = round(sway / p) * p - 6 * p
    for y, row in enumerate(SOUL_ART):
        x = 0
        while x < len(row):
            if row[x] != '#':
                x += 1
                continue
            a = x
            while x < len(row) and row[x] == '#':
                x += 1
            out.append((x0 + a * p, top + y * p, (x - a) * p, p))
    return out


# ---------------------------------------------------------------- state ----

class Mascot:
    """Clawd's state machine. step() advances one frame and fills self.r with
    everything the widget needs to paint."""

    def __init__(self):
        self.rnd = random.Random()
        self.x = -1.0
        self.dir = 1
        self.target = None
        self.look = 0
        self.tick = 0
        self.blink_at = 30
        self.mood = 'idle'
        self.cur = 'idle'
        self.crit = False
        self.idle_since = time.monotonic()
        self.act = None
        self.act_t = 0
        self.pct = None
        self.halves = None
        self.lost_t = -1
        self.lost_from = 0
        self.show_halves = None
        self.beat = 1.0
        self.love_t = -1
        self.note_t = -1
        self.conf_t = -1
        self.busy = -1
        self.waiting = 0
        self.last_reset = None
        self.last_pct = None
        self.buried = False
        self.walk_speed = 1.0     # multiplier, from config walkSpeed
        self.skin_id = 'classic'  # an outfit in skins.ROUTINES plays its own routine when awake
        self.rt, self.rt_i, self.rt_key = None, 0, None
        self.confetti = [{'x': 0.0, 'y': 0.0, 'v': 0.0, 'd': 0.0,
                          'color': CONFETTI_COLORS[i % len(CONFETTI_COLORS)]} for i in range(12)]
        self.r = {}
        self.start_act(self.rnd.choice(ENTRANCE_ACTS))

    # -- events ----------------------------------------------------------

    def start_act(self, name):
        self.act = name
        self.act_t = 0
        if name == 'celebrate':
            self.start_confetti()

    def click(self):
        if self.mood == 'dead' or self.cur == 'dead':
            if not self.act:
                self.start_act('soul')
            return
        self.love_t = 0
        if self.buried and self.cur == 'sleep':
            if not self.act:
                self.start_act('stir')
            return
        if self.act:
            return
        self.start_act(self.rnd.choice(CLICK_ACTS))

    def start_confetti(self):
        for c in self.confetti:
            c['x'] = self.x - 12 + self.rnd.random() * (MASCOT_W + 24)
            c['y'] = 34 + self.rnd.random() * 12
            c['v'] = 0.9 + self.rnd.random() * 1.2
            c['d'] = (self.rnd.random() - 0.5) * 0.8
        self.conf_t = 0

    def set_state(self, sessions, usage, crit_level):
        """sessions: list of dicts with busy/waiting; usage: dict or None."""
        busy = sum(1 for s in sessions if s['busy'])
        waiting = sum(1 for s in sessions if s['waiting'])
        pct = usage.get('session') if usage else None

        if pct is not None and pct >= 100:
            mood = 'dead'
        elif waiting:
            mood = 'wait'
        elif busy:
            mood = 'work'
        elif sessions:
            mood = 'idle'
        else:
            mood = 'sleep'
        if mood != self.mood:
            self.idle_since = time.monotonic()
        self.mood = mood

        # A session finished its reply (rather than stopping to wait for us) - jump.
        if self.busy > 0 and busy < self.busy and waiting <= self.waiting and not self.act:
            self.start_act('jump')
        self.busy = busy
        self.waiting = waiting
        self.crit = pct is not None and pct >= crit_level
        self.pct = pct

        # The 5-hour window reset: reset time moved forward, percent dropped - celebrate.
        reset = usage.get('sessionReset') if usage else None
        if reset:
            if (self.last_reset and reset > self.last_reset and
                    self.last_pct is not None and pct is not None and pct < self.last_pct):
                self.start_act('celebrate')
            self.last_reset = reset
            self.last_pct = pct

    def get_halves(self):
        if self.pct is None:
            return None
        h = math.ceil(max(0, 100 - self.pct) * 6 / 100.0)
        return int(min(6, max(0, h)))

    # -- one-shot animations --------------------------------------------

    def step_act(self, f):
        t = self.act_t
        bubble = ''
        if self.act in SEQS:
            fr = SEQS[self.act][t]
            for k in ('eyes', 'arms', 'feet', 'off', 'x', 'facing', 'poof', 'shadow'):
                f[k] = fr[k]
            f['look'] = 0
            if self.act == 'celebrate':
                bubble = '!'
        else:
            a = self.act
            if a == 'wave':
                f['look'] = 0
                f['eyes'] = 'happy'
                f['arms'] = 'down' if (t // 4) % 2 else 'right'
            elif a == 'stretch':
                if 4 <= t < 18:
                    f['arms'] = 'up'
                    f['eyes'] = 'closed'
                    f['lift'] = 1.5
            elif a == 'yawn':
                f['look'] = 0
                f['eyes'] = 'yawn' if 3 <= t < 17 else 'closed'
            elif a == 'stumble':
                if t < 12:
                    f['off'] = 1
                    f['eyes'] = 'closed'
                else:
                    f['eyes'] = 'wide'
                f['look'] = 0
            elif a == 'soul':
                f['flip'] = True
                f['look'] = 0
                if t < 6:
                    f['eyes'] = 'x'
                    f['feet'] = 'left' if t % 2 else 'right'
                elif t < SOUL_BACK + 6:
                    f['eyes'] = 'gasp'
                    f['soulT'] = t
                    if t < SOUL_UP:
                        k = (t - 6) / (SOUL_UP - 6.0)
                        f['soul'] = SOUL_TOP * (1 - (1 - k) * (1 - k))
                    elif t < SOUL_BACK:
                        f['soul'] = SOUL_TOP + 1.5 * math.sin((t - SOUL_UP) / 2.5)
                    else:
                        k = (t - SOUL_BACK) / 6.0
                        f['soul'] = SOUL_TOP * (1 - k * k)
                elif t < SOUL_BACK + 9:
                    f['eyes'] = 'wide'
                    f['lift'] = 2.5
                else:
                    f['eyes'] = 'x'
            elif a == 'burrow':
                if t < 4:
                    f['look'] = -1 if t < 2 else 1
                elif t < 24:
                    f['look'] = 0
                    f['eyes'] = 'focus'
                    f['dig'] = min(BURROW_DIG, math.floor((t - 4) / 3.5))
                    f['feet'] = 'left' if (t // 2) % 2 else 'right'
                    f['arms'] = 'up' if (t // 2) % 2 else 'down'
                    f['spray'] = (t % 3) + 1
                else:
                    f['look'] = 0
                    f['dig'] = BURROW_DIG
                    f['eyes'] = 'blink' if t < 27 else 'closed'
            elif a == 'unburrow':
                f['look'] = 0
                if t < 3:
                    f['dig'] = BURROW_DIG
                    f['eyes'] = 'wide'
                elif t < 9:
                    f['dig'] = max(0, BURROW_DIG - (t - 3))
                    f['eyes'] = 'wide'
                    f['arms'] = 'up'
                    f['spray'] = (t % 3) + 1
                    if t == 8:
                        f['lift'] = 2
                elif t < 21:
                    f['eyes'] = 'closed'
                    f['look'] = -1 if (t // 2) % 2 else 1
                    f['feet'] = 'left' if (t // 2) % 2 else 'right'
                    if t < 15:
                        f['spray'] = (t % 3) + 1
                elif t < 23:
                    f['eyes'] = 'blink'
            elif a == 'stir':
                f['dig'] = BURROW_DIG - 1 if t < 15 else BURROW_DIG
                if t < 3:
                    f['eyes'] = 'wide'
                    f['look'] = 0
                elif t < 13:
                    f['look'] = -1 if t < 8 else 1
                elif t < 17:
                    f['eyes'] = 'blink'
                    f['look'] = 0
                else:
                    f['eyes'] = 'closed'
                    f['look'] = 0
        self.act_t += 1
        if self.act_t >= ACT_LEN[self.act]:
            self.act = None
        return bubble

    # -- per-frame step ---------------------------------------------------

    def step(self, area_w, mouse_x, hovered):
        """area_w: mascot area width in units; mouse_x: cursor x in area units or
        None; hovered: cursor over the window."""
        self.tick += 1
        rnd = self.rnd
        span = max(0.0, area_w - MASCOT_W)
        if self.x < 0:
            self.x = span / 2
        if self.x > span:
            self.x = span

        def mouse_look():
            if mouse_x is None:
                return None
            cx = self.x + MASCOT_W / 2
            if mouse_x > cx + 10:
                return 1
            if mouse_x < cx - 10:
                return -1
            return 0

        mood = self.mood
        halves = self.get_halves()
        tier_n = 5 if halves is None else halves
        tier = HEALTH[tier_n]
        perky = tier['speed'] >= 0.9
        now = time.monotonic()
        if hovered:
            self.idle_since = now
        if mood == 'idle' and now - self.idle_since >= 600:
            mood = 'doze'

        if mood == 'sleep':
            if not self.buried and not self.act:
                self.buried = True
                self.start_act('burrow')
        elif self.buried:
            self.buried = False
            self.start_act('unburrow')

        f = {'feet': 'both', 'look': self.look, 'eyes': 'open', 'arms': 'down', 'flip': False,
             'lift': 0.0, 'off': 0, 'x': 0, 'facing': '', 'poof': '', 'shadow': '',
             'soul': 0.0, 'soulT': 0, 'dig': 0, 'spray': 0, 'prop': 0}
        self.cur = mood
        bubble, zzz, can_blink, dust = '', False, True, False

        if self.act:
            bubble = self.step_act(f)
            can_blink = False
        elif mood == 'sleep':
            f.update(dig=BURROW_DIG, eyes='closed', look=0)
            zzz = True
        elif mood == 'doze':
            f['look'] = 0
            p = self.tick % 70
            if p < 6:
                f['eyes'] = 'wide'
                if p < 2:
                    f['lift'] = 1.5
            else:
                f['eyes'] = 'blink'
                zzz = True
        elif mood == 'dead':
            f.update(flip=True, eyes='x', look=0)
            p = self.tick % 50
            if p < 6:
                f['feet'] = 'left' if p % 2 else 'right'
        elif mood == 'wait':
            bubble = '?'
            f['eyes'] = 'wide'
            ml = mouse_look()
            f['look'] = ml if ml is not None else 0
            p = self.tick % 40
            if p < 8:
                k = p / 7.0
                f['lift'] = 12 * k * (1 - k)
                f['arms'] = 'right'
        elif self.skin_id in ROUTINES and mood in ('idle', 'work'):
            self.step_routine(f, area_w)
        else:
            if mood == 'work':
                speed = 1.6 * tier['speed'] * self.walk_speed
                if self.target is None:
                    self.target = span if self.dir > 0 else 0.0
            else:
                speed = 0.6 * tier['speed'] * self.walk_speed
                if self.target is None:
                    if rnd.randrange(70) == 0:
                        self.target = rnd.random() * span
                    elif rnd.randrange(45) == 0:
                        self.look = rnd.randint(-1, 1)
                    elif rnd.randrange(400) == 0:
                        self.start_act(rnd.choice(['wave', 'stretch', 'look']))
            walking = False
            if self.target is not None:
                d = self.target - self.x
                if abs(d) <= speed:
                    self.x = self.target
                    self.target = None
                    if mood == 'work':
                        self.dir = -self.dir
                else:
                    self.dir = 1 if d > 0 else -1
                    self.x += speed * self.dir
                    self.look = self.dir
                    walking = True
            if walking:
                step = 2 if mood == 'work' else 3
                if tier['speed'] < 0.8:
                    step += 1
                if tier['speed'] < 0.5:
                    step += 1
                f['feet'] = 'left' if (self.tick // step) % 2 else 'right'
                dust = True
                if mood == 'work':
                    if f['feet'] == 'left' and perky:
                        f['lift'] = 1
                    if perky and rnd.randrange(150) == 0:
                        self.start_act('jump')
                elif perky and self.note_t < 0 and rnd.randrange(80) == 0:
                    self.note_t = 0
                if tier.get('stumble') and rnd.randrange(tier['stumble']) == 0:
                    self.start_act('stumble')
            elif self.crit:
                self.look = -1 if (self.tick // 5) % 2 else 1
            else:
                ml = mouse_look()
                if ml is not None:
                    self.look = ml
            f['look'] = self.look
            if mood == 'work':
                f['eyes'] = 'focus'
            if not self.act:
                if tier.get('hop') and rnd.randrange(tier['hop']) == 0:
                    self.start_act('jump')
                if tier.get('yawn') and rnd.randrange(tier['yawn']) == 0:
                    self.start_act('yawn')

        if tier.get('eyes') and not self.act and f['eyes'] in ('open', 'focus'):
            f['eyes'] = tier['eyes']
        if self.love_t >= 0 and not self.act and f['eyes'] == 'open':
            f['eyes'] = 'happy'
        if self.note_t >= 0:
            if not bubble and mood == 'idle':
                bubble = '♪'
            self.note_t += 1
            if self.note_t >= 30:
                self.note_t = -1

        if can_blink and f['eyes'] == 'open' and self.tick >= self.blink_at:
            f['eyes'] = 'blink'
            if self.tick >= self.blink_at + 1:
                self.blink_at = self.tick + rnd.randint(25, 69)

        rx = self.x
        if tier.get('stagger') and mood not in ('sleep', 'dead'):
            rx += 1.5 * math.sin(self.tick / 3.0)

        r = {
            'geo': geometry(f), 'x': round(rx), 'lift': f['lift'], 'dig': f['dig'],
            'off': f['off'], 'look': f['look'], 'bubble': bubble,
            'interval': FRAME_MS if (self.act and self.act in SEQS) else STEP_MS,
            'zzz': None, 'sweat': None, 'dust': [], 'confetti': [], 'love': None, 'soul': None,
            'f': f,
        }
        if zzz:
            p = (self.tick % 30) / 30.0
            zb = 9 if f['dig'] > 0 else (12 if f['off'] > 0 else 19)
            r['zzz'] = {'size': 7 + 4 * p, 'opacity': 1 - p,
                        'left': self.x + 28 + 3 * math.sin(p * 2 * math.pi),
                        'bottom': zb + 14 * p}
        if (self.crit or tier.get('sweat')) and mood not in ('sleep', 'dead'):
            p = (self.tick % 20) / 20.0
            r['sweat'] = {'opacity': 1 - p, 'left': 31 if f['look'] < 0 else 2,
                          'top': -2 + 6 * p - f['lift']}

        self.step_hearts()

        if dust:
            for i in range(3):
                p = ((self.tick + i * 3) % 9) / 9.0
                dx = (4 - 8 * p - 2 * i) if self.dir > 0 else (MASCOT_W - 6 + 8 * p + 2 * i)
                r['dust'].append({'left': self.x + dx, 'bottom': 4 * p, 'opacity': 0.7 * (1 - p)})

        if self.conf_t >= 0:
            for i, c in enumerate(self.confetti):
                c['y'] -= c['v']
                c['x'] += c['d']
                if c['y'] > 0:
                    w = 2.5 if ((self.tick + i) // 2) % 2 else 1.2
                    r['confetti'].append({'left': c['x'], 'bottom': c['y'], 'w': w, 'color': c['color']})
            self.conf_t += 1
            if self.conf_t >= 45:
                self.conf_t = -1

        if self.love_t >= 0:
            k = self.love_t / 20.0
            r['love'] = {'opacity': 1 - k,
                         'left': self.x + MASCOT_W / 2 - 5 + 2 * math.sin(k * 6),
                         'bottom': 23 + f['lift'] + 14 * k}
            self.love_t += 1
            if self.love_t >= 20:
                self.love_t = -1

        if f['soul'] > 0.5:
            r['soul'] = {'rects': soul_rects(f['soul'], f['soulT']),
                         'opacity': 0.7 + 0.15 * math.sin(f['soulT'] / 1.7),
                         'left': self.x + 9.5 * PX, 'lift': f['lift']}
        self.r = r
        return r

    def step_routine(self, f, area_w):
        # Keep room on his right for what he holds (pan, laptop, lens).
        max_x = max(0, int((area_w - (GW + 9) * PX) // PX))
        key = (self.skin_id, self.crit, max_x)
        if self.rt is None or self.rt_key != key or self.rt_i >= len(self.rt):
            start = max(0, min(max_x, round(self.x / PX)))
            self.rt, self.rt_i, self.rt_key = routine(self.skin_id, self.crit, start, max_x), 0, key
        gx, rf = self.rt[self.rt_i]
        self.rt_i += 1
        self.x = gx * PX
        self.target = None
        self.look = rf['look']
        for k in ('eyes', 'arms', 'feet', 'look', 'off', 'prop'):
            f[k] = rf[k]
        f['lift'] = rf['lift'] * PY

    def step_hearts(self):
        halves = self.get_halves()
        if halves is None:
            self.halves = None
            self.show_halves = None
            return
        if self.halves is not None and halves < self.halves:
            self.lost_t = 0
            self.lost_from = self.halves
        self.halves = halves
        show = halves
        if self.lost_t >= 0:
            if self.lost_t % 4 < 2:
                show = self.lost_from
            self.lost_t += 1
            if self.lost_t >= 16:
                self.lost_t = -1
        self.show_halves = show
        beat = 1.0
        if 0 < halves <= 2:
            p = self.tick % 12
            beat = 1.3 if p == 0 else (1.15 if p == 1 else 1.0)
        self.beat = beat

    def hearts_tooltip(self):
        h = self.get_halves()
        if h is None:
            return ''
        return f'{HEALTH_NAMES[h]} · {100 - self.pct}% of the session limit left'
