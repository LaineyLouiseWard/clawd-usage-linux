#!/usr/bin/env python3
"""Clawd Usage for Linux - a floating window + tray icon showing Claude plan usage.

Port of clawd-usage-winwidget (https://github.com/Enhed/clawd-usage-winwidget, MIT)
to Python + Qt 6. Data sources are the same as the original:

  * `claude -p /usage --output-format text`  - limit percentages, no tokens spent
  * ~/.claude/sessions/<pid>.json             - running Claude Code sessions
  * `claude auth status`                      - plan and email
  * status.claude.com summary.json            - service status
  * downloads.claude.ai                       - latest Claude Code version
"""

import json
import math
import os
import re
import shutil
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import (QEasingCurve, QPoint, QPointF, QProcess, QRectF, QSize, Qt, QTimer, QUrl,
                          QVariantAnimation)
from PyQt6.QtGui import (QAction, QActionGroup, QBrush, QColor, QCursor, QDesktopServices, QFont,
                         QIcon, QPainter, QPainterPath, QPixmap)
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu,
                             QSizePolicy, QSystemTrayIcon, QVBoxLayout, QWidget)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import codestats as CS  # noqa: E402
import mascot as M  # noqa: E402
import scenes as SC  # noqa: E402
import skins as SKN  # noqa: E402
import sky as SK  # noqa: E402
import split as SP  # noqa: E402
import themes as TH  # noqa: E402

APP_VERSION = '1.0.0'
APP_ID = 'clawd-usage'
HOME = Path.home()
CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config')) / APP_ID
CONFIG_PATH = CONFIG_DIR / 'config.json'
SESSIONS_DIR = HOME / '.claude' / 'sessions'
STATUS_URL = 'https://status.claude.com'
LATEST_URL = 'https://downloads.claude.ai/claude-code-releases/latest'

DEFAULTS = {
    'scale': 1.35,
    'expanded': False,
    'topmost': False,
    'opacity': 1.0,
    'warnPercent': 60,
    'critPercent': 85,
    'usageIntervalSeconds': 60,
    'statusIntervalSeconds': 120,
    'accountIntervalSeconds': 600,
    'versionIntervalSeconds': 3600,
    'showMascot': True,
    'showSessions': True,
    'showStatus': True,
    'showStats': True,
    'showSky': True,               # sky behind Clawd: time of day and real weather
    'weatherIntervalSeconds': 900,
    'weatherLat': None,            # coordinates; empty - detect by IP (ipwho.is)
    'weatherLon': None,
    'walkSpeed': 1.6,              # Clawd's walking speed, 1.0 = the original
    'mainSource': 'all',           # big number: all / code / cowork / chat (the last three are estimates)
    'codeIntervalSeconds': 60,     # how often to re-read Claude Code's and Cowork's local logs
    'showAccount': True,
    'showFable': True,             # the weekly Fable row (hidden anyway when /usage doesn't report it)
    'showDetailsButton': True,     # the ▾ button that opens Details
    'showStamp': True,             # time of the last reading, bottom right
    'theme': 'auto',               # auto (follows the season) or a theme id from themes.py
    'skin': 'auto',                # Clawd's outfit: auto (the theme's), classic, or a file name in skins/
    'startHidden': False,
    'hoverOpen': True,             # card stays a slim bar until the mouse is on it (or it's clicked)
    'closeDelaySeconds': 2,        # how long it stays open after the mouse leaves
    'left': None,
    'top': None,
}

COL = {
    'ok': '#4ADE80', 'warn': '#FBBF24', 'crit': '#F87171', 'dead': '#6B7280',
    'card': '#1A1A1E', 'border': '#33FFFFFF', 'muted': '#8B8B94', 'label': '#6B7280',
    'text': '#D4D4D8', 'faint': '#52525B', 'track': '#26FFFFFF', 'rule': '#1AFFFFFF',
    'week': '#60A5FA', 'fable': '#A78BFA', 'heartOff': '#3F3F46', 'note': '#93C5FD',
}


def qcolor(s):
    """'#AARRGGBB' or '#RRGGBB' (Qt reads 8-digit hex as ARGB too)."""
    return QColor(s)


# ---------------------------------------------------------------- config ----

def load_config():
    cfg = dict(DEFAULTS)
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
        for k, v in raw.items():
            if k in cfg:
                cfg[k] = v
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f'config.json unreadable, using defaults: {e}', file=sys.stderr)
    return cfg


def save_config(cfg):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        out = {}
        try:
            out = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
        except Exception:
            pass
        out.update(cfg)
        tmp = CONFIG_PATH.with_suffix('.tmp')
        tmp.write_text(json.dumps(out, indent=2), encoding='utf-8')
        tmp.replace(CONFIG_PATH)
    except Exception as e:
        print(f'could not save config.json: {e}', file=sys.stderr)


# --------------------------------------------------------------- parsing ----

