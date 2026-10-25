"""Themes from Pinch's art/Themes.kt (MIT, see LICENSE-pinch): a card colour, the scene
Clawd walks on, the outfit he wears when the outfit is "auto", and a wallpaper pattern.
"Classic" keeps this widget's own live-weather sky instead of a scene."""

from collections import namedtuple
from datetime import date

Theme = namedtuple('Theme', 'id name bg scene skin pattern')

ALL = [
    Theme('classic', 'Classic (live weather sky)', '#1A1A1E', None, 'classic', None),
    Theme('oled', 'OLED black', '#000000', 'oled', 'classic', None),
    Theme('midnight', 'Midnight', '#0F172A', 'midnight', 'classic', None),
    Theme('halloween', 'Halloween', '#1C1326', 'halloween', 'witch', 'halloween'),
    Theme('christmas', 'Christmas', '#0E1A2B', 'christmas', 'santa', 'christmas'),
    Theme('valentine', 'Valentine', '#24101C', 'valentine', 'bow', 'valentine'),
    Theme('spring', 'Spring', '#121A14', 'spring', 'flowershorts', 'spring'),
    Theme('summer', 'Summer', '#0B1E2B', 'summer', 'shades', 'summer'),
    Theme('space', 'Space', '#0E0820', 'space', 'astronaut', 'space'),
    Theme('ocean', 'Underwater', '#0A2236', 'ocean', 'squarepants', 'ocean'),
    Theme('cyberpunk', 'Cyberpunk', '#0C0B16', 'cyberpunk', 'netrunner', 'cyberpunk'),
]
BY_ID = {t.id: t for t in ALL}


def seasonal(today=None):
    """Spooky in October, festive in December, and so on."""
    d = today or date.today()
    md = (d.month, d.day)
    if (10, 1) <= md <= (11, 1):
        return 'halloween'
    if md >= (12, 1) or md <= (1, 6):
        return 'christmas'
    if (2, 7) <= md <= (2, 15):
        return 'valentine'
    if (3, 20) <= md <= (5, 31):
        return 'spring'
    if (6, 1) <= md <= (8, 31):
        return 'summer'
    return 'classic'


def resolve(choice, today=None):
    """'auto' follows the calendar; anything else is the theme with that id."""
    return BY_ID.get(seasonal(today) if choice == 'auto' else choice, ALL[0])
