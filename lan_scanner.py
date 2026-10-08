# lan_scanner.py - Pico W LAN Device & Service Explorer
import socket
import time
import network
import gc
import picoui as ui
from picoui import Theme

LAN_FILE = "lan_devices.txt"
PORT_NAMES = {
    80: "HTTP",
    443: "SSL",
    22: "SSH",
    53: "DNS",
    445: "SMB",
    139: "NETB",
    5000: "NAS",
    1883: "MQTT",
    8123: "HASS",
    8080: "ALT",
    3000: "NODE",
    3389: "RDP",
}

class LanScanner:
    def __init__(self):
        self.devices = []
        self.candidate_queue = []
        self.scan_cursor = 0
        self.is_scanning = False
        self.subnet_base = "192.168.1."
        self.gw_ip = "192.168.1.1"
        self.my_ip = ""
        self.last_step_time = 0
        self.probing_ip = ""
        self.load_devices()

    def load_devices(self):
        self.devices = []
        try:
            with open(LAN_FILE, "r") as f:
                for line in f:
                    p = line.strip().split("|")
                    if len(p) >= 4:
                        ports = [int(x) for x in p[2].split(",") if x.isdigit()]
                        self.devices.append({
                            "ip": p[0],
                            "role": p[1],
                            "ports": ports,
                            "lat": int(p[3]),
                            "seen": int(time.time())
                        })
                        if len(self.devices) >= 16:
                            break
        except Exception:
            pass

    def save_devices(self):
        try:
            with open(LAN_FILE, "w") as f:
                for d in self.devices[:16]:
                    ports_str = ",".join(str(p) for p in d.get("ports", []))
                    f.write(f"{d['ip']}|{d['role']}|{ports_str}|{d.get('lat', 10)}\n")
        except Exception:
            pass

    def update_network_info(self):
        try:
            w = network.WLAN(network.STA_IF)
            if w.isconnected():
                cfg = w.ifconfig()
                self.my_ip, self.gw_ip = cfg[0], cfg[2]
                self.subnet_base = ".".join(self.my_ip.split(".")[:3]) + "."
        except Exception:
            pass

    def start_scan(self, full=False):
        self.update_network_info()
        q = [1]
        try:
            my_last = int(self.my_ip.split(".")[-1])
            if my_last not in q:
                q.append(my_last)
        except Exception:
            pass
        # Priority 1: Common static & DHCP pool (2..64)
        q.extend([o for o in range(2, 65) if o not in q])
        # Priority 2: Higher DHCP pool (65..120)
        q.extend([o for o in range(65, 120) if o not in q])
        # Priority 3: Extended pool (120..200)
        q.extend([o for o in range(120, 200) if o not in q])
        if full:
            q.extend([o for o in range(200, 255) if o not in q])
        self.candidate_queue = q
        self.scan_cursor = 0
        self.is_scanning = True

    def probe_port(self, host, port, timeout_ms=35):
        t0 = time.ticks_ms()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout_ms / 1000.0)
        try:
            s.connect((host, port))
            s.close()
            return "OPEN", max(1, time.ticks_diff(time.ticks_ms(), t0))
        except OSError as e:
            s.close()
            dt = max(1, time.ticks_diff(time.ticks_ms(), t0))
            return ("RST", dt) if (len(e.args) > 0 and e.args[0] in (111, 61)) else ("TIMEOUT", dt)
        except Exception:
            try:
                s.close()
            except Exception:
                pass
            return "TIMEOUT", 0

    def classify_device(self, ip, ports, is_rst=False):
        if ip == self.gw_ip:
            return "ROUTER"
        if ip == self.my_ip:
            return "THIS PICO"
        if 8123 in ports or 1883 in ports:
            return "HASS/IOT"
        if 53 in ports and (80 in ports or 443 in ports):
            return "ROUTER"
        if 53 in ports:
            return "DNS/PI"
        if 5000 in ports:
            return "NAS/SRV"
        if 445 in ports and 22 in ports:
            return "NAS/SRV"
        if 445 in ports or 139 in ports:
            return "PC/SMB"
        if 22 in ports:
            return "LINUX/PI"
        if 80 in ports or 443 in ports:
            return "WEB SRV"
        return "NODE" if is_rst else "HOST"

    def probe_host_full(self, ip):
        open_p, min_lat, is_act = [], 999, False
        # Phase 1: Core service ports
        for p in [80, 445, 22, 53, 5000]:
            st, dt = self.probe_port(ip, p, 40)
            if st == "OPEN":
                open_p.append(p)
                is_act = True
            elif st == "RST":
                is_act = True
            if st != "TIMEOUT" and dt < min_lat:
                min_lat = dt
        # Phase 2: Extended service ports if host is alive
        if is_act:
            for p in [443, 139, 8123, 1883, 3000, 8080]:
                st, dt = self.probe_port(ip, p, 35)
                if st == "OPEN":
                    open_p.append(p)
                    if dt < min_lat:
                        min_lat = dt
        return is_act, self.classify_device(ip, open_p, len(open_p) == 0), open_p, (min_lat if min_lat != 999 else 10)

    def step_scan(self):
        if not self.is_scanning or not self.candidate_queue:
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self.last_step_time) < 120:
            return
        self.last_step_time = now

        if self.scan_cursor >= len(self.candidate_queue):
            self.is_scanning = False
            self.probing_ip = ""
            self.save_devices()
            gc.collect()
            return

        target_ip = self.subnet_base + str(self.candidate_queue[self.scan_cursor])
        self.probing_ip = target_ip
        self.scan_cursor += 1

        is_act = False
        for p in [80, 445, 22]:
            st, dt = self.probe_port(target_ip, p, 35)
            if st in ("OPEN", "RST"):
                is_act = True
                break
            elif st == "TIMEOUT":
                # ARP timeout on non-existent IP -> skip further ports immediately
                break

        if is_act:
            _, role, ports, lat = self.probe_host_full(target_ip)
            match = next((d for d in self.devices if d["ip"] == target_ip), None)
            if match:
                match.update({"role": role, "ports": ports, "lat": lat, "seen": int(time.time())})
            else:
                self.devices.append({"ip": target_ip, "role": role, "ports": ports, "lat": lat, "seen": int(time.time())})
                if len(self.devices) > 16:
                    self.devices.pop(0)
            self.save_devices()
        gc.collect()

    def get_role_badge_info(self, role):
        m = {
            "ROUTER": ("RTR", "primary"),
            "THIS PICO": ("THIS", "success"),
            "HASS/IOT": ("IOT", "info"),
            "DNS/PI": ("DNS", "info"),
            "NAS/SRV": ("NAS", "warning"),
            "PC/SMB": ("PC", "warning"),
            "LINUX/PI": ("PI", "info"),
            "WEB SRV": ("WEB", "success"),
            "NODE": ("NODE", "default"),
            "HOST": ("HOST", "default"),
        }
        return m.get(role, ("DEV", "default"))

    def render_list_view(self, lcd, cur_idx):
        badge = f"SCAN .{self.probing_ip.split('.')[-1]}" if (self.is_scanning and self.probing_ip) else f"{len(self.devices)} DEV"
        ui.header(lcd, "LAN", right_badge=badge, accent=Theme.INFO)

        vis = 8
        tot = 1 + len(self.devices)
        cur = cur_idx % tot if tot > 0 else 0
        top = max(0, min(cur - 3, tot - vis))

        for i in range(vis):
            idx = top + i
            if idx >= tot:
                break
            cy = 20 + i * 13
            is_sel = (cur == idx)
            col = Theme.INFO if is_sel else Theme.TEXT

            if is_sel:
                ui.draw_text(lcd, ">", 2, cy + 2, Theme.INFO, font="6x8")

            if idx == 0:
                scan_lbl = "SCANNING..." if self.is_scanning else "[SCAN ALL LAN]"
                ui.draw_text(lcd, scan_lbl, 8, cy + 2, Theme.PRIMARY if is_sel else Theme.INFO, font="6x8")
                ui.badge(lcd, 126, cy + 1, "BUSY" if self.is_scanning else "SCAN", variant="warning" if self.is_scanning else "primary", align_right=True)
            else:
                d = self.devices[idx - 1]
                code, var = self.get_role_badge_info(d["role"])
                ui.draw_text(lcd, d["ip"], 8, cy + 2, col, font="6x8")
                ui.badge(lcd, 126, cy + 1, code, variant=var, align_right=True)

            lcd.hline(2, cy + 12, 124, Theme.INFO if is_sel else Theme.BORDER)

    def render_detail_view(self, lcd, cur_idx):
        if not self.devices:
            return self.render_list_view(lcd, 0)
        tot = len(self.devices)
        cur = cur_idx % tot
        d = self.devices[cur]
        code, var = self.get_role_badge_info(d["role"])
        ui.header(lcd, "DEV", right_badge=f"{cur + 1}/{tot}", accent=Theme.INFO)

        # Section 1: Host IP & Role
        ui.draw_text(lcd, "HOST", 4, 22, Theme.TEXT_MUTED, font="6x8")
        ui.badge(lcd, 124, 21, code, variant=var, align_right=True)
        ui.draw_text(lcd, d["ip"], 4, 33, Theme.PRIMARY, font="6x8")
        lat = d.get('lat', 1)
        lat_col = Theme.SUCCESS if lat < 30 else (Theme.WARNING if lat < 80 else Theme.DANGER)
        ui.draw_text(lcd, f"LATENCY: {lat}ms", 4, 44, lat_col, font="6x8")
        ui.draw_right(lcd, "ONLINE", 44, Theme.SUCCESS, margin=4, font="6x8")
        lcd.hline(4, 55, 120, Theme.BORDER)

        # Section 2: Services / Open Ports
        ports = d.get("ports", [])
        ui.draw_text(lcd, f"SERVICES ({len(ports)} OPEN)", 4, 60, Theme.TEXT_MUTED, font="6x8")
        if ports:
            x_pos, y_pos = 4, 72
            for p in ports[:6]:
                p_tag = f"{p}:{PORT_NAMES.get(p, str(p))}"
                pw = len(p_tag) * 6 + 6
                if x_pos + pw > 124:
                    x_pos, y_pos = 4, y_pos + 12
                    if y_pos > 85:
                        break
                ui.badge(lcd, x_pos, y_pos, p_tag, variant="info")
                x_pos += pw + 3
        else:
            ui.draw_text(lcd, "HOST RESPONSIVE (TCP RST)", 4, 73, Theme.TEXT_MUTED, font="6x8")

        lcd.hline(4, 96, 120, Theme.BORDER)

        # Section 3: Network info
        ui.draw_text(lcd, f"ROLE: {d['role']}", 4, 102, Theme.TEXT, font="6x8")
        ui.draw_text(lcd, f"NET: {self.subnet_base}0/24", 4, 114, Theme.TEXT_DARK, font="6x8")
        ui.draw_right(lcd, "TCP PROBED", 114, Theme.TEXT_DARK, margin=4, font="6x8")