MONTHS = {m: i + 1 for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'])}


def parse_reset(s):
    """'Oct 17, 5:19am (Europe/Moscow)' or 'Oct 21, 6am' -> local datetime."""
    if not s:
        return None
    m = re.search(r'([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{1,2})(?::(\d{2}))?\s*([ap]m)', s)
    if not m:
        return None
    mon = MONTHS.get(m.group(1).lower())
    if not mon:
        return None
    hour = int(m.group(3)) % 12 + (12 if m.group(5) == 'pm' else 0)
    try:
        now = datetime.now()
        dt = datetime(now.year, mon, int(m.group(2)), hour, int(m.group(4) or 0))
    except ValueError:
        return None
    # Around New Year the date may land in the past - then it is next year.
    if dt < now - timedelta(days=30):
        dt = dt.replace(year=dt.year + 1)
    return dt


STAT_RULES = [
    (r'^(\d+)% of your usage was at >(\S+) context', '{0}% at >{1} context'),
    (r'^(\d+)% of your usage went to always-on context over (\S+)', '{0}% always-on context >{1}'),
    (r'^(\d+)% of your usage came from subagent-heavy', '{0}% subagent-heavy sessions'),
    (r'^(\d+)% of your usage came from sessions active for (\d+)\+? hours', '{0}% sessions {1}h+'),
    (r'^Top MCP servers:\s*(.+)$', 'MCP: {0}'),
    (r'^Top skills:\s*(.+)$', 'skills: {0}'),
    (r'^Top subagents:\s*(.+)$', 'subagents: {0}'),
]


def format_stat(line):
    for rx, fmt in STAT_RULES:
        m = re.match(rx, line)
        if m:
            return fmt.format(*m.groups())
    return line   # unknown metrics are kept as is


def parse_period(text, label):
    m = re.search(r'(?m)^' + re.escape(label) +
                  r'[^\r\n]*?(\d+)\s+requests?\b[^\r\n]*?(\d+)\s+sessions?\b[^\r\n]*\r?\n'
                  r'((?:[ \t]+[^\r\n]*\r?\n?)*)', text)
    if not m:
        return None
    lines = [ln.strip() for ln in m.group(3).splitlines() if ln.strip()]
    return {'requests': int(m.group(1)), 'sessions': int(m.group(2)), 'lines': lines}


def parse_usage(text):
    u = {}
    for key, rx in (('session', r'Current session:'),
                    ('week', r'Current week \(all models\):'),
                    ('fable', r'Current week \(Fable\):')):
        # No "resets" means the window hasn't started - that is 0%, not "no data".
        m = re.search(rx + r'\s*(\d+)%(?:[^\r\n]*?resets\s*([^\r\n]+))?', text)
        u[key] = int(m.group(1)) if m else None
        u[key + 'Reset'] = parse_reset(m.group(2)) if m else None
    u['day'] = parse_period(text, 'Last 24h')
    u['week7'] = parse_period(text, 'Last 7d')
    if u['session'] is None and u['week'] is None:
        return None
    return u


def format_span(end):
    secs = (end - datetime.now()).total_seconds()
    if secs <= 0:
        return None
    mins = int(secs // 60)
    h, m = divmod(mins, 60)
    if h >= 24:
        return f'{h // 24}d {h % 24}h'
    if h >= 1:
        return f'{h}h {m:02d}m'
    return f'{m}m'


# -------------------------------------------------------------- sessions ----

def proc_stat(pid):
    """(parent pid, start time in clock ticks since boot) from /proc/<pid>/stat."""
    try:
        data = Path(f'/proc/{pid}/stat').read_text()
        rest = data[data.rindex(')') + 2:].split()   # fields 3.. ; comm may contain spaces
        return int(rest[1]), int(rest[19])
    except (OSError, ValueError, IndexError):
        return None


def get_sessions(own_pids):
    out = []
    try:
        files = list(SESSIONS_DIR.glob('*.json'))
    except OSError:
        return out
    for f in files:
        try:
            j = json.loads(f.read_text(encoding='utf-8'))
        except Exception:
            continue
        pid = j.get('pid')
        if not isinstance(pid, int) or pid in own_pids:
            continue
        # Files outlive their processes; a reused PID has a different start time.
        st = proc_stat(pid)
        if st is None:
            continue
        ppid, start = st
        if ppid == os.getpid():          # our own `claude -p /usage` probe
            continue
        ps = j.get('procStart')
        if ps is not None:
            try:
                if abs(int(ps) - start) > 2:
                    continue
            except (TypeError, ValueError):
                pass
        name = j.get('name') or (os.path.basename(str(j.get('cwd', '')).rstrip('/')) or '?')
        out.append({'name': name, 'cwd': j.get('cwd', ''), 'busy': j.get('status') == 'busy',
                    'waiting': j.get('status') == 'waiting', 'waitingFor': j.get('waitingFor') or '',
                    'kind': j.get('kind', ''), 'pid': pid})
    out.sort(key=lambda s: s['name'].lower())
    return out


# ---------------------------------------------------------- background IO ----

def find_claude():
    p = shutil.which('claude')
    if p:
        return p
    for c in (HOME / '.local/bin/claude', HOME / '.claude/local/claude', Path('/usr/local/bin/claude')):
        if c.exists():
            return str(c)
    return None


class Probe:
    """A `claude ...` subprocess run asynchronously through QProcess."""

    def __init__(self, exe, args, timeout_s, on_done):
        self.exe, self.args, self.timeout_s, self.on_done = exe, args, timeout_s, on_done
        self.proc = None
        self.started = 0.0
        self.last_try = 0.0

    def pid(self):
        if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning:
            return int(self.proc.processId())
        return None

    def running(self):
        return self.pid() is not None

    def start(self):
        if self.running() or not self.exe:
            return
        self.last_try = time.time()
        p = QProcess()
        p.setWorkingDirectory(str(HOME))
        p.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        p.finished.connect(lambda code, status, p=p: self._finished(p, code))
        self.proc = p
        self.started = time.monotonic()
        p.start(self.exe, self.args)
        # Otherwise `claude -p` waits 3 s for piped stdin before running.
        p.closeWriteChannel()

    def _finished(self, p, code):
        out = bytes(p.readAllStandardOutput()).decode('utf-8', 'replace')
        if p is self.proc:
            self.proc = None
        p.deleteLater()
        self.on_done(out if code == 0 else None)

    def stop(self):
        p, self.proc = self.proc, None
        if p and p.state() != QProcess.ProcessState.NotRunning:
            p.finished.disconnect()
            p.kill()
            p.waitForFinished(1000)

    def check_timeout(self):
        if self.running() and time.monotonic() - self.started > self.timeout_s:
            self.proc.kill()


class HttpProbe:
    """GET a URL in a worker thread; result is picked up on the GUI thread."""

    def __init__(self, url, on_done):
        self.url, self.on_done = url, on_done
        self.thread = None
        self.result = None
        self.done = False
        self.last_try = 0.0

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.last_try = time.time()
        self.done = False

        def run():
            try:
                req = urllib.request.Request(self.url, headers={
                    'User-Agent': f'clawd-usage-linux/{APP_VERSION}', 'Cache-Control': 'no-cache'})
                with urllib.request.urlopen(req, timeout=15) as r:
                    self.result = r.read().decode('utf-8', 'replace')
            except Exception:
                self.result = None
            self.done = True
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def collect(self):
        if self.done:
            self.done = False
            self.on_done(self.result)


# ------------------------------------------------------------- widgets ----

class Bar(QWidget):
    def __init__(self, height, radius, color, s):
        super().__init__()
        self.frac = 0.0
        self.ghost = 0.0
        self.color = color
        self.radius = radius * s
        self.setFixedHeight(max(2, round(height * s)))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set(self, frac, color=None, ghost=0.0):
        frac = max(0.0, min(1.0, frac))
        ghost = max(0.0, min(1.0, ghost))
        if frac != self.frac or ghost != self.ghost or (color and color != self.color):
            self.frac = frac
            self.ghost = ghost
            if color:
                self.color = color
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        r = QRectF(self.rect())
        p.setBrush(qcolor(COL['track']))
        p.drawRoundedRect(r, self.radius, self.radius)
        if self.ghost > self.frac:
            p.setBrush(qcolor('#40FFFFFF'))
            p.drawRoundedRect(QRectF(0, 0, max(r.height(), r.width() * self.ghost), r.height()),
                              self.radius, self.radius)
        if self.frac > 0:
            w = max(r.height(), r.width() * self.frac)
            p.setBrush(qcolor(self.color))
            p.drawRoundedRect(QRectF(0, 0, w, r.height()), self.radius, self.radius)


class Hearts(QWidget):
    def __init__(self, mascot, s):
        super().__init__()
        self.m = mascot
        self.s = s
        self.full = M.heart_rects(6)
        self.half = M.heart_rects(3)
        w = (3 * 7 * M.HEART_PX + 2 * 2.5) * s
        self.setFixedSize(round(w) + 4, round(6 * M.HEART_PX * s) + 4)

    def paintEvent(self, e):
        show = self.m.show_halves
        if show is None:
            return
        p = QPainter(self)
        p.setPen(Qt.PenStyle.NoPen)
        s = self.s
        cell = 7 * M.HEART_PX
        for i in range(3):
            p.save()
            cx = 2 + (i * (cell + 2.5) + cell / 2) * s
            cy = 2 + 3 * M.HEART_PX * s
            p.translate(cx, cy)
            p.scale(s * self.m.beat, s * self.m.beat)
            p.translate(-cell / 2, -3 * M.HEART_PX)
            p.setBrush(qcolor(COL['heartOff']))
            for x, y, w, h in self.full:
                p.drawRect(QRectF(x, y, w + 0.02, h + 0.02))
            h_ = show - 2 * i
            rects = self.full if h_ >= 2 else (self.half if h_ == 1 else [])
            p.setBrush(qcolor(COL['crit']))
            for x, y, w, h in rects:
                p.drawRect(QRectF(x, y, w + 0.02, h + 0.02))
            p.restore()


class MascotArea(QWidget):
    """Canvas where Clawd lives; all drawing is in mascot units scaled by s."""
    AREA_H = 50.0

    def __init__(self, mascot, s, on_click):
        super().__init__()
        self.m = mascot
        self.s = s
        self.on_click = on_click
        self.skin = SKN.CLASSIC
        self.scene = None          # a scene from scenes.py behind Clawd, or None
        self.scene_img = None
        self.area_h = self.AREA_H
        self.setFixedHeight(round(self.area_h * s))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_scene(self, scene):
        # A scene is drawn in Clawd's own pixels, so it needs its full height.
        self.scene = scene
        self.scene_img = None
        self.area_h = SC.H * M.PY if scene else self.AREA_H
        self.setFixedHeight(round(self.area_h * self.s))

    def ground(self):
        """How far Clawd stands above the bottom edge: on the scene's ground."""
        return SC.GROUND * M.PY if self.scene else 0.0

    def area_w(self):
        return self.width() / self.s

    def mouse_x(self):
        if not self.window().underMouse():
            return None
        return self.mapFromGlobal(QCursor.pos()).x() / self.s

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(e)
        r = self.m.r
        if r:
            x = e.position().x() / self.s
            bottom = self.area_h - self.ground() - (r['lift'] - M.SINK)
            if r['x'] - 4 <= x <= r['x'] + M.MASCOT_W + 4 and e.position().y() / self.s >= bottom - M.MASCOT_H - 4:
                self.on_click()
                return
        # Not on Clawd: drag the window like the rest of the card.
        self.window().start_drag(e)

    def paintEvent(self, e):
        r = self.m.r
        if not r:
            return
        H = self.area_h
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.scale(self.s, self.s)
        p.setPen(Qt.PenStyle.NoPen)
        if self.scene_img is not None:
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(0, 0, self.area_w(), H), 6, 6)
            p.setClipPath(clip)
            iw = self.scene_img.width()
            p.drawImage(QRectF(0, 0, iw * M.PX, SC.H * M.PY), self.scene_img)
            p.translate(0, -self.ground())

        def rects(lst, color, ox, oy, opacity=1.0):
            if not lst:
                return
            c = qcolor(color)
            c.setAlphaF(c.alphaF() * opacity)
            p.setBrush(c)
            for x, y, w, h in lst:
                # Tiny overlap so adjacent rects don't show seams when scaled.
                p.drawRect(QRectF(ox + x, oy + y, w + 0.05, h + 0.05))

        # Mascot box: Canvas.Left = x, Canvas.Bottom = lift - sink.
        top = H - (r['lift'] - M.SINK) - M.MASCOT_H
        ox = r['x']
        g = r['geo']
        skin = self.skin
        rects(g['body'], skin.body, ox, top)
        rects(g['eyes'], skin.eyes, ox, top)
        rects(g['fx'], M.FX, ox, top)
        rects(g['sand'], SC.sand(self.scene) if self.scene else M.SAND, ox, top)
        f = r['f']
        if not f['flip']:
            dx = 2 * int(f['x'])
            dy = 4 * int(f['off']) + int(f['dig'])
            lim = M.GH - 2 if f['dig'] > 0 else M.GH
            # Outfit: what is above his head stays on while he turns; on his back it all comes off.
            for color, pts in skin.layers:
                keep = []
                for x, y in pts:
                    xx, yy = x + dx, y + dy
                    if (y >= 0 and f['facing']) or xx < 0 or xx >= M.GW or yy >= lim:
                        continue
                    if (dy < 0) if y < 0 else (yy < 0):
                        continue
                    keep.append((xx * M.PX, yy * M.PY, M.PX, M.PY))
                rects(keep, color, ox, top)
            if not f['dig'] and not f['facing']:
                rest = round(r['lift'] / M.PY)
                for x, y, argb in SKN.props(skin.id, f, self.m.tick, dx, dy, rest):
                    p.setBrush(QColor.fromRgba(argb))
                    p.drawRect(QRectF(ox + x * M.PX, top + y * M.PY, M.PX + 0.05, M.PY + 0.05))
        if r['sweat']:
            sw = r['sweat']
            rects([(sw['left'], sw['top'], 3, 4.5)], '#7DD3FC', ox, top, sw['opacity'])

        for d in r['dust']:
            rects([(d['left'], H - d['bottom'] - 2, 2, 2)], COL['muted'], 0, 0, d['opacity'])
        for c in r['confetti']:
            rects([(c['left'], H - c['bottom'] - 2.5, c['w'], 2.5)], c['color'], 0, 0)
        if r['love']:
            lv = r['love']
            rects(M.heart_rects(6), COL['crit'], lv['left'], H - lv['bottom'] - 6 * M.HEART_PX, lv['opacity'])
        if r['soul']:
            so = r['soul']
            rects(so['rects'], '#F4F4F5', so['left'], H - (so['lift'] + 6 * M.PY), so['opacity'])

        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        if r['zzz']:
            z = r['zzz']
            f = QFont(self.font())
            f.setPixelSize(max(1, round(z['size'])))
            f.setWeight(QFont.Weight.DemiBold)
            p.setFont(f)
            c = qcolor(COL['muted'])
            c.setAlphaF(max(0.0, z['opacity']))
            p.setPen(c)
            p.drawText(QPointF(z['left'], H - z['bottom'] - p.fontMetrics().descent()), 'z')
        if r['bubble']:
            b = r['bubble']
            f = QFont(self.font())
            f.setPixelSize(11)
            f.setWeight(QFont.Weight.Bold)
            p.setFont(f)
            p.setPen(qcolor({'?': COL['warn'], '!': COL['ok']}.get(b, COL['note'])))
            bottom = 22 + r['lift'] + 1.5 * math.sin(self.m.tick / 3.0)
            box = QRectF(r['x'] + M.MASCOT_W / 2 - 6, H - bottom - 15, 12, 15)
            p.drawText(box, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom), b)



