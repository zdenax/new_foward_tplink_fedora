#!/usr/bin/env python3
import subprocess, json, os, re, time, base64
from pathlib import Path
from flask import Flask, render_template, jsonify, request
import urllib.request, urllib.error

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

try:
    from config.local import AP_IP, AP_ADMIN_USER, AP_ADMIN_PASS  # type: ignore
except ImportError:
    try:
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location("config_local",
            Path(__file__).parent / "config.local.py")
        cfg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cfg)
        AP_IP = cfg.AP_IP
        AP_ADMIN_USER = cfg.AP_ADMIN_USER
        AP_ADMIN_PASS = cfg.AP_ADMIN_PASS
    except Exception:
        pass


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


def ap_auth_header():
    cred = base64.b64encode(f"{AP_ADMIN_USER}:{AP_ADMIN_PASS}".encode()).decode()
    return {"Cookie": f"Authorization=Basic {cred}", "Referer": f"http://{AP_IP}/"}


def ap_cgi(action_type, oid, stack, attrs):
    """Zavolá TP-Link CGI API. action_type: 1=GET, 2=SET, 5=GL."""
    attr_str = "\r\n".join(attrs) + "\r\n"
    count = len(attrs)
    data = f"[{oid}#{stack}#0,0,0,0,0,0]0,{count}\r\n{attr_str}".encode()
    url = f"http://{AP_IP}/cgi?{action_type}="
    req = urllib.request.Request(url, data=data, headers=ap_auth_header(), method="POST")
    req.add_header("Content-Type", "text/plain")
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.read().decode(errors="ignore")


def ap_get_wlan():
    """Vrátí SSID a stack prvního WLAN."""
    resp = ap_cgi(5, "LAN_WLAN", "0,0,0,0,0,0", ["name", "SSID", "Enable"])
    stack_m = re.search(r"\[(\d+,\d+,\d+,\d+,\d+,\d+)\]", resp)
    ssid_m = re.search(r"SSID=(.+)", resp)
    stack = stack_m.group(1) if stack_m else "1,1,0,0,0,0"
    ssid = ssid_m.group(1).strip() if ssid_m else "—"
    return stack, ssid


def get_ap_config():
    try:
        req = urllib.request.Request(f"http://{AP_IP}/", headers=ap_auth_header())
        with urllib.request.urlopen(req, timeout=2) as r:
            html = r.read().decode(errors="ignore")
        m = re.search(r'modelName="([^"]+)"', html)
        model = m.group(1) if m else "TP-Link AP"
        _, ssid = ap_get_wlan()
        return {"model": model, "ssid": ssid, "reachable": True}
    except Exception:
        return {"model": "—", "ssid": "—", "reachable": False}


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
    data = request.get_json()
    ssid = data.get("ssid", "").strip()
    password = data.get("password", "")
    if not ssid:
        return jsonify({"ok": False, "error": "SSID nesmí být prázdné"})
    if password and len(password) < 8:
        return jsonify({"ok": False, "error": "Heslo musí mít min. 8 znaků"})
    try:
        stack, _ = ap_get_wlan()
        # SET SSID
        ap_cgi(2, "LAN_WLAN", stack, [f"SSID={ssid}"])
        # SET heslo (WPA2-PSK AES)
        if password:
            ap_cgi(2, "LAN_WLAN", stack, [
                "BeaconType=11i",
                "IEEE11iAuthenticationMode=PSKAuthentication",
                "IEEE11iEncryptionModes=AESEncryption",
                f"X_TP_PreSharedKey={password}",
                "X_TP_GroupKeyUpdateInterval=0",
            ])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=False)
