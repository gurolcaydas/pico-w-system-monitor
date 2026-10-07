"""
Color Logo & Screensaver Engine for Raspberry Pi Pico W.
Features:
- Vibrant multi-color Raspberry Pi Pico vector logo (Emerald Leaves, Ruby Berry Drupelets, RP2040 Silicon Core).
- Classic retro-arcade bouncing screensaver with color cycling, particle sparks, and ambient star dust.
- 1-minute idle auto-activation with instant zero-action wake-up on any button press.
"""

import random
import time
import picoui as ui
from picoui import Theme, color565

# Color Palette for Logo & Screensaver
C_LEAF = color565(38, 208, 90)
C_LEAF_HI = color565(90, 245, 140)
C_LEAF_DARK = color565(18, 140, 55)

C_BERRY = color565(228, 22, 78)
C_BERRY_HI = color565(255, 75, 125)
C_BERRY_DARK = color565(155, 10, 48)

C_CHIP = color565(16, 22, 36)
C_GOLD = color565(240, 190, 60)
C_CYAN = color565(0, 225, 255)

ACCENTS = [
    color565(0, 225, 255),    # Cyber Cyan
    color565(38, 208, 90),    # Emerald Green
    color565(255, 60, 130),   # Neon Ruby
    color565(255, 195, 45),   # Golden Amber
    color565(170, 75, 255),   # Royal Violet
]

def draw_color_logo(lcd, cx, cy, accent_color=None):
    """
    Renders the vibrant Raspberry Pi Pico W color logo at (cx, cy).
    Zero external files required; renders instantly via vector primitives.
    """
    if accent_color is None:
        accent_color = C_CYAN

    # 1. Top Leaves Cluster
    # Center Leaf
    lcd.fill_rect(cx - 2, cy - 14, 5, 4, C_LEAF)
    lcd.pixel(cx, cy - 15, C_LEAF_HI)
    lcd.pixel(cx, cy - 16, C_LEAF_HI)
    lcd.pixel(cx - 1, cy - 14, C_LEAF_HI)

    # Left Leaf
    lcd.fill_rect(cx - 8, cy - 13, 5, 3, C_LEAF)
    lcd.pixel(cx - 9, cy - 14, C_LEAF_HI)
    lcd.pixel(cx - 5, cy - 11, C_LEAF_DARK)

    # Right Leaf
    lcd.fill_rect(cx + 4, cy - 13, 5, 3, C_LEAF)
    lcd.pixel(cx + 9, cy - 14, C_LEAF_HI)
    lcd.pixel(cx + 5, cy - 11, C_LEAF_DARK)

    # Sepal Collar
    lcd.hline(cx - 5, cy - 10, 11, C_LEAF_DARK)
    lcd.hline(cx - 3, cy - 9, 7, C_LEAF_DARK)

    # 2. Raspberry Drupelets (Cluster of 14 round berry lobes)
    lobes = [
        # Row 1 (Upper)
        (cx - 8, cy - 8), (cx - 3, cy - 8), (cx + 3, cy - 8), (cx + 8, cy - 8),
        # Row 2 (Mid-Upper)
        (cx - 11, cy - 3), (cx - 6, cy - 3), (cx + 6, cy - 3), (cx + 11, cy - 3),
        # Row 3 (Mid-Lower)
        (cx - 9, cy + 3), (cx - 4, cy + 3), (cx + 4, cy + 3), (cx + 9, cy + 3),
        # Row 4 (Bottom Tip)
        (cx - 5, cy + 8), (cx, cy + 9), (cx + 5, cy + 8)
    ]

    for lx, ly in lobes:
        # 5x5 rounded circle
        lcd.fill_rect(lx - 1, ly - 2, 3, 5, C_BERRY)
        lcd.fill_rect(lx - 2, ly - 1, 5, 3, C_BERRY)
        # Specular highlight dot (top-left)
        lcd.pixel(lx - 1, ly - 1, C_BERRY_HI)
        # Shadow dot (bottom-right)
        lcd.pixel(lx + 1, ly + 1, C_BERRY_DARK)

    # 3. RP2040 Microcontroller Silicon Core (Center of Raspberry)
    lcd.fill_rect(cx - 3, cy - 3, 7, 7, C_CHIP)
    lcd.rect(cx - 3, cy - 3, 7, 7, accent_color)

    # Golden Circuit Pins
    lcd.pixel(cx - 4, cy - 1, C_GOLD)
    lcd.pixel(cx - 4, cy + 1, C_GOLD)
    lcd.pixel(cx + 4, cy - 1, C_GOLD)
    lcd.pixel(cx + 4, cy + 1, C_GOLD)
    lcd.pixel(cx - 1, cy - 4, C_GOLD)
    lcd.pixel(cx + 1, cy - 4, C_GOLD)
    lcd.pixel(cx - 1, cy + 4, C_GOLD)
    lcd.pixel(cx + 1, cy + 4, C_GOLD)

    # Glowing Core / Wi-Fi Symbol
    lcd.pixel(cx, cy, accent_color)
    lcd.pixel(cx - 1, cy - 1, C_CYAN)
    lcd.pixel(cx + 1, cy - 1, C_CYAN)

    # 4. Typography Badge: "PICO W"
    ty = cy + 14
    ui.draw_text(lcd, "PICO", cx - 17, ty, Theme.TEXT, font="6x8")
    ui.draw_text(lcd, "W", cx + 9, ty, accent_color, font="6x8")


