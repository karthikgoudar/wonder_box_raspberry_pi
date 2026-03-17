# ============================================================
# boot.py — Runs automatically on every ESP32 power-on
# ============================================================
# Connects to WiFi and syncs the clock before main.py starts.

import network
import time
import ntptime
from config import WIFI_SSID, WIFI_PASSWORD

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return wlan

    print("[BOOT] Connecting to WiFi:", WIFI_SSID)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    timeout = 20  # seconds
    start = time.time()
    while not wlan.isconnected():
        if time.time() - start > timeout:
            print("[BOOT] WiFi connection FAILED")
            return None
        time.sleep(0.5)

    print("[BOOT] WiFi connected. IP:", wlan.ifconfig()[0])
    return wlan

wlan = connect_wifi()

if wlan and wlan.isconnected():
    try:
        ntptime.settime()
        print("[BOOT] NTP time synced")
    except Exception as e:
        print("[BOOT] NTP sync failed:", e)
