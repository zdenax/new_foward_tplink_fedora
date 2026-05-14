#!/bin/bash
# Zastavení Internet Forwardingu — Fedora

set -e

WAN_IF="wlp2s0"
LAN_IF="enp4s0"

if [ "$EUID" -ne 0 ]; then
    echo "Spusť jako root: sudo ./stop.sh"
    exit 1
fi

echo "=== Zastavení Internet Forwardingu ==="

echo "1. Vypnutí IP Forwarding..."
sysctl -w net.ipv4.ip_forward=0

echo "2. Vyčištění NAT pravidel..."
if systemctl is-active --quiet firewalld; then
    firewall-cmd --zone=external --remove-masquerade --permanent 2>/dev/null || true
    firewall-cmd --direct --remove-rule ipv4 filter FORWARD 0 -i "$LAN_IF" -o "$WAN_IF" -j ACCEPT 2>/dev/null || true
    firewall-cmd --direct --remove-rule ipv4 filter FORWARD 0 -i "$WAN_IF" -o "$LAN_IF" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
    firewall-cmd --reload
    echo "   ✓ firewalld vyčištěn"
else
    iptables -t nat -F POSTROUTING
    iptables -F FORWARD
    echo "   ✓ iptables vyčištěny"
fi

echo "3. Zastavení dnsmasq..."
systemctl stop dnsmasq || true

echo "4. Vrácení $LAN_IF na DHCP..."
nmcli con delete ap-lan 2>/dev/null || true

echo "✓ Internet Forwarding zastaveno"
