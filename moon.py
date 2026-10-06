"""
Moon Phase & Lunar Astronomy Engine for Raspberry Pi Pico W.
Calculates exact synodic phase, illumination, days until next Full Moon,
and target calendar dates using Julian Day algorithms.
"""

import math
import time

def get_current_date():
    """
    Returns (year, month, day, hour) from local RTC.
    If un-synchronized (< 2024), falls back to 2026-10-06.
    """
    try:
        t = time.localtime()
        if t[0] >= 2024:
            return t[0], t[1], t[2], t[3]
    except Exception:
        pass
    return 2026, 10, 6, 20

def get_moon_info(year=None, month=None, day=None, hour=None):
    """
    Calculates lunar phase parameters based on astronomical algorithms.
    """
    if year is None:
        year, month, day, hour = get_current_date()

    # Julian Date Calculation
    y, m = year, month
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + (a // 4)
    day_fraction = day + (hour / 24.0)
    jd = int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + day_fraction + b - 1524.5

    # Synodic Lunar Month = 29.53058867 days
    # Reference New Moon: 2000-01-06 18:14 UTC -> JD 2451549.759722
    ref_jd = 2451549.759722
    synodic = 29.53058867
    days_since = jd - ref_jd
    phase = (days_since % synodic) / synodic
    age = phase * synodic

    # Days to Next Full Moon (phase = 0.50)
    if phase <= 0.50:
        days_to_full = (0.50 - phase) * synodic
    else:
        days_to_full = (1.50 - phase) * synodic

    # Illumination percentage (0..100%)
    illum = (1.0 - math.cos(phase * 2.0 * math.pi)) / 2.0 * 100.0

    # Concise Technical Phase Name
    if phase < 0.03 or phase >= 0.97:
        name = "NEW MOON"
    elif phase < 0.22:
        name = "WAX CRESCENT"
    elif phase < 0.28:
        name = "1ST QUARTER"
    elif phase < 0.47:
        name = "WAX GIBBOUS"
    elif phase < 0.53:
        name = "FULL MOON"
    elif phase < 0.72:
        name = "WAN GIBBOUS"
    elif phase < 0.78:
        name = "LAST QUARTER"
    else:
        name = "WAN CRESCENT"

    # Next Full Moon calendar date string (e.g. '25 OCT')
    months = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    try:
        cur_epoch = time.time()
        if cur_epoch > 10000000:
            full_epoch = cur_epoch + int(days_to_full * 86400)
            ft = time.localtime(full_epoch)
            full_date = f"{ft[2]} {months[ft[1]]}"
        else:
            full_date = f"{int(round(days_to_full))}d"
    except Exception:
        full_date = f"{int(round(days_to_full))}d"

    return {
        "phase": phase,
        "age": age,
        "name": name,
        "illum": illum,
        "days_to_full": days_to_full,
        "full_date": full_date,
    }
