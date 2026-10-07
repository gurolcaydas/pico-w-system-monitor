"""
Pico Pong (Player vs Pico CPU AI) for Raspberry Pi Pico W.
Controls: KEY3=Paddle Up, KEY2=Paddle Down, KEY1=Exit to Games Hub.
Zero container boxes architecture with 1px horizontal dividers.
"""

import random
import picoui as ui
from picoui import Theme, color565

HS_FILE = "pong_hiscore.txt"

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

class PicoPongGame:
    def __init__(self):
        self.wins = load_high_score()
        self.reset()

    def reset(self):
        self.state = "PLAYING"  # "PLAYING", "VICTORY", "DEFEAT"
        self.p_score = 0
        self.cpu_score = 0
        self.paddle_h = 18
        self.p_y = 58.0
        self.cpu_y = 58.0
        self.rally = 0
        self.particles = []
        self.init_ball(serve_to_cpu=True)

    def init_ball(self, serve_to_cpu=True):
        self.ball_x = 64.0
        self.ball_y = float(random.randint(40, 85))
        spd_x = 2.4 if serve_to_cpu else -2.4
        self.ball_vx = spd_x
        self.ball_vy = random.choice([-1.4, -0.8, 0.8, 1.4])
        self.rally = 0

    def move_up(self):
        if self.state != "PLAYING":
            return
        self.p_y = max(22.0, self.p_y - 5.0)

    def move_down(self):
        if self.state != "PLAYING":
            return
        self.p_y = min(113.0 - self.paddle_h, self.p_y + 5.0)

    def add_particles(self, x, y, count=4, color=None):
        if color is None:
            color = Theme.PRIMARY
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

        # CPU AI tracking with reaction smoothing
        cpu_center = self.cpu_y + self.paddle_h / 2.0
        cpu_speed = 1.9 + min(1.0, self.rally * 0.1)
        if self.ball_vx > 0:  # Ball moving towards CPU
            if cpu_center < self.ball_y - 2:
                self.cpu_y = min(113.0 - self.paddle_h, self.cpu_y + cpu_speed)
            elif cpu_center > self.ball_y + 2:
                self.cpu_y = max(22.0, self.cpu_y - cpu_speed)

        # Move ball
        self.ball_x += self.ball_vx
        self.ball_y += self.ball_vy

        # Top & Bottom wall bounce
        if self.ball_y <= 22:
            self.ball_y = 22
            self.ball_vy = abs(self.ball_vy)
        elif self.ball_y >= 111:
            self.ball_y = 111
            self.ball_vy = -abs(self.ball_vy)

        # Player paddle collision (x = 8..11)
        if self.ball_vx < 0 and 7 <= self.ball_x <= 12:
            if self.p_y - 2 <= self.ball_y <= self.p_y + self.paddle_h + 2:
                self.ball_x = 12
                self.rally += 1
                hit_offset = (self.ball_y - (self.p_y + self.paddle_h / 2.0)) / (self.paddle_h / 2.0)
                speed = 2.4 + min(1.6, self.rally * 0.15)
                self.ball_vx = speed
                self.ball_vy = hit_offset * 2.2
                self.add_particles(self.ball_x, self.ball_y, 4, Theme.PRIMARY)

        # CPU paddle collision (x = 116..119)
        if self.ball_vx > 0 and 115 <= self.ball_x <= 120:
            if self.cpu_y - 2 <= self.ball_y <= self.cpu_y + self.paddle_h + 2:
                self.ball_x = 115
                self.rally += 1
                hit_offset = (self.ball_y - (self.cpu_y + self.paddle_h / 2.0)) / (self.paddle_h / 2.0)
                speed = 2.4 + min(1.6, self.rally * 0.15)
                self.ball_vx = -speed
                self.ball_vy = hit_offset * 2.2
                self.add_particles(self.ball_x, self.ball_y, 4, Theme.WARNING)

        # Scoring
        if self.ball_x < 2:
            # CPU scored
            self.cpu_score += 1
            self.add_particles(6, self.ball_y, 7, Theme.DANGER)
            if self.cpu_score >= 7:
                self.state = "DEFEAT"
            else:
                self.init_ball(serve_to_cpu=False)
        elif self.ball_x > 125:
            # Player scored
            self.p_score += 1
            self.add_particles(122, self.ball_y, 7, Theme.SUCCESS)
            if self.p_score >= 7:
                self.state = "VICTORY"
                self.wins += 1
                save_high_score(self.wins)
            else:
                self.init_ball(serve_to_cpu=True)


def render_game_screen(lcd, game):
    ui.header(lcd, "PICO PONG", right_badge=f"WINS {game.wins}", accent=Theme.INFO)

    # 1px border dividers
    lcd.hline(0, 19, 128, Theme.BORDER)
    lcd.hline(0, 115, 128, Theme.BORDER)

    # Net dashed centerline
    for y in range(22, 113, 6):
        lcd.vline(64, y, 3, color565(35, 42, 60))

    # Player paddle (Left, Cyan)
    py = int(game.p_y)
    lcd.fill_rect(8, py, 3, game.paddle_h, Theme.PRIMARY)

    # CPU paddle (Right, Amber)
    cpuy = int(game.cpu_y)
    lcd.fill_rect(117, cpuy, 3, game.paddle_h, Theme.WARNING)

    # Ball
    bx = int(game.ball_x)
    by = int(game.ball_y)
    lcd.fill_rect(bx - 1, by - 1, 3, 3, Theme.TEXT)

    # Particles
    for p in game.particles:
        lcd.pixel(int(p[0]), int(p[1]), p[5])

    # Scoreboard in bottom HUD
    ui.draw_text(lcd, f"YOU {game.p_score}", 16, 118, Theme.PRIMARY, font="6x8")
    ui.draw_centered(lcd, f"RALLY {game.rally}", 118, Theme.TEXT_MUTED, font="6x8")
    ui.draw_right(lcd, f"{game.cpu_score} CPU", 118, Theme.WARNING, margin=16, font="6x8")

    # Victory / Defeat Overlays (Zero Boxes, 1px Horizontal Dividers)
    if game.state == "VICTORY":
        lcd.fill_rect(0, 38, 128, 50, Theme.BG)
        lcd.hline(0, 38, 128, Theme.SUCCESS)
        ui.draw_centered(lcd, "MATCH VICTORY!", 45, Theme.SUCCESS, font="6x8")
        ui.draw_centered(lcd, f"FINAL: {game.p_score} - {game.cpu_score}", 58, Theme.TEXT, font="6x8")
        ui.draw_centered(lcd, "PICO BOT DEFEATED", 69, Theme.INFO, font="6x8")
        lcd.hline(0, 87, 128, Theme.SUCCESS)
    elif game.state == "DEFEAT":
        lcd.fill_rect(0, 38, 128, 50, Theme.BG)
        lcd.hline(0, 38, 128, Theme.DANGER)
        ui.draw_centered(lcd, "PICO BOT WON", 45, Theme.DANGER, font="6x8")
        ui.draw_centered(lcd, f"FINAL: {game.p_score} - {game.cpu_score}", 58, Theme.TEXT, font="6x8")
        ui.draw_centered(lcd, "PRESS K2 FOR REMATCH", 69, Theme.WARNING, font="6x8")
        lcd.hline(0, 87, 128, Theme.DANGER)
