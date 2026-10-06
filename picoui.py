"""
PicoUI: Minimalist Tailwind/Bootstrap-style UI Framework for 128x128 MicroPython Displays
Hardware: Raspberry Pi Pico W + Waveshare Pico-LCD-1.44 (128x128, ST7735S)
Includes dual font engine: High-density 6x8 (21 chars/line) & Native 8x8 (15 chars/line).
Optimized for 3-button navigation (KEY3=Up, KEY2=Down, KEY1=Action).
"""

import framebuf
import time

try:
    import micropython
    _native = micropython.native
except:
    def _native(f): return f

# ==============================================================================
# 1. DESIGN TOKENS (Tailwind / Bootstrap semantic palette for 16-bit RGB565)
# ==============================================================================
def color565(r, g, b):
    """Convert 8-bit RGB to little-endian swapped RGB565 for RP2040 FrameBuffer."""
    c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return ((c & 0xFF) << 8) | ((c >> 8) & 0xFF)

class Theme:
    # Canvas & Elevation
    BG           = color565(11, 15, 25)    # Slate-950
    SURFACE      = color565(22, 27, 38)    # Slate-900 (Card background)
    SURFACE_ALT  = color565(34, 41, 56)    # Slate-800 (Active/Selected Card)
    BORDER       = color565(56, 66, 83)    # Slate-700
    BORDER_FOCUS = color565(99, 102, 241)  # Indigo-500

    # Typography Luminance
    TEXT         = color565(255, 255, 255) # Pure White (#FFFFFF)
    TEXT_MUTED   = color565(156, 163, 175) # Slate-400 (#9CA3AF)
    TEXT_DARK    = color565(100, 116, 139) # Slate-500 (#64748B)

    # Brand & Semantic Variants
    PRIMARY      = color565(99, 102, 241)  # Indigo-500
    SUCCESS      = color565(16, 185, 129)  # Emerald-500
    WARNING      = color565(251, 191, 36)  # Amber-400
    DANGER       = color565(244, 63, 94)   # Rose-500
    INFO         = color565(34, 211, 238)  # Cyan-400

    # Screen Layout Metrics
    WIDTH        = 128
    HEIGHT       = 128
    HEADER_H     = 18
    FOOTER_H     = 14
    CONTENT_H    = 96   # 128 - 18 - 14

def get_variant_color(variant):
    if variant == "primary":  return Theme.PRIMARY
    if variant == "success":  return Theme.SUCCESS
    if variant == "warning":  return Theme.WARNING
    if variant == "danger":   return Theme.DANGER
    if variant == "info":     return Theme.INFO
    return Theme.PRIMARY

# ==============================================================================
# 2. TYPOGRAPHY ENGINE (6x8 High-Density Font + 8x8 Native + 16x16 Metrics)
# ==============================================================================