def label(text, size, color, s, weight=None, wrap=False):
    lb = QLabel(text)
    f = lb.font()
    f.setPixelSize(max(1, round(size * s)))
    if weight:
        f.setWeight(weight)
    lb.setFont(f)
    lb.setStyleSheet(f'color: {color}; background: transparent;')
    lb.setWordWrap(wrap)
    if wrap:
        WRAPPED.append(lb)
    return lb


# Word-wrapped labels; Qt doesn't size them to their text in a fixed-width
# window, so render() sets each one's height from heightForWidth().
WRAPPED = []


class SkyRow(QWidget):
    """The percent + Clawd row, with the sky painted behind both."""

    def __init__(self, sky, s, cfg):
        super().__init__()
        self.sky, self.s, self.cfg = sky, s, cfg
        self.themed = False        # a theme's scene replaces the weather sky

    def paintEvent(self, e):
        if not self.cfg['showSky'] or self.themed:
            return
        p = QPainter(self)
        self.sky.paint(p, self.width() / self.s, self.height() / self.s, self.s)


class Chip(QLabel):
    """A small pill; one of a group of choices."""

    def __init__(self, text, s, on_click):
        super().__init__(text)
        self.s = s
        self.on_click = on_click
        f = self.font()
        f.setPixelSize(max(1, round(9.5 * s)))
        self.setFont(f)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_on(False)

    def set_on(self, on, color=None):
        pad = f'{round(2 * self.s)}px {round(7 * self.s)}px'
        rad = round(8 * self.s)
        if on:
            ss = (f'color: {color or COL["text"]}; background: #1FFFFFFF; border: 1px solid {color or COL["muted"]};'
                  f' border-radius: {rad}px; padding: {pad};')
        else:
            ss = (f'color: {COL["label"]}; background: transparent; border: 1px dashed {COL["faint"]};'
                  f' border-radius: {rad}px; padding: {pad};')
        if self.styleSheet() != ss:
            self.setStyleSheet(ss)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.on_click()


