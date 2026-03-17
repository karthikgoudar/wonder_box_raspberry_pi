# stubs/urequests.py — MicroPython urequests → CPython requests
import requests as _req

class _Response:
    def __init__(self, r):
        self._r = r
        self.status_code = r.status_code
        self.text = r.text

    def close(self):
        self._r.close()

def post(url, headers=None, data=None, json=None):
    r = _req.post(url, headers=headers, data=data, json=json, timeout=60)
    return _Response(r)

def get(url, headers=None):
    r = _req.get(url, headers=headers, timeout=30)
    return _Response(r)
