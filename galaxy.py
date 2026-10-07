"""
Galaxy Quest Arcade Game Engine & Minimalist UI for Raspberry Pi Pico W.
Hardware: ST7735S 128x128 LCD with 3-button control (KEY3=Corridor, KEY2=Fire/Start, KEY1=Exit).
Zero container boxes / cards architecture with 1px horizontal dividers.
"""

import random
import picoui as ui
from picoui import Theme, color565

LANES = [35, 65, 95]
HS_FILE = "gq_hiscore.txt"

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

class GalaxyQuestGame:
    def __init__(self):
        self.high_score = load_high_score()
        self.init_stars()
        self.reset()

    def init_stars(self):
        # 14 bounded parallax stars: [x, y, speed, color]
        self.stars = []
        c_dim = color565(75, 85, 115)
        c_mid = color565(140, 155, 185)
        c_brt = Theme.TEXT
        for _ in range(6):
            self.stars.append([random.randint(0, 127), random.randint(22, 113), 1, c_dim])
        for _ in range(5):
            self.stars.append([random.randint(0, 127), random.randint(22, 113), 2, c_mid])
        for _ in range(3):
            self.stars.append([random.randint(0, 127), random.randint(22, 113), 3, c_brt])

    def reset(self):
        self.state = "PLAYING"  # "PLAYING", "GAMEOVER"
        self.ship_x = 12
        self.lane_idx = 1
        self.ship_y = float(LANES[self.lane_idx])
        self.target_y = float(LANES[self.lane_idx])
        self.shields = 3
        self.score = 0
        self.distance = 0
        self.sector = 1
        self.spawn_timer = 0
        self.torpedoes = []   # max 2: [[x, y], ...]
        self.hazards = []     # max 3: [[type, x, lane_y, speed], ...]
        self.particles = []   # max 8: [[x, y, vx, vy, life, col], ...]
        self.flicker = 0
        self.hit_flash = 0

    def move_ship(self):
        if self.state != "PLAYING":
            return
        self.lane_idx = (self.lane_idx + 1) % len(LANES)
        self.target_y = float(LANES[self.lane_idx])

    def fire(self):
        if self.state != "PLAYING":
            return
        if len(self.torpedoes) < 2:
            self.torpedoes.append([self.ship_x + 13, int(round(self.ship_y))])

    def add_particles(self, x, y, count=5, color=None):
        if color is None:
            color = Theme.WARNING
        for _ in range(count):
            if len(self.particles) >= 8:
                self.particles.pop(0)
            vx = random.randint(-3, 3)
            vy = random.randint(-3, 3)
            self.particles.append([float(x), float(y), float(vx), float(vy), 6, color])

    def update(self):
        # Update starfield parallax
        for star in self.stars:
            star[0] -= star[2]
            if star[0] < 0:
                star[0] = 127
                star[1] = random.randint(22, 113)

        # Update explosion particles
        alive_particles = []
        for p in self.particles:
            p[0] += p[2]
            p[1] += p[3]
            p[4] -= 1
            if p[4] > 0 and 0 <= p[0] <= 127 and 20 <= p[1] <= 115:
                alive_particles.append(p)
        self.particles = alive_particles

        if self.hit_flash > 0:
            self.hit_flash -= 1

        if self.state != "PLAYING":
            return

        self.flicker = (self.flicker + 1) % 4
        self.distance += 1

        # Smooth glide towards target lane
        dy = self.target_y - self.ship_y
        self.ship_y += dy * 0.38

        # Sector progression
        new_sector = 1 + (self.distance // 450)
        if new_sector > self.sector:
            self.sector = new_sector
            self.score += 200

        # Update torpedoes
        alive_torps = []
        for torp in self.torpedoes:
            torp[0] += 6
            if torp[0] <= 124:
                alive_torps.append(torp)
        self.torpedoes = alive_torps

        # Spawn obstacles / items
        self.spawn_timer += 1
        spawn_rate = max(18, 38 - self.sector * 3)
        if self.spawn_timer >= spawn_rate and len(self.hazards) < 3:
            self.spawn_timer = 0
            lane = LANES[random.randint(0, len(LANES) - 1)]
            # 60% Asteroid, 25% Alien Interceptor, 15% Beryllium Sphere
            roll = random.randint(1, 100)
            if roll <= 60:
                h_type = "ASTEROID"
                spd = 1.8 + (self.sector * 0.25)
            elif roll <= 85:
                h_type = "ALIEN"
                spd = 2.4 + (self.sector * 0.3)
            else:
                h_type = "BERYLLIUM"
                spd = 1.5
            self.hazards.append([h_type, 128.0, float(lane), spd])

        # Update hazards and check collisions
        alive_hazards = []
        ship_box = (self.ship_x, int(round(self.ship_y)) - 5, self.ship_x + 13, int(round(self.ship_y)) + 5)

        for h in self.hazards:
            h[1] -= h[3]
            hx = int(h[1])
            hy = int(h[2])
            h_type = h[0]

            # Check torpedo collision
            hit_by_torp = False
            for torp in self.torpedoes:
                tx, ty = torp[0], torp[1]
                if abs(tx - hx) < 8 and abs(ty - hy) < 9:
                    hit_by_torp = True
                    try:
                        self.torpedoes.remove(torp)
                    except ValueError:
                        pass
                    break

            if hit_by_torp:
                if h_type == "ASTEROID":
                    self.score += 50
                    self.add_particles(hx, hy, 5, Theme.TEXT_MUTED)
                elif h_type == "ALIEN":
                    self.score += 100
                    self.add_particles(hx, hy, 6, Theme.DANGER)
                elif h_type == "BERYLLIUM":
                    self.score += 30
                    self.add_particles(hx, hy, 4, Theme.SUCCESS)
                continue

            # Check ship collision
            h_box = (hx - 4, hy - 5, hx + 5, hy + 5)
            collision = not (ship_box[2] < h_box[0] or ship_box[0] > h_box[2] or ship_box[3] < h_box[1] or ship_box[1] > h_box[3])

            if collision:
                if h_type == "BERYLLIUM":
                    self.shields = min(3, self.shields + 1)
                    self.score += 150
                    self.add_particles(hx, hy, 6, Theme.SUCCESS)
                else:
                    self.shields -= 1
                    self.hit_flash = 3
                    self.add_particles(hx, hy, 7, Theme.WARNING)
                    if self.shields <= 0:
                        self.state = "GAMEOVER"
                        self.add_particles(self.ship_x + 6, int(round(self.ship_y)), 8, Theme.DANGER)
                        if self.score > self.high_score:
                            self.high_score = self.score
                            save_high_score(self.high_score)
                continue

            if h[1] > -10:
                alive_hazards.append(h)

        self.hazards = alive_hazards


def draw_protector(lcd, x, y, flicker):
    """
    Renders the NSEA Protector starship vector silhouette.
    """
    # Sleek central fuselage
    lcd.fill_rect(x + 2, y - 2, 7, 5, Theme.TEXT)
    # Nose cone & torpedo emitter
    lcd.pixel(x + 9, y, Theme.TEXT)
    lcd.pixel(x + 10, y, Theme.PRIMARY)
    # Illuminated command bridge
    lcd.pixel(x + 5, y - 1, Theme.PRIMARY)
    # Twin warp nacelles
    lcd.hline(x - 1, y - 4, 7, Theme.TEXT_MUTED)
    lcd.hline(x - 1, y + 4, 7, Theme.TEXT_MUTED)
    # Pylon struts
    lcd.pixel(x + 2, y - 3, Theme.BORDER)
    lcd.pixel(x + 2, y + 3, Theme.BORDER)
    # Ion thruster trail
    t_len = 2 + (flicker % 3)
    lcd.hline(x - 1 - t_len, y, t_len, Theme.PRIMARY)
    lcd.pixel(x - 1, y, Theme.WARNING)


def draw_asteroid(lcd, x, y):
    """
    Renders irregular rocky asteroid with crater accents.
    """
    lcd.fill_rect(x - 2, y - 4, 5, 9, Theme.TEXT_MUTED)
    lcd.fill_rect(x - 4, y - 2, 9, 5, Theme.TEXT_MUTED)
    lcd.pixel(x - 1, y - 1, Theme.BORDER)
    lcd.pixel(x + 1, y + 2, Theme.BORDER)
    lcd.pixel(x - 3, y - 3, color565(30, 36, 50))


def draw_alien(lcd, x, y):
    """
    Renders Sarris hostile alien interceptor craft.
    """
    # Wing delta
    lcd.fill_rect(x - 3, y - 1, 7, 3, Theme.DANGER)
    lcd.pixel(x + 1, y - 3, Theme.DANGER)
    lcd.pixel(x, y - 2, Theme.DANGER)
    lcd.pixel(x + 1, y + 3, Theme.DANGER)
    lcd.pixel(x, y + 2, Theme.DANGER)
    # Menacing optic scanner
    lcd.pixel(x - 4, y, Theme.WARNING)
    lcd.pixel(x + 3, y, Theme.TEXT)


def draw_beryllium(lcd, x, y):
    """
    Renders glowing Beryllium Sphere crystal power-up.
    """
    lcd.pixel(x, y - 3, Theme.SUCCESS)
    lcd.hline(x - 1, y - 2, 3, Theme.SUCCESS)
    lcd.hline(x - 2, y - 1, 5, Theme.SUCCESS)
    lcd.hline(x - 3, y, 7, Theme.TEXT)
    lcd.hline(x - 2, y + 1, 5, Theme.SUCCESS)
    lcd.hline(x - 1, y + 2, 3, Theme.SUCCESS)
    lcd.pixel(x, y + 3, Theme.SUCCESS)
    lcd.pixel(x, y, Theme.WARNING)


def render_game_screen(lcd, game):
    """
    Renders Galaxy Quest arcade display on 128x128 panel.
    Strictly follows zero-box minimalist architecture with 1px dividers.
    """
    # Header
    ui.header(lcd, "GALAXY QUEST", right_badge=f"SEC {game.sector}", accent=Theme.INFO)

    # Top & bottom 1px divider lines
    lcd.hline(0, 19, 128, Theme.BORDER)
    lcd.hline(0, 115, 128, Theme.BORDER)

    # 1. Starfield background
    for star in game.stars:
        lcd.pixel(star[0], star[1], star[3])

    # 2. Torpedoes
    for torp in game.torpedoes:
        tx, ty = torp[0], torp[1]
        lcd.hline(tx, ty, 4, Theme.PRIMARY)
        lcd.pixel(tx + 4, ty, Theme.TEXT)

    # 3. Hazards / Items
    for h in game.hazards:
        hx, hy = int(h[1]), int(h[2])
        if h[0] == "ASTEROID":
            draw_asteroid(lcd, hx, hy)
        elif h[0] == "ALIEN":
            draw_alien(lcd, hx, hy)
        elif h[0] == "BERYLLIUM":
            draw_beryllium(lcd, hx, hy)

    # 4. Explosion particles
    for p in game.particles:
        px, py = int(p[0]), int(p[1])
        lcd.pixel(px, py, p[5])

    # 5. Player Starship
    if game.state == "PLAYING":
        sy = int(round(game.ship_y))
        draw_protector(lcd, game.ship_x, sy, game.flicker)
        if game.hit_flash > 0:
            lcd.rect(game.ship_x - 3, sy - 6, 18, 13, Theme.WARNING)

    # 6. Bottom HUD: Shields & Score
    # Shield pips
    shd_col = Theme.SUCCESS if game.shields == 3 else (Theme.WARNING if game.shields == 2 else Theme.DANGER)
    ui.draw_text(lcd, "SHD", 6, 118, Theme.TEXT_MUTED, font="6x8")
    for i in range(3):
        pip_x = 28 + i * 7
        if i < game.shields:
            lcd.fill_rect(pip_x, 118, 5, 7, shd_col)
        else:
            lcd.rect(pip_x, 118, 5, 7, Theme.SURFACE_ALT)

    # Score right-aligned
    scr_str = f"{game.score:05d}"
    ui.draw_right(lcd, f"SCR {scr_str}", 118, Theme.TEXT, margin=6, font="6x8")

    # 7. Game Over Overlay (Zero Boxes, 1px Horizontal Dividers)
    if game.state == "GAMEOVER":
        lcd.fill_rect(0, 38, 128, 50, Theme.BG)
        lcd.hline(0, 38, 128, Theme.DANGER)
        ui.draw_centered(lcd, "MISSION FAILED", 45, Theme.DANGER, font="6x8")
        ui.draw_centered(lcd, f"SCORE: {game.score}", 58, Theme.TEXT, font="6x8")
        ui.draw_centered(lcd, f"BEST:  {game.high_score}", 69, Theme.WARNING, font="6x8")
        lcd.hline(0, 87, 128, Theme.DANGER)
