"""
Lunar Lander Vector Physics Simulator for Raspberry Pi Pico W.
Controls: KEY3=Main Thruster, KEY2=RCS Attitude Tilt, KEY1=Exit to Games Hub.
Zero container boxes architecture with 1px horizontal dividers.
"""

import random
import picoui as ui
from picoui import Theme, color565

HS_FILE = "lander_hiscore.txt"

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

class LunarLanderGame:
    def __init__(self):
        self.high_score = load_high_score()
        self.reset()

    def reset(self):
        self.state = "PLAYING"  # "PLAYING", "LANDED", "GAMEOVER"
        self.x = 24.0
        self.y = 26.0
        self.vx = 0.5
        self.vy = 0.0
        self.tilt = 0           # -1 (Left), 0 (Vertical), 1 (Right)
        self.fuel = 100.0
        self.score = 0
        self.thrusting = False
        self.particles = []
        self.mission = 1
        self.init_terrain()

    def init_terrain(self):
        # Generate mountainous terrain profile: 9 vertices across 128 px
        # Ensure one flat landing pad (20 px wide)
        self.pad_x1 = 54
        self.pad_x2 = 74
        self.pad_y = 104
        self.terrain = [
            (0, 95), (20, 85), (38, 98),
            (self.pad_x1, self.pad_y), (self.pad_x2, self.pad_y),
            (90, 88), (110, 96), (127, 85)
        ]

    def thrust(self):
        if self.state != "PLAYING" or self.fuel <= 0:
            return
        self.thrusting = True
        self.fuel = max(0.0, self.fuel - 1.2)
        # Apply vector thrust
        self.vy -= 0.16
        if self.tilt != 0:
            self.vx += self.tilt * 0.12
        # Exhaust particles
        if len(self.particles) < 8:
            self.particles.append([self.x + 4, self.y + 7, -self.tilt * 1.5, random.uniform(1.5, 3.0), 4, Theme.WARNING])

    def toggle_tilt(self):
        if self.state != "PLAYING":
            return
        # Cycle tilt: 0 -> 1 -> -1 -> 0
        if self.tilt == 0:
            self.tilt = 1
        elif self.tilt == 1:
            self.tilt = -1
        else:
            self.tilt = 0

    def add_particles(self, x, y, count=6, color=None):
        if color is None:
            color = Theme.WARNING
        for _ in range(count):
            if len(self.particles) >= 8:
                self.particles.pop(0)
            self.particles.append([float(x), float(y), random.uniform(-2.5, 2.5), random.uniform(-2.5, 2.5), 6, color])

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

        # Lunar Gravity
        self.vy += 0.052
        if self.vy > 3.2:
            self.vy = 3.2

        # Apply velocity
        self.x += self.vx
        self.y += self.vy
        self.thrusting = False

        # Screen boundaries
        if self.x < 4:
            self.x = 4
            self.vx = 0
        elif self.x > 120:
            self.x = 120
            self.vx = 0

        # Collision check with landing pad or ground
        if self.y + 7 >= self.pad_y:
            if self.pad_x1 - 2 <= self.x <= self.pad_x2 - 6:
                # On the landing pad
                if abs(self.vx) < 0.7 and self.vy < 1.15 and self.tilt == 0:
                    # Safe touchdown!
                    self.state = "LANDED"
                    bonus = int(self.fuel * 2)
                    self.score += 250 + bonus
                    self.add_particles(self.x + 4, self.y + 4, 8, Theme.SUCCESS)
                    if self.score > self.high_score:
                        self.high_score = self.score
                        save_high_score(self.high_score)
                else:
                    self.crash()
            else:
                self.crash()

    def crash(self):
        self.state = "GAMEOVER"
        self.add_particles(self.x + 4, self.y + 4, 8, Theme.DANGER)
        if self.score > self.high_score:
            self.high_score = self.score
            save_high_score(self.high_score)

    def next_mission(self):
        self.mission += 1
        self.x = float(random.randint(15, 45))
        self.y = 24.0
        self.vx = random.uniform(0.2, 0.6)
        self.vy = 0.0
        self.tilt = 0
        self.fuel = min(100.0, self.fuel + 40.0)
        self.pad_x1 = random.randint(30, 80)
        self.pad_x2 = self.pad_x1 + max(14, 22 - self.mission * 2)
        self.pad_y = 104
        self.state = "PLAYING"