# Compact 5x7 ASCII font bitmap (ASCII 32 to 126, 95 chars * 5 bytes = 475 bytes)
FONT_6X8 = (
    b'\x00\x00\x00\x00\x00\x00\x00_\x00\x00\x00\x07\x00\x07\x00\x14\x7f\x14\x7f\x14'
    b'$*\x7f*\x12#\x13\x08db6IV P\x00\x08\x07\x03\x00\x00\x1c"A\x00\x00A"\x1c\x00'
    b'*\x1c\x7f\x1c*\x08\x08>\x08\x08\x00\x80p0\x00\x08\x08\x08\x08\x08\x00\x00``\x00 '
    b'\x10\x08\x04\x02>QIE>\x00B\x7f@\x00rIIIF!AIM3\x18\x14\x12\x7f\x10\'EEE9'
    b'<JII1A!\x11\t\x076III6FII)\x1e\x00\x00\x14\x00\x00\x00@4\x00\x00\x00\x08\x14"A'
    b'\x14\x14\x14\x14\x14\x00A"\x14\x08\x02\x01Y\t\x06>A]YN|\x12\x11\x12|\x7fIII6'
    b'>AAA"\x7fAAA>\x7fIIIA\x7f\t\t\t\x01>AAQs\x7f\x08\x08\x08\x7f\x00A\x7fA\x00 '
    b'@A?\x01\x7f\x08\x14"A\x7f@@@@\x7f\x02\x1c\x02\x7f\x7f\x04\x08\x10\x7f>AAA>'
    b'\x7f\t\t\t\x06>AQ!^\x7f\t\x19)F&III2\x03\x01\x7f\x01\x03?@@@?\x1f @ \x1f'
    b'?@8@?c\x14\x08\x14c\x03\x04x\x04\x03aYIMC\x00\x7fAAA\x02\x04\x08\x10 \x00AAA\x7f'
    b'\x04\x02\x01\x02\x04@@@@@\x00\x03\x07\x08\x00 TTx@\x7f(DD88DDD(8DD(\x7f'
    b'8TTT\x18\x00\x08~\t\x02\x18\xa4\xa4\x9cx\x7f\x08\x04\x04x\x00D}@\x00 @@=\x00'
    b'\x7f\x10(D\x00\x00A\x7f@\x00|\x04x\x04x|\x08\x04\x04x8DDD8\xfc\x18$$\x18'
    b'\x18$$\x18\xfc|\x08\x04\x04\x08HTTT$\x04\x04?D$<@@ |\x1c @ \x1c<@0@<D(\x10(D'
    b'L\x90\x90\x90|DdTLD\x00\x086A\x00\x00\x00w\x00\x00\x00A6\x08\x00\x02\x01\x02\x04\x02'
)

@_native
def draw_text_6x8(lcd, text, x: int, y: int, color: int):
    """
    Renders 6x8 crisp font (5x7 glyph + 1px spacing) using RP2040 native instructions.
    Yields 21 characters across the 128px screen!
    """
    cx = x
    f = FONT_6X8
    pix = lcd.pixel
    for i in range(len(text)):
        code = ord(text[i]) - 32
        if 0 <= code <= 94:
            base = code * 5
            for col in range(5):
                b = f[base + col]
                if b != 0:
                    px = cx + col
                    for row in range(8):
                        if (b >> row) & 1:
                            pix(px, y + row, color)
        cx += 6

def draw_text(lcd, text, x, y, color=Theme.TEXT, font="6x8"):
    """
    Draw crisp text.
    - font="6x8": 6px width x 8px height (up to 21 chars/line) - Default
    - font="8x8": 8px width x 8px height (up to 15 chars/line) - MicroPython standard
    """
    if font == "6x8":
        draw_text_6x8(lcd, text, x, y, color)
    else:
        lcd.text(text, x, y, color)