class Clip(QWidget):
    """Shows the top `frac` of its child at full size, so opening looks like a blind
    being pulled down instead of the rows getting squashed."""

    def __init__(self, child):
        super().__init__()
        self.child = child
        child.setParent(self)
        self.frac = 1.0
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def full_height(self):
        lay = self.child.layout()
        lay.activate()
        w = self.width()
        return lay.heightForWidth(w) if lay.hasHeightForWidth() and w > 0 else lay.sizeHint().height()

    def sizeHint(self):
        return QSize(self.child.sizeHint().width(), round(self.full_height() * self.frac))

    def minimumSizeHint(self):
        return QSize(0, self.sizeHint().height())

    def set_frac(self, f):
        self.frac = max(0.0, min(1.0, f))
        self.child.setVisible(self.frac > 0)
        self.place()
        self.updateGeometry()

    def place(self):
        self.child.setGeometry(0, 0, self.width(), self.full_height())

    def resizeEvent(self, e):
        self.place()

    def event(self, e):
        if e.type() == e.Type.LayoutRequest:   # the child's content changed size
            self.place()
            self.updateGeometry()
        return super().event(e)


class Card(QFrame):
    PATTERN_DIR = Path(__file__).resolve().parent / 'patterns'

    def __init__(self, s):
        super().__init__()
        self.s = s
        self.bg = COL['card']
        self.pattern = None
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def set_theme(self, theme):
        self.bg = theme.bg
        self.pattern = None
        pm = QPixmap(str(self.PATTERN_DIR / f'{theme.pattern}.png')) if theme.pattern else QPixmap()
        if not pm.isNull():
            # Pinch's tiles use 6 px per pattern pixel; at the default scale 1.35 this gives 2.
            k = self.s / 4.05
            self.pattern = pm.scaled(max(1, round(pm.width() * k)), max(1, round(pm.height() * k)),
                                     transformMode=Qt.TransformationMode.FastTransformation)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        rad = 10 * self.s
        path.addRoundedRect(r, rad, rad)
        p.fillPath(path, qcolor(self.bg))
        if self.pattern:
            p.fillPath(path, QBrush(self.pattern))
        p.setPen(qcolor(COL['border']))
        p.drawPath(path)


# -------------------------------------------------------------- window ----

