# Pico Project AI Agent Guidelines & Engineering Rules

## 1. Hardware Constraints (RP2040 + Waveshare 1.44" LCD)
- **Target Microcontroller**: Raspberry Pi Pico W (RP2040 @ 133 MHz, 264 KB SRAM, CYW43439 Wi-Fi).
- **Display**: Waveshare Pico-LCD-1.44 (ST7735S, 128×128 pixels, 16-bit RGB565 little-endian byte-swapped).
- **Physical Key Navigation**:
  - `KEY3` (GP3, Top): Move / Up / Next / Cycle.
  - `KEY2` (GP2, Middle): Select / Action / Enter Detail / Re-probe.
  - `KEY1` (GP17, Bottom): Back / Exit to Parent Menu.
  - `KEY0` (GP15): **Physically broken**. Hardcoded to `False`. NEVER use or wait on KEY0.

## 2. UI & Aesthetics Rules
- **No Key Map / Hint Text**: NEVER display button hints (`K3:NEXT`, `K2:SELECT`, `K1:MENU`, `Press K2...`, or footers) anywhere in the UI.
- **Ultra-Minimalist Horizontal-Line Architecture (Zero Boxes)**:
  - **No Boxes / Enclosing Cards**: NEVER use bounding card boxes (`ui.card`, `lcd.rect`) across any screen in the UI.
  - **Faded Pill Badges (Zero Border Boxes)**: Badges (`ui.badge`) render as borderless, subtle rounded pills with a soft, faded dark-tint background (`get_badge_colors`) and bright, high-contrast typography. NEVER draw hard bounding border boxes (`lcd.rect`) around badges (e.g. `dB` in Wi-Fi, `PORT 80`, `133MHz`, `PASS`).
  - **1px Horizontal Dividers**: Separate sections and rows using clean 1-pixel horizontal lines (`lcd.hline`) in `Theme.BORDER`.
  - **Main Menu**: 5-category list with horizontal lines separating each row (`DEV`, `PING`, `SITES`, `YT`, `WEB`), active row indicated by `>` cursor and highlighted accent line (`start_y = 23`, `row_h = 20`).
  - **Combined DEV Subsystem**: Like `SITES`, `DEV` features a dedicated Landing Page (View A) with selectable subpages (`CORE`, `NET`, `MEM`), where KEY2 enters the full detail view (View B) and KEY1 returns to the landing page.
  - **Detail Screens (DEV Subpages, Ping, Sites, YT, Web)**: Divided into clean sections by 1px horizontal lines on a unified dark canvas.
  - **Progress Bars**: Sleek track lines without outer border boxes.
- **Canvas Budget (128×128 px)**:
  - Header: `y = 0..18` (18 px).
  - Usable area: `y = 19..127` (109 px).
- **Typography & Anti-Smudge**:
  - High-density 6×8 font (`picoui.draw_text`, 21 chars/line) for all menus and lists.
  - 1-pixel crisp strokes only. Never use artificial double-strike bolding.
  - Use luminance contrast and subtle line accents for hierarchy.
- **Abbreviated Technical Vocabulary Rule (No Long Words)**:
  - On the 128×128 panel, NEVER use verbose labels or long words that waste spatial budget.
  - Use concise standard technical abbreviations across all labels, menus, and badges:
    - `Temperature` -> `Tmp` (e.g. `CORE TMP`)
    - `Device` -> `Dev`
    - `Network` -> `Net`
    - `Memory` -> `Mem`
    - `Allocated` -> `Alloc` (e.g. `Alloc: 42KB`)
    - `Connecting` -> `Conn...`
    - `Server` -> `Srv` (e.g. `WEB SRV`)
    - `Protocol` -> `Proto` (e.g. `Proto: ICMP`)
    - `Cloudflare` -> `CF` (e.g. `CF PING`, `1.1.1.1 (CF)`)
    - `YouTube` -> `YT` (e.g. `YT` menu item, `SUBS`, `VIDS`, `VIEWS`)
    - `Min / Max` -> Char-sized icons `↓` / `↑` (zero text labels)

