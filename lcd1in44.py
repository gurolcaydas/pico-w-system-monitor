"""
Waveshare Pico-LCD-1.44 MicroPython Driver
Hardware: Raspberry Pi Pico / Pico W + Waveshare Pico-LCD-1.44 (ST7735S, 128x128)
"""

from machine import Pin, SPI, PWM
import framebuf
import time

# Pin Definitions
BL_PIN   = 13
DC_PIN   = 8
RST_PIN  = 12
MOSI_PIN = 11
SCK_PIN  = 10
CS_PIN   = 9

KEY0_PIN = 15
KEY1_PIN = 17
KEY2_PIN = 2
KEY3_PIN = 3

def color565(r, g, b):
    """
    Convert RGB (0-255, 0-255, 0-255) to byte-swapped RGB565 
    for MicroPython's framebuf on little-endian RP2040.
    """
    c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return ((c & 0xFF) << 8) | ((c >> 8) & 0xFF)


class LCD_1inch44(framebuf.FrameBuffer):
    # Pre-calculated primary colors (byte-swapped for RP2040 FrameBuffer)
    BLACK   = 0x0000
    WHITE   = 0xFFFF
    RED     = 0x00F8
    GREEN   = 0xE007
    BLUE    = 0x1F00
    YELLOW  = 0xE0FF
    CYAN    = 0xFF07
    MAGENTA = 0x1FF8
    GRAY    = 0x1084
    ORANGE  = 0x00FC

    def __init__(self, brightness=70):
        self.width = 128
        self.height = 128

        # 1. Backlight Setup (PWM on GP13)
        self.bl = PWM(Pin(BL_PIN))
        self.bl.freq(1000)
        self.set_backlight(brightness)

        # 2. SPI1 Setup FIRST (at 10 MHz)
        self.spi = SPI(1, baudrate=10_000_000, polarity=0, phase=0,
                       sck=Pin(SCK_PIN), mosi=Pin(MOSI_PIN), miso=None)

        # 3. Control Pins (MUST BE SET AFTER SPI to prevent SPI1_RX hijack of GP8)
        self.dc = Pin(DC_PIN, Pin.OUT)
        self.cs = Pin(CS_PIN, Pin.OUT)
        self.rst = Pin(RST_PIN, Pin.OUT)

        self.cs.value(1)
        self.dc.value(1)

        # 4. Buttons (Active Low with Pull-Up)
        self.key0 = Pin(KEY0_PIN, Pin.IN, Pin.PULL_UP)
        self.key1 = Pin(KEY1_PIN, Pin.IN, Pin.PULL_UP)
        self.key2 = Pin(KEY2_PIN, Pin.IN, Pin.PULL_UP)
        self.key3 = Pin(KEY3_PIN, Pin.IN, Pin.PULL_UP)

        # 5. Framebuffer initialization
        self.buffer = bytearray(self.width * self.height * 2)
        super().__init__(self.buffer, self.width, self.height, framebuf.RGB565)

        # 6. Initialize ST7735S Display Controller
        self.init_display()

    def text_width(self, text):
        """Calculate pixel width of standard 8x8 text."""
        return len(text) * 8

    def draw_text(self, text, x, y, color, size=1, bold=False, shadow=None):
        """Draw clean, crisp 1-pixel native font."""
        self.text(text, x, y, color)

    def draw_centered(self, text, y, color, size=1, bold=False, shadow=None):
        """Draw text cleanly centered on screen."""
        w = len(text) * 8
        x = max(0, (self.width - w) // 2)
        self.text(text, x, y, color)

    def set_backlight(self, percent):
        """Set backlight brightness from 0 to 100%."""
        val = max(0, min(100, percent))
        duty = int(val * 65535 / 100)
        self.bl.duty_u16(duty)

    def write_cmd(self, cmd):
        self.dc.value(0)
        self.cs.value(0)
        self.spi.write(bytearray([cmd]))
        self.cs.value(1)

    def write_data(self, data):
        self.dc.value(1)
        self.cs.value(0)
        if isinstance(data, int):
            self.spi.write(bytearray([data]))
        else:
            self.spi.write(bytearray(data))
        self.cs.value(1)

    def reset(self):
        """Hardware reset pulse."""
        self.rst.value(1)
        time.sleep_ms(50)
        self.rst.value(0)
        time.sleep_ms(50)
        self.rst.value(1)
        time.sleep_ms(100)

    def init_display(self):
        """Official Waveshare ST7735S initialization sequence."""
        self.reset()

        self.write_cmd(0x11)  # Sleep out
        time.sleep_ms(120)

        # Memory Data Access Control (Orientation: Horizontal, BGR order: 0x78)
        self.write_cmd(0x36)
        self.write_data(0x78)

        # Interface Pixel Format (16-bit RGB565)
        self.write_cmd(0x3A)
        self.write_data(0x05)

        # ST7735R Frame Rate
        self.write_cmd(0xB1)
        self.write_data([0x01, 0x2C, 0x2D])
        self.write_cmd(0xB2)
        self.write_data([0x01, 0x2C, 0x2D])
        self.write_cmd(0xB3)
        self.write_data([0x01, 0x2C, 0x2D, 0x01, 0x2C, 0x2D])

        # Column inversion
        self.write_cmd(0xB4)
        self.write_data(0x07)

        # Power Sequence
        self.write_cmd(0xC0)
        self.write_data([0xA2, 0x02, 0x84])
        self.write_cmd(0xC1)
        self.write_data(0xC5)
        self.write_cmd(0xC2)
        self.write_data([0x0A, 0x00])
        self.write_cmd(0xC3)
        self.write_data([0x8A, 0x2A])
        self.write_cmd(0xC4)
        self.write_data([0x8A, 0xEE])
        self.write_cmd(0xC5)
        self.write_data(0x0E)

        # Gamma Sequence
        self.write_cmd(0xE0)
        self.write_data([0x0F, 0x1A, 0x0F, 0x18, 0x2F, 0x28, 0x20, 0x22,
                         0x1F, 0x1B, 0x23, 0x37, 0x00, 0x07, 0x02, 0x10])
        self.write_cmd(0xE1)
        self.write_data([0x0F, 0x1B, 0x0F, 0x17, 0x33, 0x2C, 0x29, 0x2E,
                         0x30, 0x30, 0x39, 0x3F, 0x00, 0x07, 0x03, 0x10])

        # Unlock manufacturer test mode & disable RAM power save
        self.write_cmd(0xF0)
        self.write_data(0x01)
        self.write_cmd(0xF6)
        self.write_data(0x00)

        # Display Inversion OFF
        self.write_cmd(0x20)
        time.sleep_ms(10)

        # Display ON
        self.write_cmd(0x29)
        time.sleep_ms(100)

    def show(self):
        """Flush the framebuf to the LCD."""
        # 128x128 panel window on ST7735 RAM (col: 1..128, row: 2..130)
        self.write_cmd(0x2A)
        self.write_data([0x00, 0x01, 0x00, 0x80])
        self.write_cmd(0x2B)
        self.write_data([0x00, 0x02, 0x00, 0x82])
        self.write_cmd(0x2C)

        self.dc.value(1)
        self.cs.value(0)
        self.spi.write(self.buffer)
        self.cs.value(1)

    def read_keys(self):
        """Return dict of button states: True if pressed, False if released."""
        return {
            "KEY0": False,  # Physically broken, permanently disabled
            "KEY1": self.key1.value() == 0,
            "KEY2": self.key2.value() == 0,
            "KEY3": self.key3.value() == 0,
        }
