"""
Blackjack (21) Game Engine & Ultra-Minimalist UI for Raspberry Pi Pico W.
Hardware: ST7735S 128x128 LCD with 3-button control (KEY3=Hit, KEY2=Stand/Deal, KEY1=Exit).
Zero card boxes / container cards architecture with 1px horizontal dividers.
"""

import random
import picoui as ui
from picoui import Theme, color565

RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
SUITS = ["S", "H", "D", "C"]  # Spades, Hearts, Diamonds, Clubs
CHIPS_FILE = "bj_chips.txt"

def load_chips():
    try:
        with open(CHIPS_FILE, "r") as f:
            return int(f.read().strip())
    except Exception:
        return 100

def save_chips(chips):
    try:
        with open(CHIPS_FILE, "w") as f:
            f.write(str(int(chips)))
    except Exception:
        pass

def calculate_score(hand):
    val = 0
    aces = 0
    for card in hand:
        r = card[0]
        if r == "A":
            aces += 1
            val += 11
        elif r in ("J", "Q", "K"):
            val += 10
        else:
            val += int(r)
    while val > 21 and aces > 0:
        val -= 10
        aces -= 1
    return val

class BlackjackGame:
    def __init__(self):
        self.deck = []
        self.player_hand = []
        self.dealer_hand = []
        self.state = "PLAYING"  # "PLAYING", "WIN", "LOSE", "BUST", "PUSH", "BLACKJACK"
        self.wins = 0
        self.losses = 0
        self.pushes = 0
        self.chips = load_chips()
        self.bet = 10
        self.reset_deck()
        self.deal()

    def reset_deck(self):
        self.deck = [(r, s) for r in RANKS for s in SUITS]
        for i in range(len(self.deck) - 1, 0, -1):
            j = random.randint(0, i)
            self.deck[i], self.deck[j] = self.deck[j], self.deck[i]

    def draw_card(self):
        if len(self.deck) < 10:
            self.reset_deck()
        return self.deck.pop()

    def deal(self):
        if len(self.deck) < 10:
            self.reset_deck()
        if self.chips < self.bet:
            self.chips = 100  # Reload chips when bankroll empty
        self.player_hand = [self.draw_card(), self.draw_card()]
        self.dealer_hand = [self.draw_card(), self.draw_card()]
        self.state = "PLAYING"
        p = self.get_player_score()
        d = self.get_dealer_score(False)
        if p == 21:
            if d == 21:
                self.state = "PUSH"
                self.pushes += 1
            else:
                self.state = "BLACKJACK"
                self.wins += 1
                self.chips += int(self.bet * 1.5)
                save_chips(self.chips)

    def hit(self):
        if self.state != "PLAYING":
            return
        self.player_hand.append(self.draw_card())
        p = self.get_player_score()
        if p > 21:
            self.state = "BUST"
            self.losses += 1
            self.chips = max(0, self.chips - self.bet)
            save_chips(self.chips)
        elif p == 21:
            self.stand()

    def stand(self):
        if self.state != "PLAYING":
            return
        while self.get_dealer_score(False) < 17:
            self.dealer_hand.append(self.draw_card())
        p = self.get_player_score()
        d = self.get_dealer_score(False)
        if d > 21:
            self.state = "WIN"
            self.wins += 1
            self.chips += self.bet
            save_chips(self.chips)
        elif p > d:
            self.state = "WIN"
            self.wins += 1
            self.chips += self.bet
            save_chips(self.chips)
        elif p < d:
            self.state = "LOSE"
            self.losses += 1
            self.chips = max(0, self.chips - self.bet)
            save_chips(self.chips)
        else:
            self.state = "PUSH"
            self.pushes += 1

    def get_player_score(self):
        return calculate_score(self.player_hand)

    def get_dealer_score(self, hide_hole=True):
        if hide_hole and self.state == "PLAYING":
            return calculate_score([self.dealer_hand[0]])
        return calculate_score(self.dealer_hand)

def draw_card(lcd, x, y, rank, suit, is_hidden=False):
    """
    Renders a crisp 17x21 mini playing card on the LCD.
    """
    w, h = 17, 21
    if is_hidden:
        # Hole card back: deep indigo with border and question mark
        lcd.fill_rect(x, y, w, h, Theme.SURFACE_ALT)
        lcd.rect(x, y, w, h, Theme.BORDER)
        ui.draw_text(lcd, "?", x + 6, y + 6, Theme.PRIMARY, font="6x8")
    else:
        # Card face: bright card white
        lcd.fill_rect(x, y, w, h, Theme.TEXT)
        lcd.rect(x, y, w, h, Theme.BORDER)

        # Suit & rank color
        is_red = suit in ("H", "D")
        text_col = Theme.DANGER if is_red else color565(18, 22, 34)

        # Rank
        if rank == "10":
            ui.draw_text(lcd, "10", x + 2, y + 2, text_col, font="6x8")
        else:
            ui.draw_text(lcd, rank, x + 3, y + 2, text_col, font="6x8")

        # Suit symbol/letter
        ui.draw_text(lcd, suit, x + 6, y + 11, text_col, font="6x8")

