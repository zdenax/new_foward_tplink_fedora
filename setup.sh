#!/bin/bash
# Internet Forwarding Setup — Fedora
# Internet z WAN_IF přes LAN_IF do AP sítě

set -e

# === Konfigurace rozhraní ===
WAN_IF="wlp2s0"       # internet (zabudovaný WiFi)
LAN_IF="enp4s0"       # kabel do AP
LAN_IP="192.168.100.50"  # statická IP Fedory v AP síti

echo "=== Internet Forwarding Setup (Fedora) ==="
echo "    WAN: $WAN_IF  →  LAN: $LAN_IF"

if [ "$EUID" -ne 0 ]; then
    echo "Spusť jako root: sudo ./setup.sh"
    exit 1
fi

# 1. Kontrola rozhraní + statická IP na LAN
echo ""
echo "1. Kontrola sítě..."
ip addr show "$LAN_IF" > /dev/null 2>&1 || { echo "Chyba: $LAN_IF nenalezeno"; exit 1; }
ip addr show "$WAN_IF" > /dev/null 2>&1 || { echo "Chyba: $WAN_IF nenalezeno"; exit 1; }

# Nastav statickou IP na LAN (přes nmcli, permanentně)
echo "   Nastavuji statickou IP $LAN_IP na $LAN_IF..."
if nmcli con show ap-lan &>/dev/null; then
    nmcli con modify ap-lan ip4 "$LAN_IP/24" ipv4.method manual
else
    nmcli con add type ethernet ifname "$LAN_IF" con-name ap-lan ip4 "$LAN_IP/24" ipv4.method manual
fi
nmcli con up ap-lan > /dev/null

echo "   $LAN_IF: $(ip addr show "$LAN_IF" | grep "inet " | awk '{print $2}' || echo 'bez IP')"
echo "   $WAN_IF: $(ip addr show "$WAN_IF" | grep "inet " | awk '{print $2}' || echo 'bez IP')"

# 2. IP Forwarding
echo ""
echo "2. Povolení IP Forwarding..."
sysctl -w net.ipv4.ip_forward=1
sysctl -w net.ipv4.conf.all.rp_filter=0

# 3. NAT — firewalld (Fedora default)
echo ""
echo "3. Nastavení NAT (firewalld)..."

if systemctl is-active --quiet firewalld; then
    # Přiřaď rozhraní do zón
    firewall-cmd --zone=external --change-interface="$WAN_IF" --permanent
    firewall-cmd --zone=trusted  --change-interface="$LAN_IF" --permanent
    # Masquerade na WAN
    firewall-cmd --zone=external --add-masquerade --permanent
    firewall-cmd --reload
    echo "   ✓ firewalld nakonfigurován"
else
    # Fallback: raw iptables
    echo "   firewalld neběží, používám iptables..."
    iptables -t nat -D POSTROUTING -o "$WAN_IF" -j MASQUERADE 2>/dev/null || true
    iptables -t nat -A POSTROUTING -o "$WAN_IF" -j MASQUERADE
    iptables -A FORWARD -i "$LAN_IF" -o "$WAN_IF" -j ACCEPT
    iptables -A FORWARD -i "$WAN_IF" -o "$LAN_IF" -m state --state RELATED,ESTABLISHED -j ACCEPT
    echo "   ✓ iptables nastaveny"
fi

# 4. DNS (dnsmasq)
echo ""
echo "4. Nastavení DNS (dnsmasq)..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$SCRIPT_DIR/dnsmasq.conf" /etc/dnsmasq.conf

# Fedora: dnsmasq může konfliktovat s systemd-resolved na portu 53
if systemctl is-active --quiet systemd-resolved; then
    echo "   Zastavuji systemd-resolved (konflikt port 53)..."
    systemctl stop systemd-resolved
    systemctl disable systemd-resolved
fi

# Ujisti se, že firewall povoluje DNS
if systemctl is-active --quiet firewalld; then
    firewall-cmd --zone=trusted --add-service=dns --permanent 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
fi

systemctl enable dnsmasq
systemctl restart dnsmasq && echo "   ✓ dnsmasq spuštěn" || echo "   ✗ dnsmasq selhal"

# 4b. Docker override — Docker má FORWARD policy DROP, běží před firewalld
# DOCKER-USER je správné místo pro vlastní pravidla
echo ""
echo "4b. Docker FORWARD override..."
if iptables -L DOCKER-USER &>/dev/null 2>&1; then
    iptables -D DOCKER-USER -i "$LAN_IF" -o "$WAN_IF" -j ACCEPT 2>/dev/null || true
    iptables -D DOCKER-USER -i "$WAN_IF" -o "$LAN_IF" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
    iptables -I DOCKER-USER -i "$LAN_IF" -o "$WAN_IF" -j ACCEPT
    iptables -I DOCKER-USER -i "$WAN_IF" -o "$LAN_IF" -m state --state RELATED,ESTABLISHED -j ACCEPT
    echo "   ✓ DOCKER-USER pravidla přidána"
else
    echo "   Docker neběží, přeskakuji"
fi

# 5. Verifikace
echo ""
echo "=== Verifikace ==="
echo "IP Forwarding: $(cat /proc/sys/net/ipv4/ip_forward)"
echo ""
if systemctl is-active --quiet firewalld; then
    echo "Masquerade (external zone):"
    firewall-cmd --zone=external --query-masquerade && echo "  ✓ aktivní" || echo "  ✗ neaktivní"
else
    echo "NAT pravidla:"
    iptables -t nat -L POSTROUTING -v | grep -A1 "Chain POSTROUTING"
fi

echo ""
echo "✓ Forwarding nastaven!"
echo ""
echo "Příští kroky:"
echo "1. Ověř AP gateway: měl by být IP $LAN_IF (192.168.100.50)"
echo "2. Test na Testeri: ping 8.8.8.8"
echo "3. Zastavení: sudo ./stop.sh"