class Widget(QWidget):
    def __init__(self, cfg, claude_exe):
        super().__init__()
        self.cfg = cfg
        self.s = s = float(cfg['scale'])
        self.claude = claude_exe
        self.usage = None
        self.usage_at = None
        self.usage_failed = False
        self.sessions = []
        self.status = None
        self.account = None
        self.local_ver = None
        self.latest_ver = None
        self.quitting = False

        self.m = M.Mascot()
        self.m.walk_speed = float(cfg['walkSpeed'])
        self.weather = SK.Weather()
        self.sky = SK.Sky(self.weather, cfg)
        self.skins = SKN.load_all()
        self.scene_cache = SC.SceneCache()
        self.theme_key = None
        self.code = CS.CodeStats()
        self.cowork = CS.CodeStats(CS.COWORK)
        self.split = SP.Split()
        if cfg['mainSource'] not in SP.SOURCES:
            cfg['mainSource'] = 'all'

        self.setWindowTitle('Clawd Usage')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.apply_flags()
        self.setWindowOpacity(float(cfg['opacity']))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.card = Card(s)
        self.card.setFixedWidth(round(262 * s))
        outer.addWidget(self.card)
        v = QVBoxLayout(self.card)
        v.setContentsMargins(round(12 * s), round(10 * s), round(12 * s), round(11 * s))
        v.setSpacing(0)
        semi = QFont.Weight.DemiBold

        # header
        hdr = QHBoxLayout()
        hdr.setSpacing(round(9 * s))
        hdr.addWidget(label('CLAUDE USAGE', 9.5, COL['muted'], s, semi))
        self.mini_pct = label('--%', 10.5, COL['dead'], s, semi)
        hdr.addWidget(self.mini_pct)
        hdr.addStretch(1)
        self.hearts = Hearts(self.m, s)
        hdr.addWidget(self.hearts)
        hdr.addSpacing(round(3 * s))
        self.btn_toggle = self.header_button('▾', 11, 'Details', self.toggle_details)
        self.btn_toggle.setVisible(bool(cfg['showDetailsButton']))
        self.btn_hide = self.header_button('–', 13, 'Hide to tray', self.hide_to_tray)
        self.btn_exit = self.header_button('✕', 11, 'Quit', self.quit)
        for b in (self.btn_toggle, self.btn_hide, self.btn_exit):
            hdr.addWidget(b)
        v.addLayout(hdr)
        # Everything below the header lives in `body`, which slides open on hover.
        card_v = v
        self.body = QWidget()
        v = QVBoxLayout(self.body)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addSpacing(round(6 * s))

        # big percent + mascot
        self.sky_row = SkyRow(self.sky, s, cfg)
        row = QHBoxLayout(self.sky_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.pct = label('--', 30, COL['dead'], s, QFont.Weight.Light)
        self.pct_sign = label('%', 14, COL['muted'], s)
        pv = QVBoxLayout()
        pv.addStretch(1)
        ph = QHBoxLayout()
        ph.setSpacing(round(2 * s))
        ph.addWidget(self.pct, 0, Qt.AlignmentFlag.AlignBottom)
        sign_box = QVBoxLayout()
        sign_box.addStretch(1)
        sign_box.addWidget(self.pct_sign)
        sign_box.addSpacing(round(7 * s))
        ph.addLayout(sign_box)
        pv.addLayout(ph)
        row.addLayout(pv)
        row.addSpacing(round(10 * s))
        self.area = MascotArea(self.m, s, self.m.click)
        row.addWidget(self.area, 1, Qt.AlignmentFlag.AlignBottom)
        v.addWidget(self.sky_row)
        v.addSpacing(round(1 * s))

        self.bar_session = Bar(6, 3, COL['ok'], s)
        v.addWidget(self.bar_session)
        v.addSpacing(round(7 * s))
        self.line_reset = label('loading...', 11, COL['text'], s)
        v.addWidget(self.line_reset)
        v.addSpacing(round(9 * s))

        def limit_row(title, color, top=0):
            g = QHBoxLayout()
            lb = label(title, 9, COL['label'], s, semi)
            val = label('', 10, COL['muted'], s)
            g.addWidget(lb)
            g.addStretch(1)
            g.addWidget(val)
            bar = Bar(4, 2, color, s)
            box = QWidget()
            bl = QVBoxLayout(box)
            bl.setContentsMargins(0, top, 0, 0)
            bl.setSpacing(round(4 * s))
            bl.addLayout(g)
            bl.addWidget(bar)
            return box, val, bar

        self.week_box, self.line_week, self.bar_week = limit_row('WEEK', COL['week'])
        v.addWidget(self.week_box)
        self.fable_box, self.line_fable, self.bar_fable = limit_row('FABLE · WEEK', COL['fable'], round(7 * s))
        v.addWidget(self.fable_box)

        # sessions
        self.sess_box = QWidget()
        sl = QHBoxLayout(self.sess_box)
        sl.setContentsMargins(0, round(10 * s), 0, 0)
        sl.addWidget(label('SESSIONS', 9, COL['label'], s, semi))
        sl.addStretch(1)
        self.line_sessions = label('', 10, COL['muted'], s)
        sl.addWidget(self.line_sessions)
        v.addWidget(self.sess_box)

        # status
        self.status_box = QWidget()
        self.status_box.setCursor(Qt.CursorShape.PointingHandCursor)
        self.status_box.setToolTip('Open status.claude.com')
        self.status_box.mousePressEvent = lambda e: QDesktopServices.openUrl(QUrl(STATUS_URL))
        stl = QHBoxLayout(self.status_box)
        stl.setContentsMargins(0, round(10 * s), 0, 0)
        stl.setSpacing(round(6 * s))
        self.status_dot = label('●', 9, COL['dead'], s)
        stl.addWidget(self.status_dot, 0, Qt.AlignmentFlag.AlignTop)
        stv = QVBoxLayout()
        stv.setSpacing(round(2 * s))
        self.line_status = label('status: loading...', 10.5, COL['muted'], s, wrap=True)
        self.line_status2 = label('', 10, COL['muted'], s, wrap=True)
        stv.addWidget(self.line_status)
        stv.addWidget(self.line_status2)
        stl.addLayout(stv, 1)
        v.addWidget(self.status_box)

        # details
        self.details = QWidget()
        dl = QVBoxLayout(self.details)
        dl.setContentsMargins(0, round(11 * s), 0, 0)
        dl.setSpacing(0)

        def rule():
            r = QFrame()
            r.setFixedHeight(max(1, round(1 * s)))
            r.setStyleSheet(f'background: {COL["rule"]};')
            return r

        dl.addWidget(rule())
        dl.addSpacing(round(8 * s))
        dl.addWidget(label('MAIN NUMBER', 9, COL['label'], s, semi))
        dl.addSpacing(round(5 * s))
        chips = QHBoxLayout()
        chips.setSpacing(round(5 * s))
        self.chips = {}
        for key in SP.SOURCES:
            c = Chip(SP.SHORT[key], s, lambda k=key: self.set_source(k))
            self.chips[key] = c
            chips.addWidget(c)
        chips.addStretch(1)
        dl.addLayout(chips)
        dl.addSpacing(round(11 * s))

        self.stats_box = QWidget()
        stb = QVBoxLayout(self.stats_box)
        stb.setContentsMargins(0, 0, 0, 0)
        stb.setSpacing(0)
        stb.addWidget(rule())
        stb.addSpacing(round(8 * s))
        self.stat_lines = {}
        for key, title in (('day', 'LAST 24 HOURS · THIS COMPUTER'), ('week7', 'LAST 7 DAYS')):
            stb.addWidget(label(title, 9, COL['label'], s, semi))
            stb.addSpacing(round(3 * s))
            a = label('', 10.5, COL['text'], s, wrap=True)
            b = label('', 10, COL['muted'], s, wrap=True)
            stb.addWidget(a)
            stb.addSpacing(round(2 * s))
            stb.addWidget(b)
            stb.addSpacing(round(10 * s))
            self.stat_lines[key] = (a, b)
        dl.addWidget(self.stats_box)
        dl.addWidget(rule())
        dl.addSpacing(round(7 * s))
        self.line_version = label('', 10, COL['muted'], s, wrap=True)
        dl.addWidget(self.line_version)
        v.addWidget(self.details)

        # footer
        foot = QHBoxLayout()
        foot.setContentsMargins(0, round(7 * s), 0, 0)
        self.line_account = label('', 9, COL['faint'], s)
        self.line_stamp = label('', 9, COL['faint'], s)
        foot.addWidget(self.line_account, 1)
        foot.addWidget(self.line_stamp)
        self.line_account.setVisible(bool(cfg['showAccount']))
        self.line_stamp.setVisible(bool(cfg['showStamp']))
        v.addLayout(foot)
        self.clip = Clip(self.body)
        card_v.addWidget(self.clip)
        v = card_v

        self.close_timer = QTimer(self)
        self.close_timer.setSingleShot(True)
        self.close_timer.timeout.connect(self.maybe_close)
        self.slide = QVariantAnimation(self)
        self.slide.setDuration(240)
        self.slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.slide.valueChanged.connect(self.on_slide)
        self.slide.finished.connect(self.on_slide_done)
        self.open = True
        if cfg['hoverOpen']:
            self.open = False
            self.clip.set_frac(0)

        self.set_details(bool(cfg['expanded']), save=False)
        self.area.setVisible(bool(cfg['showMascot']))
        self.hearts.setVisible(bool(cfg['showMascot']))
        self.apply_theme()

        # probes
        self.p_usage = Probe(self.claude, ['-p', '/usage', '--output-format', 'text',
                                           '--no-session-persistence'], 45, self.on_usage)
        self.p_auth = Probe(self.claude, ['auth', 'status'], 30, self.on_auth)
        self.p_ver = Probe(self.claude, ['--version'], 30, self.on_local_ver)
        self.h_status = HttpProbe(f'{STATUS_URL}/api/v2/summary.json', self.on_status)
        self.h_latest = HttpProbe(LATEST_URL, self.on_latest)

        self.tray = None
        self.build_tray()

        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self.update_data)
        self.tick_timer.start(2000)
        self.mascot_timer = QTimer(self)
        self.mascot_timer.timeout.connect(self.step_mascot)
        self.mascot_timer.start(M.STEP_MS)

        self.restore_position()
        self.update_data()

    # -- window chrome ----------------------------------------------------

    def header_button(self, text, size, tip, fn):
        b = label(text, size, COL['muted'], self.s)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolTip(tip)
        b.mousePressEvent = lambda e: fn() if e.button() == Qt.MouseButton.LeftButton else None
        return b

    def apply_flags(self):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.cfg['topmost']:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        vis = self.isVisible()
        self.setWindowFlags(flags)
        if vis:
            self.show()

    def start_drag(self, e):
        h = self.windowHandle()
        if h and h.startSystemMove():
            return
        self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.open_card()
            self.start_drag(e)

    # -- slide open on hover ------------------------------------------------

    def enterEvent(self, e):
        self.close_timer.stop()
        if self.cfg['hoverOpen']:
            self.open_card()
        super().enterEvent(e)

    def leaveEvent(self, e):
        if self.cfg['hoverOpen'] and self.open:
            self.close_timer.start(max(0, int(float(self.cfg['closeDelaySeconds']) * 1000)))
        super().leaveEvent(e)

    def maybe_close(self):
        # Not while a menu is open or the mouse is back on the card.
        if QApplication.activePopupWidget() or self.underMouse():
            if not self.underMouse():
                self.close_timer.start(500)
            return
        self.close_card()

    def open_card(self):
        if self.open:
            return
        self.open = True
        self.mini_pct.hide()
        self.slide.stop()
        self.slide.setStartValue(self.clip.frac)
        self.slide.setEndValue(1.0)
        self.slide.start()

    def close_card(self):
        if not self.open or not self.cfg['hoverOpen']:
            return
        self.open = False
        self.slide.stop()
        self.slide.setStartValue(self.clip.frac)
        self.slide.setEndValue(0.0)
        self.slide.start()

    def on_slide(self, f):
        self.clip.set_frac(float(f))
        self.adjustSize()

    def on_slide_done(self):
        if not self.open:
            self.mini_pct.show()
        self.fit_wrapped()

    def set_hover_open(self, on):
        self.cfg['hoverOpen'] = on
        save_config({'hoverOpen': on})
        if on and not self.underMouse():
            self.close_card()
        elif not on:
            self.close_timer.stop()
            self.open_card()

    def set_close_delay(self, secs):
        self.cfg['closeDelaySeconds'] = secs
        save_config({'closeDelaySeconds': secs})

    def mouseMoveEvent(self, e):
        d = getattr(self, '_drag', None)
        if d is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - d)

    def mouseReleaseEvent(self, e):
        self._drag = None
        self.remember_position()

    def moveEvent(self, e):
        super().moveEvent(e)
        QTimer.singleShot(500, self.remember_position)

    def remember_position(self):
        # Wayland doesn't tell clients their position (pos() stays 0,0); only save real ones.
        if QApplication.platformName() == 'wayland':
            return
        p = self.pos()
        if (self.cfg['left'], self.cfg['top']) != (p.x(), p.y()):
            self.cfg['left'], self.cfg['top'] = p.x(), p.y()
            save_config({'left': p.x(), 'top': p.y()})

    def restore_position(self):
        if self.cfg['left'] is not None and self.cfg['top'] is not None:
            self.move(int(self.cfg['left']), int(self.cfg['top']))

    def contextMenuEvent(self, e):
        self.build_menu().exec(e.globalPos())

    def build_menu(self, for_tray=False):
        menu = QMenu(self)
        if for_tray:
            a = menu.addAction('Hide window' if self.isVisible() else 'Show window')
            a.triggered.connect(self.toggle_visible)
        a = menu.addAction('Details')
        a.setCheckable(True)
        a.setChecked(self.details.isVisible())
        a.triggered.connect(self.toggle_details)
        a = menu.addAction('Open on hover')
        a.setCheckable(True)
        a.setChecked(bool(self.cfg['hoverOpen']))
        a.triggered.connect(lambda on: self.set_hover_open(on))
        delay = menu.addMenu('Close after mouse leaves')
        delay.setEnabled(bool(self.cfg['hoverOpen']))
        for secs in (0.5, 1, 2, 3, 5, 10, 30):
            a = delay.addAction(f'{secs:g} second' + ('' if secs == 1 else 's'))
            a.setCheckable(True)
            a.setChecked(float(self.cfg['closeDelaySeconds']) == secs)
            a.triggered.connect(lambda _=False, x=secs: self.set_close_delay(x))
        a = menu.addAction('Always on top')
        a.setCheckable(True)
        a.setChecked(bool(self.cfg['topmost']))
        a.triggered.connect(self.toggle_topmost)
        menu.addAction('Refresh now').triggered.connect(self.refresh_now)
        menu.addSeparator()
        src = menu.addMenu('Main number')
        for key in SP.SOURCES:
            a = src.addAction(SP.TITLES[key] + ('' if key == 'all' else ' (estimate)'))
            a.setCheckable(True)
            a.setChecked(self.cfg['mainSource'] == key)
            a.triggered.connect(lambda _=False, k=key: self.set_source(k))
        a = menu.addAction('Sky && weather')
        a.setCheckable(True)
        a.setChecked(bool(self.cfg['showSky']))
        a.triggered.connect(self.toggle_sky)
        th = menu.addMenu('Theme')
        for tid, name in [('auto', f'Follow the season (now {TH.resolve("auto").name})')] + \
                [(t.id, t.name) for t in TH.ALL]:
            a = th.addAction(name)
            a.setCheckable(True)
            a.setChecked(self.cfg['theme'] == tid)
            a.triggered.connect(lambda _=False, x=tid: self.set_look('theme', x))
        sk = menu.addMenu('Outfit')
        outfits = sorted(((k, v.name) for k, v in self.skins.items() if k != 'classic'), key=lambda kv: kv[1].lower())
        for sid, name in [('auto', "The theme's own"), ('classic', 'None')] + outfits:
            a = sk.addAction(name)
            a.setCheckable(True)
            a.setChecked(self.cfg['skin'] == sid)
            a.triggered.connect(lambda _=False, x=sid: self.set_look('skin', x))
        anim = menu.addMenu('Play animation')
        for act in M.DEMO_ACTS:
            anim.addAction(act).triggered.connect(lambda _=False, a=act: self.m.start_act(a))
        menu.addAction('Open status.claude.com').triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl(STATUS_URL)))
        menu.addAction('Open config file').triggered.connect(self.open_config)
        menu.addSeparator()
        menu.addAction('Quit').triggered.connect(self.quit)
        return menu

    def open_config(self):
        if not CONFIG_PATH.exists():
            save_config(self.cfg)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(CONFIG_PATH)))

    def toggle_details(self):
        self.set_details(not self.details.isVisible())

    def set_details(self, on, save=True):
        self.details.setVisible(on)
        self.btn_toggle.setText('▴' if on else '▾')
        self.fit_wrapped()
        if save:
            self.cfg['expanded'] = on
            save_config({'expanded': on})

    def set_source(self, key):
        self.cfg['mainSource'] = key
        save_config({'mainSource': key})
        self.code.last_try = self.cowork.last_try = 0
        self.update_data()

    def toggle_sky(self):
        self.cfg['showSky'] = not self.cfg['showSky']
        save_config({'showSky': self.cfg['showSky']})
        self.weather.last_try = 0
        self.sky_row.update()
        self.update_data()

    def set_look(self, key, value):
        self.cfg[key] = value
        save_config({key: value})
        self.apply_theme()

    def apply_theme(self):
        """Theme and outfit from the config; 'auto' theme follows the calendar."""
        theme = TH.resolve(self.cfg['theme'])
        sid = theme.skin if self.cfg['skin'] == 'auto' else self.cfg['skin']
        skin = self.skins.get(sid, SKN.CLASSIC)
        if (theme.id, skin.id) == self.theme_key:
            return
        self.theme_key = (theme.id, skin.id)
        self.card.set_theme(theme)
        self.area.skin = skin
        self.m.skin_id = skin.id
        self.area.set_scene(theme.scene)
        self.sky_row.themed = theme.scene is not None
        self.sky_row.update()
        self.fit_wrapped()

    def toggle_topmost(self):
        self.cfg['topmost'] = not self.cfg['topmost']
        save_config({'topmost': self.cfg['topmost']})
        self.apply_flags()

    def toggle_visible(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def hide_to_tray(self):
        if self.tray and self.tray.isVisible():
            self.hide()
        else:
            self.showMinimized()

    def refresh_now(self):
        self.p_usage.last_try = 0
        self.p_auth.last_try = 0
        self.h_status.last_try = 0
        self.update_data()

    def quit(self):
        self.quitting = True
        for p in (self.p_usage, self.p_auth, self.p_ver):
            p.stop()
        QApplication.quit()

    def closeEvent(self, e):
        if self.quitting:
            e.accept()
        else:
            e.ignore()
            self.hide_to_tray()

    # -- tray ------------------------------------------------------------

    def build_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(tray_icon('--', COL['dead']))
        self.tray.setToolTip('Clawd Usage: loading...')
        self.tray.activated.connect(self.on_tray)
        self.tray_menu = QMenu()
        self.tray_menu.aboutToShow.connect(self.fill_tray_menu)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.show()

    def fill_tray_menu(self):
        self.tray_menu.clear()
        for a in self.build_menu(for_tray=True).actions():
            self.tray_menu.addAction(a)

    def on_tray(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_visible()

    # -- data --------------------------------------------------------------

    def on_usage(self, text):
        u = parse_usage(text) if text else None
        if u:
            self.usage = u
            self.usage_at = datetime.now()
            self.usage_failed = False
            if u.get('session') is not None:
                self.split.add(u['session'])
        else:
            self.usage_failed = True
        self.render()

    def on_auth(self, text):
        try:
            j = json.loads(text)
        except Exception:
            return
        names = {'max': 'Max', 'pro': 'Pro', 'team': 'Team', 'enterprise': 'Enterprise', 'free': 'Free'}
        plan = str(j.get('subscriptionType') or '')
        plan = names.get(plan, plan)
        if not plan and j.get('authMethod') and j.get('authMethod') != 'claude.ai':
            plan = 'API'
        self.account = {'loggedIn': bool(j.get('loggedIn')), 'plan': plan, 'email': j.get('email', '')}
        self.render()

    def on_local_ver(self, text):
        if text:
            m = re.search(r'(\d+\.\d+\.\d+)', text)
            if m:
                self.local_ver = m.group(1)
        self.render()

    def on_latest(self, text):
        if text:
            m = re.search(r'(\d+\.\d+\.\d+)', text)
            if m:
                self.latest_ver = m.group(1)
        self.render()

    def on_status(self, text):
        if not text:
            return
        try:
            j = json.loads(text)
        except Exception:
            return
        broken = []
        for c in j.get('components', []):
            if c.get('group') or c.get('status') == 'operational':
                continue
            broken.append({'name': re.sub(r'\s*\(.*\)\s*$', '', c.get('name', '')),
                           'state': c.get('status', '')})
        self.status = {'indicator': j.get('status', {}).get('indicator', ''),
                       'description': j.get('status', {}).get('description', ''),
                       'incidents': [i.get('name', '') for i in j.get('incidents', [])],
                       'broken': broken}
        self.render()

    def own_pids(self):
        return {p for p in (self.p_usage.pid(), self.p_auth.pid(), self.p_ver.pid()) if p}

    def update_data(self):
        now = time.time()
        cfg = self.cfg
        self.apply_theme()
        for p in (self.p_usage, self.p_auth, self.p_ver):
            p.check_timeout()
        # Counted from the last attempt, not success: don't hammer a failing /usage.
        if now - self.p_usage.last_try >= float(cfg['usageIntervalSeconds']):
            self.p_usage.start()
        if cfg['showAccount'] and now - self.p_auth.last_try >= float(cfg['accountIntervalSeconds']):
            self.p_auth.start()
        if now - self.p_ver.last_try >= float(cfg['versionIntervalSeconds']):
            self.p_ver.start()
            self.h_latest.start()
        if cfg['showStatus'] and now - self.h_status.last_try >= float(cfg['statusIntervalSeconds']):
            self.h_status.start()
        self.h_status.collect()
        self.h_latest.collect()
        if cfg['showSky'] and cfg['showMascot'] and not self.sky_row.themed and self.weather.due(cfg):
            self.weather.start(cfg)
        if cfg['mainSource'] != 'all':
            for c in (self.code, self.cowork):
                if c.due(float(cfg['codeIntervalSeconds'])):
                    c.start()

        self.sessions = get_sessions(self.own_pids()) if cfg['showSessions'] else []
        self.m.set_state(self.sessions, self.usage, float(cfg['critPercent']))
        self.render()

    def level(self, pct):
        if pct >= float(self.cfg['critPercent']):
            return 'crit'
        if pct >= float(self.cfg['warnPercent']):
            return 'warn'
        return 'ok'

    def render(self):
        u = self.usage
        cfg = self.cfg
        tray_tip = []
        if not u or u.get('session') is None:
            self.pct.setText('--')
            self.set_color(self.pct, COL['dead'])
            self.bar_session.set(0)
            if self.claude is None:
                self.line_reset.setText('claude not found on PATH')
            elif self.usage_failed:
                self.line_reset.setText('no data: claude -p /usage failed')
            else:
                self.line_reset.setText('loading...')
            if self.tray:
                self.tray.setIcon(tray_icon('--', COL['dead']))
            tray_tip.append('Clawd Usage: no data yet')
        else:
            pct = int(u['session'])
            lv = self.level(pct)
            src = cfg['mainSource']
            span = format_span(u['sessionReset']) if u['sessionReset'] else None
            if span:
                when = f'resets in {span}'
            elif u['sessionReset']:
                when = 'window closed'
            else:
                when = 'window not started'
            part = self.estimate(u) if src != 'all' else None
            if part is None:
                self.pct.setText(str(pct))
                self.set_color(self.pct, COL[lv])
                self.bar_session.set(pct / 100.0, COL[lv])
                self.line_reset.setText(when if src == 'all' else f'{SP.TITLES[src]}: reading logs...  ·  {when}')
                self.line_reset.setToolTip('')
            else:
                mine = part[src]
                shown = round(mine)
                self.pct.setText(('<1' if 0 < mine < 0.5 else str(shown)) if pct else '0')
                self.set_color(self.pct, COL[lv])
                self.bar_session.set(mine / 100.0, COL[lv], pct / 100.0)
                self.line_reset.setText(f'≈ {SP.TITLES[src]}  ·  of {pct}%  ·  {when}')
                self.line_reset.setToolTip(
                    f'Estimated split of the {pct}% used this 5-hour window:\n'
                    f'  Claude Code  ≈ {part["code"]:.1f}%\n'
                    f'  Cowork       ≈ {part["cowork"]:.1f}%\n'
                    f'  Chat & other ≈ {part["chat"]:.1f}%\n\n'
                    'Anthropic only reports the total. Each time it went up, the rise is given to\n'
                    'whatever was active on this PC then (Claude Code / Cowork logs); if nothing\n'
                    'was, it counts as chat. Chat used at the same time as Claude Code is counted\n'
                    'as Claude Code. The faint bar is the real total; the colour bar is this part.\n'
                    'Hearts and the tray icon always use the real total.')
            if self.tray:
                self.tray.setIcon(tray_icon(str(pct), COL[lv]))
            tray_tip.append(f'Session {pct}%' + (f' · resets in {span}' if span else ''))

        self.mini_pct.setText(self.pct.text() + '%')
        if self.mini_pct.styleSheet() != self.pct.styleSheet():
            self.mini_pct.setStyleSheet(self.pct.styleSheet())
        self.mini_pct.setVisible(not self.open)

        for key, box, line, bar in (('week', self.week_box, self.line_week, self.bar_week),
                                    ('fable', self.fable_box, self.line_fable, self.bar_fable)):
            val = u.get(key) if u else None
            if key == 'fable' and not cfg['showFable']:
                val = None
            if val is None:
                # The Fable line can be missing: hide the row instead of showing 0.
                box.setVisible(key == 'week')
                line.setText('')
                bar.set(0)
                continue
            box.setVisible(True)
            span = format_span(u[key + 'Reset']) if u[key + 'Reset'] else None
            line.setText(f'{val}%' + (f'  ·  {span}' if span else ''))
            bar.set(val / 100.0)
            tray_tip.append(f'{"Week" if key == "week" else "Fable week"} {val}%' + (f' · {span}' if span else ''))

        for key, chip in self.chips.items():
            chip.set_on(key == cfg['mainSource'], M.BODY if key != 'all' else None)
            chip.setToolTip(SP.TITLES[key] + (' - the real combined percent' if key == 'all' else
                                              ' - estimated share of the combined percent'))
        if cfg['showSky']:
            self.sky_row.setToolTip(self.weather.tooltip(cfg))
        else:
            self.sky_row.setToolTip('')

        # sessions
        self.sess_box.setVisible(bool(cfg['showSessions']))
        ss = self.sessions
        if not ss:
            self.line_sessions.setText('none running')
            self.sess_box.setToolTip('')
        else:
            parts = [f'{len(ss)} session' + ('s' if len(ss) != 1 else '')]
            busy = sum(1 for x in ss if x['busy'])
            wait = sum(1 for x in ss if x['waiting'])
            if busy:
                parts.append(f'{busy} working')
            if wait:
                parts.append(f'{wait} waiting')
            self.line_sessions.setText('  ·  '.join(parts))
            tip = []
            for x in ss:
                mark = '▶' if x['busy'] else ('?' if x['waiting'] else '○')
                extra = f' — {x["waitingFor"]}' if x['waiting'] and x['waitingFor'] else ''
                tip.append(f'{mark}  {x["name"]}{extra}')
            self.sess_box.setToolTip('\n'.join(tip))
            if wait:
                tray_tip.append(f'{wait} session(s) waiting for you')

        # status
        self.status_box.setVisible(bool(cfg['showStatus']))
        st = self.status
        if st:
            ind = st['indicator']
            color = {'none': COL['ok'], 'minor': COL['warn'], 'major': COL['crit'],
                     'critical': COL['crit'], 'maintenance': COL['week']}.get(ind, COL['dead'])
            self.set_color(self.status_dot, color)
            self.line_status.setText(st['description'] or ind)
            extra = st['incidents'][:2] or [f'{b["name"]}: {b["state"].replace("_", " ")}' for b in st['broken'][:3]]
            self.line_status2.setText('\n'.join(extra))
            self.line_status2.setVisible(bool(extra))
        else:
            self.line_status2.setVisible(False)

        # details
        self.stats_box.setVisible(bool(cfg['showStats']))
        for key in ('day', 'week7'):
            a, b = self.stat_lines[key]
            per = u.get(key) if u else None
            if per:
                a.setText(f'{per["requests"]} requests  ·  {per["sessions"]} sessions')
                b.setText('  ·  '.join(format_stat(x) for x in per['lines']))
            else:
                a.setText('—')
                b.setText('')
        if self.local_ver:
            if self.latest_ver and self.latest_ver != self.local_ver:
                vt = f'Claude Code v{self.local_ver}  ·  v{self.latest_ver} available'
            elif self.latest_ver:
                vt = f'Claude Code v{self.local_ver}  ·  latest'
            else:
                vt = f'Claude Code v{self.local_ver}'
        else:
            vt = ''
        self.line_version.setText(vt + f'\nClawd Usage for Linux v{APP_VERSION}')

        # footer
        acc = self.account
        if cfg['showAccount'] and acc:
            self.line_account.setText(' · '.join(x for x in (acc['plan'], acc['email']) if x)
                                      if acc['loggedIn'] else 'not logged in')
        else:
            self.line_account.setText('')
        if self.usage_at:
            stale = (datetime.now() - self.usage_at).total_seconds() > 3 * float(cfg['usageIntervalSeconds']) + 30
            self.line_stamp.setText(self.usage_at.strftime('%H:%M:%S') + (' (stale)' if stale else ''))
            self.set_color(self.line_stamp, COL['warn'] if stale else COL['faint'])

        self.hearts.setToolTip(self.m.hearts_tooltip())
        if self.tray:
            self.tray.setToolTip('\n'.join(tray_tip))
        self.fit_wrapped()

    def fit_wrapped(self):
        # Tell the card about the body's new height now, not on the next event loop pass
        # (otherwise closing Details leaves the window tall for a moment).
        self.clip.place()
        self.clip.updateGeometry()
        self.card.layout().activate()
        for lb in WRAPPED:
            w = lb.width() if lb.width() > 10 else self.card.width() - round(24 * self.s)
            h = lb.heightForWidth(w)
            if h > 0 and lb.height() != h:
                lb.setFixedHeight(h)
        self.adjustSize()

    def estimate(self, u):
        """Split of this 5-hour window's percent, or None until the logs are read."""
        if not (self.code.ready and self.cowork.ready):
            return None
        now = datetime.now()
        if u.get('sessionReset') and u['sessionReset'] > now:
            start = u['sessionReset'] - timedelta(hours=5)
        else:
            start = now - timedelta(hours=5)
        return self.split.estimate(start.timestamp(), now.timestamp(), u['session'],
                                   self.code, self.cowork)

    @staticmethod
    def set_color(lb, color):
        ss = f'color: {color}; background: transparent;'
        if lb.styleSheet() != ss:
            lb.setStyleSheet(ss)

    def step_mascot(self):
        if not self.isVisible() or not self.cfg['showMascot']:
            return
        hovered = self.underMouse()
        r = self.m.step(self.area.area_w(), self.area.mouse_x(), hovered)
        if self.mascot_timer.interval() != r['interval']:
            self.mascot_timer.setInterval(r['interval'])
        if self.area.scene:
            w_px = max(1, math.ceil(self.area.area_w() / M.PX))
            t = int(time.monotonic() / SC.FRAME_S) % SC.LOOP
            self.area.scene_img = self.scene_cache.frame(self.area.scene, w_px, datetime.now().hour, t)
            self.area.update()
        elif self.cfg['showSky']:
            self.sky.step(self.sky_row.width() / self.s, self.sky_row.height() / self.s)
            self.sky_row.update()
        else:
            self.area.update()
        self.hearts.update()


def tray_icon(text, color):
    size = 64
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(qcolor(color))
    p.drawRoundedRect(QRectF(2, 2, size - 4, size - 4), 14, 14)
    f = QFont()
    f.setBold(True)
    f.setPixelSize({1: 46, 2: 40}.get(len(text), 28))
    p.setFont(f)
    p.setPen(qcolor('#141416'))
    p.drawText(QRectF(0, 0, size, size), int(Qt.AlignmentFlag.AlignCenter), text)
    p.end()
    return QIcon(pm)


def clawd_pixmap(size):
    """Clawd standing, for the app icon."""
    f = {'feet': 'both', 'look': 0, 'eyes': 'open', 'arms': 'down', 'flip': False, 'off': 0,
         'x': 0, 'facing': '', 'poof': '', 'shadow': '', 'dig': 0, 'spray': 0}
    geo = M.geometry(f)
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    k = size / (M.MASCOT_W + 4)
    h = (M.MASCOT_H - M.SINK) * k
    p.translate(2 * k, (size - h) / 2)
    p.scale(k, k)
    p.setPen(Qt.PenStyle.NoPen)
    for part, color in (('body', M.BODY), ('eyes', M.EYE)):
        p.setBrush(qcolor(color))
        for x, y, w, hh in geo[part]:
            p.drawRect(QRectF(x, y, w + 0.05, hh + 0.05))
    p.end()
    return pm


# ---------------------------------------------------------------- main ----

def main():
    if '--write-icon' in sys.argv:
        app = QApplication(sys.argv)
        path = sys.argv[sys.argv.index('--write-icon') + 1]
        clawd_pixmap(256).save(path)
        return 0

    QApplication.setDesktopFileName(APP_ID)
    app = QApplication(sys.argv)
    app.setApplicationName('Clawd Usage')
    app.setQuitOnLastWindowClosed(False)

    # One instance per user: a second start just shows the running window.
    server_name = f'{APP_ID}-{os.getuid()}'
    sock = QLocalSocket()
    sock.connectToServer(server_name)
    if sock.waitForConnected(300):
        sock.write(b'show')
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return 0
    QLocalServer.removeServer(server_name)
    server = QLocalServer()
    server.listen(server_name)

    cfg = load_config()
    claude = find_claude()
    w = Widget(cfg, claude)
    app.setWindowIcon(QIcon(clawd_pixmap(128)))

    def on_conn():
        c = server.nextPendingConnection()
        if c:
            c.readyRead.connect(lambda: (c.readAll(), w.show(), w.raise_(), w.activateWindow()))
    server.newConnection.connect(on_conn)

    if not (cfg['startHidden'] and w.tray) or '--show' in sys.argv:
        w.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