def render_game_screen(lcd, game):
    """
    Renders complete 21 Blackjack gaming screen on 128x128 panel.
    Strictly follows zero-box minimalist architecture with 1px dividers.
    """
    ui.header(lcd, "21 BLACKJACK", right_badge=f"${game.chips}", accent=Theme.SUCCESS)

    # =========================================================================
    # Section 1: DEALER HAND (y = 20..52)
    # =========================================================================
    ui.draw_text(lcd, "DEALER", 6, 21, Theme.TEXT_MUTED, font="6x8")
    d_score = game.get_dealer_score(hide_hole=(game.state == "PLAYING"))
    d_variant = "info" if game.state == "PLAYING" else ("danger" if d_score > 21 else "warning")
    ui.badge(lcd, 122, 20, str(d_score), variant=d_variant, align_right=True)

    # Dealer Cards (max 5 displayed)
    for i, card in enumerate(game.dealer_hand[:5]):
        cx = 6 + i * 19
        is_hidden = (i == 1 and game.state == "PLAYING")
        draw_card(lcd, cx, 30, card[0], card[1], is_hidden=is_hidden)

    # 1px Horizontal Divider Line 1
    lcd.hline(6, 53, 116, Theme.BORDER)

    # =========================================================================
    # Section 2: PLAYER / YOU (y = 55..87)
    # =========================================================================
    ui.draw_text(lcd, "YOU", 6, 56, Theme.TEXT_MUTED, font="6x8")
    p_score = game.get_player_score()
    p_variant = "success" if p_score == 21 else ("danger" if p_score > 21 else "primary")
    ui.badge(lcd, 122, 55, str(p_score), variant=p_variant, align_right=True)

    # Player Cards (max 5 displayed)
    for i, card in enumerate(game.player_hand[:5]):
        cx = 6 + i * 19
        draw_card(lcd, cx, 65, card[0], card[1], is_hidden=False)

    # 1px Horizontal Divider Line 2
    lcd.hline(6, 88, 116, Theme.BORDER)

    # =========================================================================
    # Section 3: GAME STATUS & RECORD (y = 90..127)
    # =========================================================================
    if game.state == "PLAYING":
        ui.draw_text(lcd, "STATUS", 6, 92, Theme.TEXT_MUTED, font="6x8")
        ui.badge(lcd, 122, 92, "IN PLAY", variant="info", align_right=True)

        ui.draw_text(lcd, f"BET: ${game.bet}", 6, 104, Theme.WARNING, font="6x8")
        ui.draw_right(lcd, f"W:{game.wins} L:{game.losses}", 104, Theme.TEXT_MUTED, margin=6, font="6x8")

        ui.draw_text(lcd, f"CHIPS: ${game.chips}", 6, 116, Theme.SUCCESS, font="6x8")
        ui.draw_right(lcd, f"DECK:{len(game.deck)}", 116, Theme.TEXT_DARK, margin=6, font="6x8")
    else:
        # Hand Result outcome
        if game.state == "WIN":
            ui.draw_big(lcd, "WIN!", 6, 92, Theme.SUCCESS)
            ui.badge(lcd, 122, 92, f"+${game.bet}", variant="success", align_right=True)
        elif game.state == "BLACKJACK":
            ui.draw_big(lcd, "BJ 21!", 6, 92, Theme.SUCCESS)
            ui.badge(lcd, 122, 92, f"+${int(game.bet * 1.5)}", variant="success", align_right=True)
        elif game.state == "BUST":
            ui.draw_big(lcd, "BUST!", 6, 92, Theme.DANGER)
            ui.badge(lcd, 122, 92, f"-${game.bet}", variant="danger", align_right=True)
        elif game.state == "LOSE":
            ui.draw_big(lcd, "LOSE!", 6, 92, Theme.DANGER)
            ui.badge(lcd, 122, 92, f"-${game.bet}", variant="danger", align_right=True)
        elif game.state == "PUSH":
            ui.draw_big(lcd, "PUSH!", 6, 92, Theme.WARNING)
            ui.badge(lcd, 122, 92, "TIE", variant="warning", align_right=True)

        ui.draw_text(lcd, f"CHIPS: ${game.chips}", 6, 115, Theme.TEXT, font="6x8")
        ui.draw_right(lcd, f"W:{game.wins} L:{game.losses} P:{game.pushes}", 115, Theme.TEXT_MUTED, margin=6, font="6x8")
