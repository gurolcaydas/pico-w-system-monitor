# boot.py - Early Hardware Initialization for Pico W
# Allocates 32KB ST7735S FrameBuffer on pristine heap before main.py compiles
import gc
gc.collect()

from lcd1in44 import LCD_1inch44
lcd_instance = LCD_1inch44(brightness=85)
gc.collect()
