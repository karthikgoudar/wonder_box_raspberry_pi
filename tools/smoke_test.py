"""
Command-line check of the Pi's backend path, with no microphone, screen or button.

    python tools/smoke_test.py recordings/sample.wav            # upload + download
    python tools/smoke_test.py recordings/sample.wav --print    # also print the strips

Reads BACKEND_URL, DEVICE_TOKEN and CHILD_ID from .env. With --print it uses
PrinterService (set PRINTER_SIMULATE=1 to skip the real printer).
Saves the returned picture to outputs/smoke_test.png.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from services.backend_client import BackendClient, BackendError  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wav")
    ap.add_argument("--print", action="store_true", dest="do_print")
    a = ap.parse_args()

    c = BackendClient()
    print(f"backend: {c.base_url}")
    print(f"health:  {'ok' if c.health() else 'NOT REACHABLE'}")
    if not c.health():
        return 1

    t0 = time.time()
    try:
        r = c.submit_sticker(a.wav)
    except BackendError as e:
        print(f"submit FAILED: {e} (status={e.status_code} code={e.code})")
        return 2
    print(f"submit:  ok in {time.time() - t0:.1f}s, text={r.text!r}")

    png = c.download(r.image_url)
    os.makedirs("outputs", exist_ok=True)
    with open("outputs/smoke_test.png", "wb") as f:
        f.write(png)
    print(f"image:   {len(png)} bytes -> outputs/smoke_test.png")

    strips = c.download_print_strips(r.print_url)
    print(f"strips:  {len(strips)} x 1160 bytes, headers ok")

    if a.do_print:
        from services.printer_service import PrinterService

        p = PrinterService()
        p.start_print_strips(strips)
        p._thread.join(60)
        if p.has_failed():
            print(f"print FAILED: {p.get_error()}")
            return 3
        print("print:   done" if p.is_done() else "print:   still running after 60s")
    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