def draw_centered(lcd, text, y, color=Theme.TEXT, font="6x8"):
    """Center text horizontally across the 128px display."""
    char_w = 6 if font == "6x8" else 8
    x = max(0, (Theme.WIDTH - len(text) * char_w) // 2)
    draw_text(lcd, text, x, y, color, font=font)

def draw_right(lcd, text, y, color=Theme.TEXT, margin=4, font="6x8"):
    """Right-align text with margin."""
    char_w = 6 if font == "6x8" else 8
    x = max(0, Theme.WIDTH - len(text) * char_w - margin)
    draw_text(lcd, text, x, y, color, font=font)

# Framebuffer buffer for 2x scaling
_cbuf = bytearray(8)
_cfb = framebuf.FrameBuffer(_cbuf, 8, 8, framebuf.MONO_HLSB)

def draw_big(lcd, text, x, y, color=Theme.TEXT):
    """
    Draw 2x scaled (16x16) crisp open-counter text for metrics and numbers.
    """
    cur_x = x
    for ch in text:
        if ch == ' ':
            cur_x += 12
            continue
        _cfb.fill(0)
        _cfb.text(ch, 0, 0, 1)
        for ry in range(8):
            row = _cbuf[ry]
            if not row:
                continue
            py = y + ry * 2
            for rx in range(8):
                if (row << rx) & 0x80:
                    lcd.fill_rect(cur_x + rx * 2, py, 2, 2, color)
        cur_x += 14

def draw_big_centered(lcd, text, y, color=Theme.TEXT):
    """Center 2x big text horizontally."""
    total_w = len(text) * 14 - 2
    x = max(0, (Theme.WIDTH - total_w) // 2)
    draw_big(lcd, text, x, y, color)

def draw_arrow_down(lcd, x: int, y: int, color: int):
    """Draws a crisp 5x7 downward arrow (Min icon, same size as 6x8 char)."""
    lcd.vline(x + 2, y, 5, color)
    lcd.hline(x, y + 4, 5, color)
    lcd.hline(x + 1, y + 5, 3, color)
    lcd.pixel(x + 2, y + 6, color)

def draw_arrow_up(lcd, x: int, y: int, color: int):
    """Draws a crisp 5x7 upward arrow (Max icon, same size as 6x8 char)."""
    lcd.pixel(x + 2, y, color)
    lcd.hline(x + 1, y + 1, 3, color)
    lcd.hline(x, y + 2, 5, color)
    lcd.vline(x + 2, y + 2, 5, color)

# ==============================================================================
# 3. ATOMIC UI COMPONENTS (Tailwind / Bootstrap Style)
# ==============================================================================

def header(lcd, title, right_badge=None, accent=Theme.PRIMARY):
    """
    App Header Bar (y=0..18).
    Includes title, optional status text, and bottom accent line.
    """
    lcd.fill_rect(0, 0, Theme.WIDTH, Theme.HEADER_H, Theme.SURFACE)
    lcd.hline(0, Theme.HEADER_H - 1, Theme.WIDTH, accent)
    draw_text(lcd, title, 4, 5, Theme.TEXT, font="6x8")
    if right_badge:
        draw_right(lcd, right_badge, 5, Theme.TEXT_MUTED, margin=4, font="6x8")

def footer(lcd, k3="^", k2="v", k1="SELECT"):
    """
    3-Key Hardware Action Footer (y=114..128).
    Accurately maps to physical hardware: KEY3 (Top), KEY2 (Mid), KEY1 (Low).
    """
    lcd.fill_rect(0, 114, Theme.WIDTH, Theme.FOOTER_H, Theme.SURFACE)
    lcd.hline(0, 114, Theme.WIDTH, Theme.BORDER)
    hint_str = f"K3:{k3}  K2:{k2}  K1:{k1}"
    draw_centered(lcd, hint_str, 117, Theme.INFO, font="6x8")

def card(lcd, x, y, w, h, is_active=False, border_color=None):
    """
    Container Card with elevation and border.
    Active cards feature highlighted borders and brighter surface color.
    """
    bg = Theme.SURFACE_ALT if is_active else Theme.SURFACE
    b_color = border_color if border_color else (Theme.BORDER_FOCUS if is_active else Theme.BORDER)
    lcd.fill_rect(x, y, w, h, bg)
    lcd.rect(x, y, w, h, b_color)

def badge(lcd, x, y, text, variant="info"):
    """
    Pill badge / tag (e.g., [LIVE], [WARN], [ONLINE]).
    """
    v_color = get_variant_color(variant)
    w = len(text) * 6 + 6
    h = 10
    lcd.fill_rect(x, y, w, h, Theme.SURFACE)
    lcd.rect(x, y, w, h, v_color)
    draw_text(lcd, text, x + 3, y + 1, v_color, font="6x8")

def progress_bar(lcd, x, y, w, h, percent, variant="primary"):
    """
    Minimalist linear progress indicator track (no outer box).
    """
    pct = max(0, min(100, percent))
    fill_w = int(w * (pct / 100))
    v_color = get_variant_color(variant)
    
    # Sleek background track
    lcd.fill_rect(x, y, w, h, Theme.SURFACE)
    if fill_w > 0:
        lcd.fill_rect(x, y, fill_w, h, v_color)

def latency_chart(lcd, x, y, w, h, values, min_val=None, max_val=None):
    """
    Minimalist latency histogram / sparkline bar chart.
    values: list of numbers (e.g. latency in ms)
    """
    if not values:
        draw_centered(lcd, "Collecting data...", y + (h // 2) - 4, Theme.TEXT_MUTED, font="6x8")
        return

    # Baseline axis
    base_y = y + h - 2
    lcd.hline(x, base_y, w, Theme.BORDER)

    num = len(values)
    high = max_val if (max_val and max_val > 0) else max(max(values), 1)
    
    max_bars = 16
    plot_vals = values[-max_bars:]
    count = len(plot_vals)
    slot_w = w // count if count > 0 else 6
    bar_w = max(2, slot_w - 2)
    max_bar_h = h - 6

    for i, val in enumerate(plot_vals):
        bx = x + i * slot_w + 1
        bar_h = max(2, min(max_bar_h, int(val * max_bar_h / high)))
        by = base_y - bar_h

        # Color coding: Green for fast (<70%), Cyan for mid (<90%), Warning for spikes
        if val < high * 0.7:
            b_color = Theme.SUCCESS
        elif val < high * 0.9:
            b_color = Theme.INFO
        else:
            b_color = Theme.WARNING
        
        lcd.fill_rect(bx, by, bar_w, bar_h, b_color)

def metric_widget(lcd, x, y, w, h, label, value_str, unit="", variant="primary", is_active=False):
    """
    Hero Metric Card (e.g. Temperature 24.5 C or CPU 12%).
    Displays label, big bold value, and optional unit tag.
    """
    card(lcd, x, y, w, h, is_active=is_active)
    v_color = get_variant_color(variant)
    draw_text(lcd, label, x + 4, y + 3, Theme.TEXT_MUTED, font="6x8")
    draw_big(lcd, value_str, x + 6, y + 14, v_color)
    if unit:
        unit_x = x + 6 + len(value_str) * 14 + 2
        draw_text(lcd, unit, unit_x, y + 20, Theme.TEXT, font="6x8")

def list_menu(lcd, items, selected_idx, start_y=20, max_visible=4):
    """
    Standard ListGroup Menu with scroll window and active item indicator.
    Supports up to 18 characters per item with 6x8 font!
    items: list of dicts [{'title': '...', 'sub': '...', 'badge': '...', 'color': ...}]
    """
    num_items = len(items)
    top_idx = max(0, min(selected_idx - 1, num_items - max_visible))
    card_h = 21
    gap = 2

    for row in range(max_visible):
        idx = top_idx + row
        if idx >= num_items:
            break
        item = items[idx]
        cy = start_y + row * (card_h + gap)
        is_sel = (idx == selected_idx)
        item_color = item.get("color", Theme.PRIMARY)

        # Card container
        card(lcd, 2 if is_sel else 4, cy, 124 if is_sel else 120, card_h, 
             is_active=is_sel, border_color=item_color if is_sel else None)
        
        # Cursor & Text with 6x8 font (up to 18 chars!)
        if is_sel:
            draw_text(lcd, ">", 5, cy + 2, item_color, font="6x8")
            draw_text(lcd, item["title"][:17], 13, cy + 2, Theme.TEXT, font="6x8")
            if "sub" in item:
                draw_text(lcd, item["sub"][:18], 13, cy + 11, item_color, font="6x8")
        else:
            draw_text(lcd, item["title"][:17], 10, cy + 2, Theme.TEXT_MUTED, font="6x8")
            if "sub" in item:
                draw_text(lcd, item["sub"][:18], 10, cy + 11, Theme.TEXT_DARK, font="6x8")

    # Scroll indicators
    if top_idx > 0:
        draw_text(lcd, "^", 121, start_y - 2, Theme.WARNING, font="6x8")
    if top_idx + max_visible < num_items:
        draw_text(lcd, "v", 121, start_y + max_visible * (card_h + gap) - 4, Theme.WARNING, font="6x8")

def alert_modal(lcd, title, message, variant="info", prompt=None):
    """
    Centered modal dialog / alert box with dark backdrop.
    """
    v_color = get_variant_color(variant)
    # Backdrop
    lcd.fill_rect(10, 24, 108, 80, Theme.BG)
    lcd.rect(10, 24, 108, 80, v_color)
    
    # Title & Line
    draw_centered(lcd, title, 32, v_color, font="6x8")
    lcd.hline(18, 44, 92, Theme.BORDER)
    
    # Message (up to 2 lines)
    if "\n" in message:
        lines = message.split("\n")
        draw_centered(lcd, lines[0], 52, Theme.TEXT, font="6x8")
        draw_centered(lcd, lines[1], 64, Theme.TEXT_MUTED, font="6x8")
    else:
        draw_centered(lcd, message, 56, Theme.TEXT, font="6x8")
        
    # Action prompt (optional)
    if prompt:
        draw_centered(lcd, prompt, 84, Theme.SUCCESS, font="6x8")

def dos_boot_sequence(lcd, fast=False):
    """
    Simulates an authentic retro MS-DOS / BIOS boot sequence on the 128x128 LCD.
    Includes memory counting, device detection, config loading, and blinking cursor,
    concluding with 'Device Ready!'.
    """
    lines = []
    max_lines = 13
    line_h = 9
    dos_white = 0xFFFF
    dos_gray = 0xAD55
    dos_green = 0x2506
    dos_cyan = 0x0E1F

    def redraw(cursor=True):
        lcd.fill(0x0000)  # Pure DOS Black
        visible = lines[-max_lines:]
        for idx, text in enumerate(visible):
            y = 2 + idx * line_h
            col = dos_white
            if text.startswith("C:\\>"):
                col = dos_white
            elif text.startswith("[OK]"):
                col = dos_green
            elif text.startswith("Device"):
                col = dos_white
            elif "BIOS" in text or "MS-DOS" in text:
                col = dos_cyan
            else:
                col = dos_gray
            draw_text(lcd, text, 2, y, col, font="6x8")
            
        if cursor and visible:
            last_idx = len(visible) - 1
            last_line = visible[-1]
            cx = 2 + len(last_line) * 6
            cy = 2 + last_idx * line_h
            if cx < 124:
                lcd.fill_rect(cx, cy + 6, 5, 2, dos_white)
        lcd.show()

    delay_mult = 0.5 if fast else 1.0

    def add_line(text, delay=0.15, cursor=True):
        lines.append(text)
        redraw(cursor=cursor)
        time.sleep(delay * delay_mult)

    # 1. BIOS Banner & CPU
    add_line("Phoenix BIOS (C)1998", 0.3)
    add_line("RP2040 CPU at 133MHz", 0.2)

    # 2. Memory Test counter
    for ram in (64, 128, 192, 264):
        if lines and lines[-1].startswith("RAM Test:"):
            lines.pop()
        add_line(f"RAM Test: {ram} KB OK", 0.08)

    time.sleep(0.15 * delay_mult)
    add_line("Drive A: SPI-FLASH", 0.12)
    add_line("Display: ST7735S 16B", 0.15)
    add_line("Keypad: 3 Active", 0.18)

    # 3. DOS Load & Drivers
    add_line("Starting MS-DOS 6.22", 0.3)
    add_line("HIMEM.SYS is active", 0.15)
    add_line("DEVICE=PICOUI.SYS", 0.2)
    add_line("C:\\> AUTOEXEC.BAT", 0.25)
    add_line("[OK] Video 128x128", 0.15)
    add_line("[OK] Keys 3,2,1 Map", 0.15)
    add_line("C:\\> RUN PICO.EXE", 0.35)

    # 4. Final: Device Ready! with blinking cursor
    lines.append("Device Ready!")
    for _ in range(3):
        redraw(cursor=True)
        time.sleep(0.3 * delay_mult)
        redraw(cursor=False)
        time.sleep(0.2 * delay_mult)
    redraw(cursor=True)
    time.sleep(0.8 * delay_mult)