class Screensaver:
    def __init__(self):
        self.x = 64.0
        self.y = 64.0
        self.vx = 0.82
        self.vy = 0.62
        self.accent_idx = 0
        self.particles = []
        self.last_up_s = -1
        self.cached_up_str = "UP 0h00m"
        self.last_temp_val = -999
        self.cached_t_str = ""
        self.init_stars()

    def init_stars(self):
        # 12 ambient drifting star dust points: [x, y, speed, color]
        self.stars = []
        for _ in range(8):
            self.stars.append([random.randint(0, 127), random.randint(0, 127), 0.5, color565(45, 55, 75)])
        for _ in range(4):
            self.stars.append([random.randint(0, 127), random.randint(0, 127), 1.0, color565(90, 110, 150)])

    def add_sparks(self, x, y, count=4):
        col = ACCENTS[self.accent_idx]
        for _ in range(count):
            if len(self.particles) >= 8:
                self.particles.pop(0)
            self.particles.append([
                float(x), float(y),
                random.uniform(-1.8, 1.8),
                random.uniform(-1.8, 1.8),
                6, col
            ])

    def on_bounce(self, bx, by):
        self.accent_idx = (self.accent_idx + 1) % len(ACCENTS)
        self.add_sparks(bx, by, 4)

    def update(self):
        # 1. Update stars
        for s in self.stars:
            s[0] -= s[2]
            if s[0] < 0:
                s[0] = 127
                s[1] = random.randint(0, 127)

        # 2. Update particles in place
        i = len(self.particles) - 1
        while i >= 0:
            p = self.particles[i]
            p[0] += p[2]
            p[1] += p[3]
            p[4] -= 1
            if p[4] <= 0 or not (0 <= p[0] <= 127 and 0 <= p[1] <= 127):
                self.particles.pop(i)
            i -= 1

        # 3. Logo Bouncing Physics
        self.x += self.vx
        self.y += self.vy

        # Screen boundaries (Logo half-width ~ 19, half-height ~ 20)
        if self.x <= 19:
            self.x = 19
            self.vx = abs(self.vx)
            self.on_bounce(self.x - 14, self.y)
        elif self.x >= 108:
            self.x = 108
            self.vx = -abs(self.vx)
            self.on_bounce(self.x + 14, self.y)

        if self.y <= 19:
            self.y = 19
            self.vy = abs(self.vy)
            self.on_bounce(self.x, self.y - 14)
        elif self.y >= 107:
            self.y = 107
            self.vy = -abs(self.vy)
            self.on_bounce(self.x, self.y + 16)

    def render(self, lcd, uptime_s=0, temp_c=None):
        lcd.fill(Theme.BG)

        # 1. Background Star Dust
        for s in self.stars:
            lcd.pixel(int(s[0]), int(s[1]), s[3])

        # 2. Sparkle Particles
        for p in self.particles:
            lcd.pixel(int(p[0]), int(p[1]), p[5])

        # 3. Floating Color Logo
        accent = ACCENTS[self.accent_idx]
        draw_color_logo(lcd, int(round(self.x)), int(round(self.y)), accent_color=accent)

        # 4. Subtle Ambient System Telemetry (cached strings to prevent GC pauses)
        if uptime_s != self.last_up_s:
            self.last_up_s = uptime_s
            m = (uptime_s // 60) % 60
            h = uptime_s // 3600
            self.cached_up_str = f"UP {h}h{m:02d}m"
        ui.draw_text(lcd, self.cached_up_str, 4, 119, color565(50, 60, 80), font="6x8")

        if temp_c is not None:
            t_int = int(temp_c * 10)
            if t_int != self.last_temp_val:
                self.last_temp_val = t_int
                self.cached_t_str = f"{temp_c:.1f}C"
            ui.draw_right(lcd, self.cached_t_str, 119, color565(50, 60, 80), margin=4, font="6x8")
