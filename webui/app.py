#!/usr/bin/env python3
import subprocess, json, os, re, time
from pathlib import Path
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

SCRIPT_DIR = Path(__file__).parent.parent
SETUP_SCRIPT = SCRIPT_DIR / "setup.sh"
STOP_SCRIPT  = SCRIPT_DIR / "stop.sh"
DNSMASQ_LEASES = Path("/var/lib/dnsmasq/dnsmasq.leases")
AP_IP = "192.168.100.2"
AP_ADMIN_USER = "admin"
AP_ADMIN_PASS = "admin"  # změň dle AP

WAN_IF = "wlp2s0"
LAN_IF = "enp4s0"


def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return ""


def forwarding_active():
    return run("cat /proc/sys/net/ipv4/ip_forward") == "1"


def get_iface_stats(iface):
    try:
        with open(f"/sys/class/net/{iface}/statistics/rx_bytes") as f:
            rx = int(f.read())
        with open(f"/sys/class/net/{iface}/statistics/tx_bytes") as f:
            tx = int(f.read())
        return rx, tx
    except Exception:
        return 0, 0


def fmt_bytes(b):
    for unit in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def get_iface_ip(iface):
    out = run(f"ip addr show {iface}")
    m = re.search(r"inet (\S+)", out)
    return m.group(1) if m else "—"


def get_iface_state(iface):
    state = run(f"cat /sys/class/net/{iface}/operstate 2>/dev/null")
    return state or "unknown"


def get_dhcp_leases():
    leases = []
    if DNSMASQ_LEASES.exists():
        for line in DNSMASQ_LEASES.read_text().splitlines():
            parts = line.split()
            if len(parts) >= 4:
                exp, mac, ip, name = parts[0], parts[1], parts[2], parts[3]
                exp_str = "∞" if exp == "0" else time.strftime("%H:%M:%S", time.localtime(int(exp)))
                leases.append({"ip": ip, "mac": mac, "name": name if name != "*" else "—", "expires": exp_str})
    return leases


def get_ap_config():
    """Pokus o čtení konfigurace AP přes HTTP. Model-specific — placeholder."""
    try:
        import urllib.request
        r = urllib.request.urlopen(f"http://{AP_IP}", timeout=2)
        html = r.read().decode(errors="ignore")
        # Detekuj model z HTML
        m = re.search(r"(TL-\w+|Archer \w+)", html, re.IGNORECASE)
        model = m.group(1) if m else "TP-Link AP"
        return {"model": model, "reachable": True}
    except Exception:
        return {"model": "—", "reachable": False}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    wan_rx, wan_tx = get_iface_stats(WAN_IF)
    lan_rx, lan_tx = get_iface_stats(LAN_IF)
    return jsonify({
        "forwarding": forwarding_active(),
        "wan": {
            "iface": WAN_IF,
            "ip": get_iface_ip(WAN_IF),
            "state": get_iface_state(WAN_IF),
            "rx": fmt_bytes(wan_rx),
            "tx": fmt_bytes(wan_tx),
        },
        "lan": {
            "iface": LAN_IF,
            "ip": get_iface_ip(LAN_IF),
            "state": get_iface_state(LAN_IF),
            "rx": fmt_bytes(lan_rx),
            "tx": fmt_bytes(lan_tx),
        },
        "clients": get_dhcp_leases(),
        "ap": get_ap_config(),
    })


@app.route("/api/start", methods=["POST"])
def api_start():
    result = subprocess.run(["sudo", str(SETUP_SCRIPT)], capture_output=True, text=True)
    ok = result.returncode == 0
    return jsonify({"ok": ok, "output": result.stdout + result.stderr})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    result = subprocess.run(["sudo", str(STOP_SCRIPT)], capture_output=True, text=True)
    ok = result.returncode == 0
    return jsonify({"ok": ok, "output": result.stdout + result.stderr})


@app.route("/api/ap/wifi", methods=["POST"])
def api_ap_wifi():
    """Změna SSID a hesla — implementace závisí na modelu AP."""
    data = request.get_json()
    ssid = data.get("ssid", "")
    password = data.get("password", "")
    if not ssid:
        return jsonify({"ok": False, "error": "SSID nesmí být prázdné"})
    # TODO: implementovat dle modelu AP (viz README)
    return jsonify({"ok": False, "error": "AP model ještě nepodporován — přidej model do app.py"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=False)