## 3. Memory Management & Circular Buffer Rule
- **Bounded Buffers Only**: Any chart data, telemetry series, logs, or repeating job records **MUST be strictly bounded / circular with a fixed maximum size** (e.g. `len(history) <= 16`, `len(yt_history) <= 16`).
- **Pruning**: Always prune with FIFO `pop(0)` or circular ring buffers when appending new samples. Unbounded list growth will fragment MicroPython heap and cause OOM crashes.
- **Garbage Collection**: Run `gc.collect()` before and after heavy network operations (DNS lookup, HTTP socket reads, mbedTLS handshakes).

## 4. Internet Quality & Ping Architecture (`PING`)
- **Multi-Target Diagnostic**: Cycles 3 critical network checkpoints:
  - `CF` (Cloudflare `1.1.1.1` - Fast Anycast DNS)
  - `GOOG` (Google `8.8.8.8` - Global Backbone)
  - `GW` (Local Router Gateway via `wlan.ifconfig()[2]` - Wi-Fi Link Health)
- **Quality Grade Badges**: Faded pill badges (`GREAT` <30ms, `GOOD` <60ms, `FAIR` <120ms, `POOR` >=120ms, `LOSS`).
- **Telemetry Metrics**:
  - Hero latency in big numbers + `JIT: Xms` (consecutive packet variance).
  - Daily Min (`↓`) & Max (`↑`) arrows + Packet Loss percentage (`LOSS X%`).
  - 16-bar response time histogram chart (`ui.latency_chart`) plotting live latency pulses.
- **Controls & Live Telemetry**:
  - `KEY3`: Cycle target (`CF` ↔ `GOOG` ↔ `GW`).
  - `KEY2`: Instant re-probe.
  - `KEY1`: Return to main menu.
  - Auto-pings every 2.5s while active to continuously update the live chart.

## 5. Sites Monitor Architecture
- **View A (Overview)**: 2-column NOC list showing up to 16 websites simultaneously (8 rows × 2 columns), with vertical divider at `x = 63` and color-coded status dots (Green = UP, Red = DOWN, Yellow = WAIT).
- **View B (Site Detail)**: Ultra-minimalist single-site view with **zero boxes/cards**:
  - Section 1: Single-line website URL + port, followed by hero status (`UP`/`DOWN`), latency, and HTTP code.
  - 1px horizontal line divider (`y = 59`).
  - Section 2: Daily Min and Max values using char-sized 5×7 arrow icons (`↓` for Min, `↑` for Max) without `MIN:` or `MAX:` text labels.
  - 1px horizontal line divider (`y = 78`).
  - Section 3: 16-bar response time histogram chart with baseline axis and color-coded spikes.

## 5. YouTube Channel Tracker Architecture
- **API**: Official YouTube Data API v3 (`https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&...`) over TLS port 443 with RP2040 built-in `ssl.wrap_socket`.
- **Query Resolution**: Automatically supports Channel IDs (`id=UC...`) and handles (`forHandle=%40handle`).
- **Data Extracted**: Channel Title, Subscriber Count, View Count, Video Count.
- **Dedicated Screen (`YT`)**:
  - Section 1: Single-line channel title, hero subscriber count (`ui.draw_big`), `SUBS` badge, and video count (`VIDS`).
  - 1px horizontal line divider (`y = 54`).
  - Section 2: `48H VIEWS` total gain (`+XXX`), followed by daily Min & Max interval views with char-sized `↓` / `↑` arrow icons.
  - 1px horizontal line divider (`y = 80`).
  - Section 3: 48-Hour Views histogram bar chart (16 bounded bars, 3 hours per bar = 48h) with clean baseline axis at `y = 124` and color-coded spikes (`Theme.SUCCESS` emerald, `Theme.INFO` cyan, `Theme.WARNING` amber).