def draw_lander(lcd, x, y, tilt, thrusting):
    ix, iy = int(round(x)), int(round(y))
    # Command Module (cabin)
    lcd.fill_rect(ix + 2, iy, 5, 4, Theme.TEXT)
    lcd.pixel(ix + 4, iy + 1, Theme.PRIMARY)
    # Descent Stage / Base
    lcd.hline(ix + 1, iy + 4, 7, Theme.WARNING)
    # Landing Legs
    if tilt == -1:
        # Tilted left
        lcd.pixel(ix, iy + 6, Theme.TEXT_MUTED)
        lcd.pixel(ix + 7, iy + 7, Theme.TEXT_MUTED)
    elif tilt == 1:
        # Tilted right
        lcd.pixel(ix, iy + 7, Theme.TEXT_MUTED)
        lcd.pixel(ix + 8, iy + 6, Theme.TEXT_MUTED)
    else:
        # Upright
        lcd.pixel(ix, iy + 6, Theme.TEXT_MUTED)
        lcd.pixel(ix + 8, iy + 6, Theme.TEXT_MUTED)
        lcd.pixel(ix - 1, iy + 7, Theme.TEXT_MUTED)
        lcd.pixel(ix + 9, iy + 7, Theme.TEXT_MUTED)

    # Rocket thruster flame
    if thrusting:
        lcd.pixel(ix + 4, iy + 6, Theme.WARNING)
        lcd.pixel(ix + 4, iy + 7, Theme.DANGER)


def render_game_screen(lcd, game):
    ui.header(lcd, "LUNAR LANDER", right_badge=f"M{game.mission}", accent=Theme.WARNING)

    # 1px border dividers
    lcd.hline(0, 19, 128, Theme.BORDER)
    lcd.hline(0, 115, 128, Theme.BORDER)

    # 1. Terrain surface
    for i in range(len(game.terrain) - 1):
        x1, y1 = game.terrain[i]
        x2, y2 = game.terrain[i + 1]
        lcd.line(x1, y1, x2, y2, color565(80, 95, 125))

    # Glowing landing pad
    lcd.hline(game.pad_x1, game.pad_y, game.pad_x2 - game.pad_x1, Theme.SUCCESS)
    lcd.pixel(game.pad_x1, game.pad_y - 2, Theme.SUCCESS)
    lcd.pixel(game.pad_x2, game.pad_y - 2, Theme.SUCCESS)

    # 2. Particles
    for p in game.particles:
        lcd.pixel(int(p[0]), int(p[1]), p[5])

    # 3. Lander Craft
    if game.state in ("PLAYING", "LANDED"):
        draw_lander(lcd, game.x, game.y, game.tilt, game.thrusting)

    # 4. Bottom HUD: Fuel Gauge & Speed
    fuel_col = Theme.SUCCESS if game.fuel > 40 else (Theme.WARNING if game.fuel > 15 else Theme.DANGER)
    ui.draw_text(lcd, f"F:{game.fuel:.0f}%", 6, 118, fuel_col, font="6x8")
    vy_col = Theme.SUCCESS if game.vy < 1.15 else Theme.DANGER
    ui.draw_right(lcd, f"VY:{game.vy:.1f}", 118, vy_col, margin=6, font="6x8")

    # 5. Overlays (Zero Boxes, 1px Horizontal Dividers)
    if game.state == "LANDED":
        lcd.fill_rect(0, 38, 128, 50, Theme.BG)
        lcd.hline(0, 38, 128, Theme.SUCCESS)
        ui.draw_centered(lcd, "TOUCHDOWN SUCCESS!", 45, Theme.SUCCESS, font="6x8")
        ui.draw_centered(lcd, f"SCORE: {game.score}", 58, Theme.TEXT, font="6x8")
        ui.draw_centered(lcd, "PRESS K2 FOR NEXT", 69, Theme.INFO, font="6x8")
        lcd.hline(0, 87, 128, Theme.SUCCESS)
    elif game.state == "GAMEOVER":
        lcd.fill_rect(0, 38, 128, 50, Theme.BG)
        lcd.hline(0, 38, 128, Theme.DANGER)
        ui.draw_centered(lcd, "LANDER CRASHED", 45, Theme.DANGER, font="6x8")
        ui.draw_centered(lcd, f"SCORE: {game.score}", 58, Theme.TEXT, font="6x8")
        ui.draw_centered(lcd, f"BEST:  {game.high_score}", 69, Theme.WARNING, font="6x8")
        lcd.hline(0, 87, 128, Theme.DANGER)
