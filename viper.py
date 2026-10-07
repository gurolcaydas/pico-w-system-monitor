"""
Neon Viper (Cyberpunk Snake) Arcade Game for Raspberry Pi Pico W.
Controls: KEY3=Turn Left (90 deg), KEY2=Turn Right (90 deg), KEY1=Exit to Games Hub.
Zero container boxes architecture with 1px horizontal dividers.
"""

import random
import picoui as ui
from picoui import Theme, color565

HS_FILE = "viper_hiscore.txt"

# Direction vectors: 0=UP, 1=RIGHT, 2=DOWN, 3=LEFT
DIRS = [(0, -1), (1, 0), (0, 1), (-1, 0)]
COLS = 20  # 20 * 6 = 120 px (x = 4..123)
ROWS = 15  # 15 * 6 = 90 px  (y = 22..111)

def load_high_score():
    try:
        with open(HS_FILE, "r") as f:
            return int(f.read().strip())
    except Exception:
        return 0

def save_high_score(score):
    try:
        with open(HS_FILE, "w") as f:
            f.write(str(int(score)))
    except Exception:
        pass

class NeonViperGame:
    def __init__(self):
        self.high_score = load_high_score()
        self.reset()

    def reset(self):
        self.state = "PLAYING"  # "PLAYING", "GAMEOVER"
        self.dir_idx = 1        # Moving RIGHT initially
        self.body = [(8, 7), (7, 7), (6, 7)]  # Max 64 segments
        self.score = 0
        self.tick_timer = 0
        self.speed_ticks = 4    # Frames per step (lower = faster)
        self.food = self.spawn_food()
        self.particles = []

    def turn_left(self):
        if self.state != "PLAYING":
            return
        self.dir_idx = (self.dir_idx - 1) % 4

    def turn_right(self):
        if self.state != "PLAYING":
            return
        self.dir_idx = (self.dir_idx + 1) % 4

    def spawn_food(self):
        for _ in range(50):
            fc = random.randint(0, COLS - 1)
            fr = random.randint(0, ROWS - 1)
            if (fc, fr) not in self.body:
                return (fc, fr)
        return (1, 1)

    def add_particles(self, x, y, count=5, color=None):
        if color is None:
            color = Theme.SUCCESS
        for _ in range(count):
            if len(self.particles) >= 8:
                self.particles.pop(0)
            self.particles.append([float(x), float(y), random.uniform(-2, 2), random.uniform(-2, 2), 5, color])

    def update(self):
        # Update particles
        alive_particles = []
        for p in self.particles:
            p[0] += p[2]
            p[1] += p[3]
            p[4] -= 1
            if p[4] > 0:
                alive_particles.append(p)
        self.particles = alive_particles

        if self.state != "PLAYING":
            return

        self.tick_timer += 1
        if self.tick_timer < self.speed_ticks:
            return
        self.tick_timer = 0

        # Calculate new head
        d = DIRS[self.dir_idx]
        hx, hy = self.body[0]
        nx, ny = hx + d[0], hy + d[1]

        # Wall collision
        if nx < 0 or nx >= COLS or ny < 0 or ny >= ROWS:
            self.die()
            return

        # Self collision
        if (nx, ny) in self.body[:-1]:
            self.die()
            return

        # Move forward
        self.body.insert(0, (nx, ny))

        # Check food consumption
        if (nx, ny) == self.food:
            self.score += 10
            fx = 4 + nx * 6 + 3
            fy = 22 + ny * 6 + 3
            self.add_particles(fx, fy, 6, Theme.SUCCESS)
            self.food = self.spawn_food()
            # Speed scaling
            if self.score % 50 == 0 and self.speed_ticks > 2:
                self.speed_ticks -= 1
            # Bounded max body size
            if len(self.body) > 60:
                self.body.pop()
        else:
            self.body.pop()

    def die(self):
        self.state = "GAMEOVER"
        hx, hy = self.body[0]
        self.add_particles(4 + hx * 6 + 3, 22 + hy * 6 + 3, 8, Theme.DANGER)
        if self.score > self.high_score:
            self.high_score = self.score
            save_high_score(self.high_score)


def render_game_screen(lcd, game):
    ui.header(lcd, "NEON VIPER", right_badge=f"LEN {len(game.body)}", accent=Theme.SUCCESS)

    # Clean arena boundary (1px lines)
    lcd.hline(3, 21, 122, Theme.BORDER)
    lcd.hline(3, 112, 122, Theme.BORDER)
    lcd.vline(3, 21, 92, Theme.BORDER)
    lcd.vline(124, 21, 92, Theme.BORDER)

    # 1. Food item (pulsing neon gem)
    fx = 4 + game.food[0] * 6
    fy = 22 + game.food[1] * 6
    lcd.fill_rect(fx + 1, fy + 1, 4, 4, Theme.WARNING)
    lcd.pixel(fx + 2, fy + 2, Theme.TEXT)

    # 2. Snake Body segments
    for idx, (bx, by) in enumerate(game.body):
        sx = 4 + bx * 6
        sy = 22 + by * 6
        if idx == 0:
            # Snake Head
            lcd.fill_rect(sx, sy, 5, 5, Theme.SUCCESS)
            lcd.pixel(sx + 2, sy + 2, Theme.TEXT)
        else:
            # Body fading gradient
            col = Theme.SUCCESS if idx < 5 else color565(30, 130, 80)
            lcd.fill_rect(sx + 1, sy + 1, 4, 4, col)

    # 3. Spark particles
    for p in game.particles:
        lcd.pixel(int(p[0]), int(p[1]), p[5])

    # 4. Bottom HUD
    ui.draw_text(lcd, f"PTS {game.score:03d}", 6, 118, Theme.SUCCESS, font="6x8")
    ui.draw_right(lcd, f"HI {game.high_score:03d}", 118, Theme.TEXT_MUTED, margin=6, font="6x8")

    # 5. Game Over Overlay (Zero Boxes, 1px Horizontal Dividers)
    if game.state == "GAMEOVER":
        lcd.fill_rect(0, 38, 128, 50, Theme.BG)
        lcd.hline(0, 38, 128, Theme.DANGER)
        ui.draw_centered(lcd, "VIPER TERMINATED", 45, Theme.DANGER, font="6x8")
        ui.draw_centered(lcd, f"SCORE: {game.score}", 58, Theme.TEXT, font="6x8")
        ui.draw_centered(lcd, f"BEST:  {game.high_score}", 69, Theme.WARNING, font="6x8")
        lcd.hline(0, 87, 128, Theme.DANGER)