- **Persistence**: Persistently stored in `youtube.txt` (channel + key) and `yt_views.txt` (48-hour bounded view samples).
- **Web UI Management**: Live config form on port 80 (`http://<pico_ip>/`) to update channel handle/ID and API key on the fly without re-flashing.

## 6. Web Server & Persistence
- Non-blocking socket listener on Port 80 (`s.setblocking(False)`), integrated into the main loop without blocking UI rendering or button response.
- Post/Redirect/Get pattern (HTTP 303 to `/`) for all POST/GET mutations.
- Monitored sites persistently saved to `sites.txt` and YouTube config saved to `youtube.txt`.

## 7. Flashing & Deployment
- Automated deployment via `upload_to_pico.py` on `COM3` at 115200 baud over MicroPython Raw REPL.

## 8. 🧠 Note for Next AI: Deep Dive into `picoui.py`
Dear future AI agent, when you read or modify `picoui.py`, keep these crucial architecture details in mind:

1. **The RGB565 Little-Endian Byte-Swap Rule**:
   - The ST7735S driver and RP2040 FrameBuffer send 16-bit color words over SPI in little-endian byte order (`[low, high]`).
   - If you write standard big-endian RGB565 `((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)`, the colors will look inverted/swapped on the LCD panel.
   - **Always** use `picoui.color565(r, g, b)` (which byte-swaps `((c & 0xFF) << 8) | ((c >> 8) & 0xFF)`) or the pre-calibrated `Theme` tokens (`Theme.PRIMARY`, `Theme.SUCCESS`, `Theme.BG`, etc.).

2. **The 6×8 High-Density Font Engine**:
   - Standard MicroPython `framebuf.text()` is fixed at 8×8 pixels, allowing only 16 characters across 128 px.
   - `picoui.py` has a built-in raster font dictionary `FONT_6X8` (ASCII 32..126) with 5×7 glyphs + 1px spacing = **6×8 pixels** (allowing **21 characters per line**).
   - Core functions:
     - `draw_text(lcd, text, x, y, color, font="6x8")`
     - `draw_centered(lcd, text, y, color, font="6x8")`
     - `draw_right(lcd, text, y, color, margin=4, font="6x8")`
     - `draw_big(lcd, text, x, y, color)`: 2× scaled (16×16) hero metric numbers, accelerated via `@micropython.native`.
   - **NEVER use artificial double-strike bolding** (`(x+1, y)`). On a 128×128 panel, double-striking closes glyph loops (`B`, `8`, `e`) into unreadable ink blobs. Use luminance contrast and container elevation (`Theme.SURFACE_ALT`) instead.

3. **No Footer / No Button Hint Rule**:
   - `picoui.footer()` is retained only for backward compatibility. **DO NOT call it** in active dashboard screens.
   - The user strictly requires a clean, distraction-free UI with zero key-mapping text (`K3:NEXT`, `K2:SELECT`, `K1:MENU`, `Press K2...`). Removing the 14px footer reclaims valuable vertical space (`y = 19..127`).

4. **Component Palette**:
   - `card(lcd, x, y, w, h, is_active=False, border_color=None)`: Elevated container with border.
   - `badge(lcd, x, y, text, variant="info", align_right=False)`: Borderless pill badge with faded tint background and bright high-contrast font. Zero boxes.
   - `progress_bar(lcd, x, y, w, h, percent, variant="primary")`: Bounded progress indicator.
   - `latency_chart(lcd, x, y, w, h, values, min_val=None, max_val=None)`: 16-bar response histogram with baseline axis and color-coded latency spikes.
   - `alert_modal(lcd, title, message, variant="info", prompt=None)`: Centered modal dialog.

5. **Memory Safety Contract**:
   - When passing time-series or latency data into `latency_chart()` or UI widgets, **always ensure the data array is bounded / circular** (e.g. `history[-16:]`). MicroPython heap fragmentation happens easily on RP2040; never store unbounded lists.

