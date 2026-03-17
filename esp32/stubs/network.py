# stubs/network.py — MicroPython network → always "connected" on PC
STA_IF = 0
AP_IF  = 1

class WLAN:
    def __init__(self, mode):
        self._mode = mode

    def active(self, v=None):
        return True

    def isconnected(self):
        return True  # PC is always connected

    def connect(self, ssid, password):
        print("[network STUB] WiFi connect — skipped on PC (using host network)")

    def ifconfig(self):
        return ("127.0.0.1", "255.255.255.0", "127.0.0.1", "8.8.8.8")
