"""
Cyber Copter Arcade Game Engine & Minimalist UI for Raspberry Pi Pico W.
Controls: KEY3=Thrust/Ascend, KEY2=Missile/Start, KEY1=Exit to Games Hub.
Zero container boxes architecture with 1px horizontal dividers.
"""

import random
import picoui as ui
from picoui import Theme, color565

HS_FILE = "copter_hiscore.txt"

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

class CyberCopterGame:
    def __init__(self):
        self.high_score = load_high_score()
        self.reset()

    def reset(self):
        self.state = "PLAYING"  # "PLAYING", "GAMEOVER"
        self.x = 20.0
        self.y = 64.0
        self.vy = 0.0
        self.score = 0
        self.distance = 0
        self.flicker = 0
        self.missiles = []     # max 2: [[x, y], ...]
        self.particles = []    # max 8: [[x, y, vx, vy, life, col], ...]
        self.orbs = []         # max 2: [[x, y], ...]
        self.pillars = []      # max 3: [[x, top_y, bot_y, w, alive], ...]
        self.spawn_timer = 0

        # Procedural cavern terrain (16 segments across screen, each 8px wide)
        # top_ceilings and bot_floors: bounds are y=20 (header) to y=115 (HUD)
        self.cavern = []
        c_top = 26
        c_bot = 108
        for i in range(18):
            self.cavern.append([i * 8, c_top, c_bot])

    def thrust(self):
        if self.state != "PLAYING":
            return
        self.vy -= 2.2
        if self.vy < -4.0:
            self.vy = -4.0
        # Jet exhaust sparks
        if len(self.particles) < 8:
            self.particles.append([self.x - 2, self.y + 2, -2.0, random.uniform(-0.5, 0.5), 4, Theme.WARNING])

    def fire(self):
        if self.state != "PLAYING":
            return
        if len(self.missiles) < 2:
            self.missiles.append([self.x + 12, int(round(self.y))])

    def add_particles(self, x, y, count=5, color=None):
        if color is None:
            color = Theme.WARNING
        for _ in range(count):
            if len(self.particles) >= 8:
                self.particles.pop(0)
            self.particles.append([float(x), float(y), random.uniform(-3, 3), random.uniform(-3, 3), 6, color])

    def update(self):
        # Update particles
        alive_particles = []
        for p in self.particles:
            p[0] += p[2]
            p[1] += p[3]
            p[4] -= 1
            if p[4] > 0 and 0 <= p[0] <= 127 and 20 <= p[1] <= 115:
                alive_particles.append(p)
        self.particles = alive_particles

        if self.state != "PLAYING":
            return

        self.flicker = (self.flicker + 1) % 4
        self.distance += 1
        if self.distance % 5 == 0:
            self.score += 1

        # Copter gravity physics
        self.vy += 0.42
        if self.vy > 3.8:
            self.vy = 3.8
        self.y += self.vy

        # Advance cavern scroll
        speed = 2.0 + min(1.8, self.distance * 0.001)
        for seg in self.cavern:
            seg[0] -= speed

        if self.cavern[0][0] <= -8:
            self.cavern.pop(0)
            last_x = self.cavern[-1][0]
            last_top = self.cavern[-1][1]
            last_bot = self.cavern[-1][2]
            # Undulate terrain
            new_top = max(22, min(55, last_top + random.randint(-3, 3)))
            new_bot = min(113, max(75, last_bot + random.randint(-3, 3)))
            if new_bot - new_top < 30:
                new_bot = new_top + 30
            self.cavern.append([last_x + 8, new_top, new_bot])

        # Update missiles
        alive_missiles = []
        for m in self.missiles:
            m[0] += 5.5
            if m[0] <= 124:
                alive_missiles.append(m)
        self.missiles = alive_missiles

        # Spawn obstacle pillars & energy orbs
        self.spawn_timer += 1
        if self.spawn_timer >= 45:
            self.spawn_timer = 0
            # 70% pillar, 30% orb
            if random.random() < 0.7 and len(self.pillars) < 3:
                # Find cavern gap at right edge
                c_t = self.cavern[-1][1]
                c_b = self.cavern[-1][2]
                mid = (c_t + c_b) // 2
                p_h = 16
                self.pillars.append([128.0, mid - p_h // 2, mid + p_h // 2, 8, True])
            elif len(self.orbs) < 2:
                c_t = self.cavern[-1][1]
                c_b = self.cavern[-1][2]
                self.orbs.append([128.0, float(random.randint(c_t + 6, c_b - 6))])

        # Update orbs
        alive_orbs = []
        for orb in self.orbs:
            orb[0] -= speed
            # Collision with copter
            if abs(orb[0] - self.x) < 8 and abs(orb[1] - self.y) < 8:
                self.score += 50
                self.add_particles(orb[0], orb[1], 5, Theme.SUCCESS)
                continue
            if orb[0] > -8:
                alive_orbs.append(orb)
        self.orbs = alive_orbs

        # Update pillars & collision with missiles
        alive_pillars = []
        for pil in self.pillars:
            pil[0] -= speed
            px = int(pil[0])
            py1 = pil[1]
            py2 = pil[2]

            # Check missile hit
            hit = False
            for m in self.missiles:
                if px <= m[0] <= px + pil[3] and py1 <= m[1] <= py2:
                    hit = True
                    try:
                        self.missiles.remove(m)
                    except ValueError:
                        pass
                    break

            if hit:
                self.score += 75
                self.add_particles(px + 4, (py1 + py2) // 2, 6, Theme.PRIMARY)
                continue

            # Check copter collision with pillar
            if px <= self.x + 8 and self.x - 4 <= px + pil[3]:
                if py1 <= self.y <= py2:
                    self.crash()
                    return

            if pil[0] > -12:
                alive_pillars.append(pil)
        self.pillars = alive_pillars

        # Collision with ceiling or floor
        for seg in self.cavern:
            if seg[0] - 4 <= self.x <= seg[0] + 12:
                if self.y - 4 <= seg[1] or self.y + 4 >= seg[2]:
                    self.crash()
                    return

    def crash(self):
        self.state = "GAMEOVER"
        self.add_particles(self.x, self.y, 8, Theme.DANGER)
        if self.score > self.high_score:
            self.high_score = self.score
            save_high_score(self.high_score)


def draw_copter(lcd, x, y, flicker):
    ix, iy = int(x), int(round(y))
    # Main fuselage
    lcd.fill_rect(ix - 2, iy - 2, 9, 5, Theme.TEXT)
    # Cockpit windshield
    lcd.pixel(ix + 5, iy - 1, Theme.PRIMARY)
    lcd.pixel(ix + 6, iy, Theme.PRIMARY)
    # Tail boom & fin
    lcd.hline(ix - 7, iy, 5, Theme.TEXT_MUTED)
    lcd.pixel(ix - 7, iy - 2, Theme.DANGER)
    # Rotor mast & spinning blade
    lcd.pixel(ix + 1, iy - 3, Theme.BORDER)
    if flicker % 2 == 0:
        lcd.hline(ix - 5, iy - 4, 13, Theme.TEXT)
    else:
        lcd.hline(ix - 2, iy - 4, 7, Theme.TEXT_MUTED)
    # Landing skids
    lcd.hline(ix - 3, iy + 4, 9, Theme.BORDER)
    lcd.pixel(ix - 1, iy + 3, Theme.BORDER)
    lcd.pixel(ix + 3, iy + 3, Theme.BORDER)


def render_game_screen(lcd, game):
    ui.header(lcd, "CYBER COPTER", right_badge=f"{game.distance}m", accent=Theme.WARNING)

    # 1px border dividers
    lcd.hline(0, 19, 128, Theme.BORDER)
    lcd.hline(0, 115, 128, Theme.BORDER)

    # 1. Cavern terrain
    for seg in game.cavern:
        sx = int(seg[0])
        stop = int(seg[1])
        sbot = int(seg[2])
        if -8 <= sx <= 128:
            # Ceiling rock
            lcd.fill_rect(sx, 20, 8, max(0, stop - 20), color565(36, 42, 60))
            lcd.hline(sx, stop, 8, Theme.BORDER)
            # Floor rock
            lcd.fill_rect(sx, sbot, 8, max(0, 115 - sbot), color565(36, 42, 60))
            lcd.hline(sx, sbot, 8, Theme.BORDER)

    # 2. Obstacle pillars
    for pil in game.pillars:
        px = int(pil[0])
        py1 = int(pil[1])
        py2 = int(pil[2])
        pw = pil[3]
        lcd.fill_rect(px, py1, pw, py2 - py1, Theme.DANGER)
        lcd.rect(px, py1, pw, py2 - py1, Theme.WARNING)

    # 3. Energy orbs
    for orb in game.orbs:
        ox, oy = int(orb[0]), int(orb[1])
        lcd.pixel(ox, oy - 2, Theme.SUCCESS)
        lcd.hline(ox - 1, oy - 1, 3, Theme.SUCCESS)
        lcd.hline(ox - 2, oy, 5, Theme.TEXT)
        lcd.hline(ox - 1, oy + 1, 3, Theme.SUCCESS)
        lcd.pixel(ox, oy + 2, Theme.SUCCESS)

    # 4. Missiles
    for m in game.missiles:
        mx, my = int(m[0]), int(m[1])
        lcd.hline(mx, my, 4, Theme.PRIMARY)
        lcd.pixel(mx + 4, my, Theme.TEXT)

    # 5. Particles
    for p in game.particles:
        lcd.pixel(int(p[0]), int(p[1]), p[5])

    # 6. Copter
    if game.state == "PLAYING":
        draw_copter(lcd, game.x, game.y, game.flicker)

    # 7. Bottom HUD: Score & Best
    ui.draw_text(lcd, f"DIST {game.distance}m", 6, 118, Theme.TEXT_MUTED, font="6x8")
    ui.draw_right(lcd, f"SCR {game.score:04d}", 118, Theme.TEXT, margin=6, font="6x8")

    # 8. Game Over Overlay (Zero Boxes, 1px Horizontal Dividers)
    if game.state == "GAMEOVER":
        lcd.fill_rect(0, 38, 128, 50, Theme.BG)
        lcd.hline(0, 38, 128, Theme.DANGER)
        ui.draw_centered(lcd, "COPTER CRASHED", 45, Theme.DANGER, font="6x8")
        ui.draw_centered(lcd, f"SCORE: {game.score}", 58, Theme.TEXT, font="6x8")
        ui.draw_centered(lcd, f"BEST:  {game.high_score}", 69, Theme.WARNING, font="6x8")
        lcd.hline(0, 87, 128, Theme.DANGER)
