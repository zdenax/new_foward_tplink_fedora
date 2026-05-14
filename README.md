# Internet Forwarding Lab — Fedora

Nastavení internet forwardingu z Fedora Linuxu přes TP-Link AP do testovacího PC.

## Fyzická Topologie

```
┌─────────────────────────────────────────────────────┐
│ Fedora Linux (Notebook)                             │
│  ├─ wlp2s0: internet (WAN, zabudovaný WiFi)        │
│  └─ enp4s0: 192.168.100.50/24 (připojeno na AP LAN)│
└─────────────────────────────────────────────────────┘
              │
              │ (CAT5 kabel)
              │
┌─────────────────────────────────────────────────────┐
│ TP-Link AP                                          │
│  ├─ LAN: 192.168.100.1/24                          │
│  ├─ DHCP: 192.168.100.10-100                       │
│  └─ Gateway/DNS: 192.168.100.50 (Fedora)           │
└─────────────────────────────────────────────────────┘
              │
              │ (WiFi)
              │
┌─────────────────────────────────────────────────────┐
│ Tester PC                                           │
│  └─ WiFi: 192.168.100.X (z DHCP AP)                │
└─────────────────────────────────────────────────────┘
```

## Datový Tok

```
Tester → WiFi → AP (192.168.100.1) → Fedora enp4s0 → IP Forward → Fedora wlp2s0 → Internet
```

## Konfigurace rozhraní

V `setup.sh` a `stop.sh` nahoře:

```bash
WAN_IF="wlp2s0"   # internet (zabudovaný WiFi)
LAN_IF="enp4s0"   # kabel do AP
```

Změň podle `ip link show` pokud máš jiné názvy.

## Instalace

### 1. Příprava Fedory

```bash
# Nastav statickou IP na enp4s0 (LAN do AP)
sudo ip addr add 192.168.100.50/24 dev enp4s0
sudo ip link set enp4s0 up

# nebo permanentně přes nmcli:
sudo nmcli con add type ethernet ifname enp4s0 ip4 192.168.100.50/24
```

### 2. Spuštění Forwardingu

```bash
cd ~/new_foward_tplink_fedora
sudo ./setup.sh
```

Skript automaticky detekuje firewalld (Fedora default) a použije `firewall-cmd`. Pokud firewalld neběží, fallback na raw iptables.

### 3. Ověření na Fedoře

```bash
# IP forwarding zapnutý?
cat /proc/sys/net/ipv4/ip_forward
# Mělo by být: 1

# NAT pravidla (firewalld)?
sudo firewall-cmd --zone=external --query-masquerade

# nebo raw iptables:
sudo iptables -t nat -L POSTROUTING -v
sudo iptables -L FORWARD -v
```

### 4. Konfigurace AP (Web Admin)

Vstup do AP webového rozhraní (http://192.168.100.1):

- **Network → LAN:**
  - IP: 192.168.100.1
  - Netmask: 255.255.255.0

- **Network → DHCP Server:**
  - Enable: ON
  - Start IP: 192.168.100.10
  - End IP: 192.168.100.100
  - Gateway: **192.168.100.50** (Fedora)
  - DNS 1: **192.168.100.50** (Fedora)
  - DNS 2: 8.8.8.8 (záloha)

- **WLAN → Basic:**
  - SSID: (tvůj network)
  - Security: WPA2 (nebo tvůj výběr)

### 5. Test na Testeri

```bash
ip route           # Mělo by mít gateway 192.168.100.1 (AP)
ping 8.8.8.8      # Test internetu
curl -I google.com # Test HTTP
```

## Příkazy Diagnostiky

```bash
# Na Fedoře:
netstat -tlnp                   # Otevřené porty
sudo tcpdump -i enp4s0 -n       # Sledovat LAN provoz
sudo tcpdump -i wlp2s0 -n       # Sledovat WAN provoz
sudo firewall-cmd --list-all --zone=external

# Na Testeri:
traceroute 8.8.8.8              # Cesta k internetu
nslookup google.com             # DNS test
iperf3 -c 192.168.100.50        # Bandwidth test
```

## Zastavení Forwardingu

```bash
sudo ./stop.sh
```

## Troubleshooting

### Tester nemá internet
1. Kontrola AP gateway: měl by být 192.168.100.50
2. `ping 192.168.100.1` z Testera (AP)
3. `ping 192.168.100.50` z Testera (Fedora)
4. `cat /proc/sys/net/ipv4/ip_forward` — musí být 1

### AP nemá internet
1. `ping 8.8.8.8` z Fedory na wlp2s0
2. `sudo firewall-cmd --zone=external --query-masquerade`
3. `cat /proc/sys/net/ipv4/conf/all/rp_filter` — musí být 0

### dnsmasq nespustí (port 53 obsazený)
```bash
# systemd-resolved konfliktuje — setup.sh ho zastaví automaticky
# manuálně:
sudo systemctl stop systemd-resolved
sudo systemctl disable systemd-resolved
sudo systemctl restart dnsmasq
```

### firewalld blokuje provoz
```bash
sudo firewall-cmd --zone=trusted --list-all
sudo firewall-cmd --zone=external --list-all
```

## Persistence (Systemd Service)

```bash
sudo cp net-forwarding.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable net-forwarding
sudo systemctl start net-forwarding
```

## Soubory

- `setup.sh` — nastavení forwardingu (firewalld + fallback iptables)
- `stop.sh` — zastavení forwardingu
- `dnsmasq.conf` — DNS konfigurace
- `net-forwarding.service` — systemd service
- `README.md` — tato dokumentace

---
vault: [[Vault/School/ZPS]]
