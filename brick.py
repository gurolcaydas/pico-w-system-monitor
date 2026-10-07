"""
Cyber Brick (Arkanoid / Breakout) Arcade Game for Raspberry Pi Pico W.
Controls: KEY3=Paddle Left, KEY2=Paddle Right, KEY1=Exit to Games Hub.
Zero container boxes architecture with 1px horizontal dividers.
"""

import random
import picoui as ui
from picoui import Theme, color565

HS_FILE = "brick_hiscore.txt"

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

class CyberBrickGame:
    def __init__(self):
        self.high_score = load_high_score()
        self.reset()

    def reset(self):
        self.state = "PLAYING"  # "PLAYING", "GAMEOVER"
        self.score = 0
        self.lives = 3
        self.level = 1
        self.paddle_w = 22
        self.paddle_x = 53.0
        self.paddle_y = 108
        self.particles = []
        self.init_ball()
        self.init_bricks()

    def init_ball(self):
        self.ball_x = self.paddle_x + self.paddle_w // 2
        self.ball_y = float(self.paddle_y - 4)
        self.ball_vx = random.choice([-1.8, 1.8])
        self.ball_vy = -2.2

    def init_bricks(self):
        # 3 rows x 6 cols = 18 bricks
        # Arena width: 128 px, margin: 7 px left/right -> 114 px usable
        # Each brick: 17 px wide, 6 px high, gap: 2 px
        self.bricks = []
        cols = 6
        bw = 17
        bh = 6
        gap_x = 2
        gap_y = 3
        start_x = 8
        start_y = 26
        for r in range(3):
            # Row 0: Red (50 pts), Row 1: Amber (30 pts), Row 2: Cyan (10 pts)
            pts = 50 if r == 0 else (30 if r == 1 else 10)
            col = Theme.DANGER if r == 0 else (Theme.WARNING if r == 1 else Theme.INFO)
            for c in range(cols):
                bx = start_x + c * (bw + gap_x)
                by = start_y + r * (bh + gap_y)
                self.bricks.append([bx, by, bw, bh, pts, col, True])

    def move_left(self):
        if self.state != "PLAYING":
            return
        self.paddle_x = max(4.0, self.paddle_x - 7.0)

    def move_right(self):
        if self.state != "PLAYING":
            return
        self.paddle_x = min(124.0 - self.paddle_w, self.paddle_x + 7.0)

    def add_particles(self, x, y, count=4, color=None):
        if color is None:
            color = Theme.WARNING
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

        # Move ball
        self.ball_x += self.ball_vx
        self.ball_y += self.ball_vy

        # Wall collisions (Left & Right)
        if self.ball_x <= 4:
            self.ball_x = 4
            self.ball_vx = abs(self.ball_vx)
        elif self.ball_x >= 123:
            self.ball_x = 123
            self.ball_vx = -abs(self.ball_vx)

        # Top wall collision
        if self.ball_y <= 21:
            self.ball_y = 21
            self.ball_vy = abs(self.ball_vy)

        # Paddle collision
        px = self.paddle_x
        py = float(self.paddle_y)
        if py - 3 <= self.ball_y <= py + 3 and px - 2 <= self.ball_x <= px + self.paddle_w + 2:
            self.ball_y = py - 3
            self.ball_vy = -abs(self.ball_vy)
            # Deflection angle based on hit location
            hit_offset = (self.ball_x - (px + self.paddle_w / 2.0)) / (self.paddle_w / 2.0)
            self.ball_vx = hit_offset * 2.8
            self.add_particles(self.ball_x, self.ball_y, 3, Theme.PRIMARY)

        # Brick collisions
        for b in self.bricks:
            if not b[6]:
                continue
            bx, by, bw, bh = b[0], b[1], b[2], b[3]
            if bx <= self.ball_x <= bx + bw and by <= self.ball_y <= by + bh:
                b[6] = False  # Destroy brick
                self.score += b[4]
                self.ball_vy = -self.ball_vy
                self.add_particles(bx + bw // 2, by + bh // 2, 6, b[5])
                break

        # Check wave cleared
        if not any(b[6] for b in self.bricks):
            self.level += 1
            self.score += 200
            self.init_bricks()
            self.init_ball()

        # Ball fallen below bottom
        if self.ball_y > 115:
            self.lives -= 1
            self.add_particles(self.ball_x, 114, 8, Theme.DANGER)
            if self.lives <= 0:
                self.state = "GAMEOVER"
                if self.score > self.high_score:
                    self.high_score = self.score
                    save_high_score(self.high_score)
            else:
                self.init_ball()


def render_game_screen(lcd, game):
    ui.header(lcd, "CYBER BRICK", right_badge=f"WAVE {game.level}", accent=Theme.INFO)

    # 1px border dividers
    lcd.hline(0, 19, 128, Theme.BORDER)
    lcd.hline(0, 115, 128, Theme.BORDER)

    # 1. Bricks
    for b in game.bricks:
        if b[6]:
            bx, by, bw, bh, _, col, _ = b
            lcd.fill_rect(bx, by, bw, bh, col)
            lcd.pixel(bx + 1, by + 1, Theme.TEXT)

    # 2. Paddle
    px = int(game.paddle_x)
    py = game.paddle_y
    lcd.fill_rect(px, py, game.paddle_w, 4, Theme.PRIMARY)
    lcd.pixel(px, py, Theme.TEXT)
    lcd.pixel(px + game.paddle_w - 1, py, Theme.TEXT)

    # 3. Ball
    bx = int(game.ball_x)
    by = int(game.ball_y)
    lcd.fill_rect(bx - 1, by - 1, 3, 3, Theme.TEXT)
    lcd.pixel(bx, by, Theme.WARNING)

    # 4. Particles
    for p in game.particles:
        lcd.pixel(int(p[0]), int(p[1]), p[5])

    # 5. Bottom HUD: Lives & Score
    ui.draw_text(lcd, "BALL", 6, 118, Theme.TEXT_MUTED, font="6x8")
    for i in range(3):
        col = Theme.SUCCESS if i < game.lives else Theme.SURFACE_ALT
        lcd.fill_rect(34 + i * 7, 118, 5, 7, col)

    ui.draw_right(lcd, f"SCR {game.score:04d}", 118, Theme.TEXT, margin=6, font="6x8")

    # 6. Game Over Overlay (Zero Boxes, 1px Horizontal Dividers)
    if game.state == "GAMEOVER":
        lcd.fill_rect(0, 38, 128, 50, Theme.BG)
        lcd.hline(0, 38, 128, Theme.DANGER)
        ui.draw_centered(lcd, "GAME OVER", 45, Theme.DANGER, font="6x8")
        ui.draw_centered(lcd, f"SCORE: {game.score}", 58, Theme.TEXT, font="6x8")
        ui.draw_centered(lcd, f"BEST:  {game.high_score}", 69, Theme.WARNING, font="6x8")
        lcd.hline(0, 87, 128, Theme.DANGER)
