"""Retrieve AMFI NAV history for given scheme codes in 90-day windows (the portal rejects longer ranges).

Writes, under the output directory:
  * <name>_extract.txt     the original response lines for the requested scheme codes only
                           (header line + section/AMC lines kept as received)
  * <name>_chunks.csv      one row per AMFI response: URL, bytes, SHA256 (proves what was retrieved)

usage: python -I fetch_amfi_history.py OUT_DIR NAME AMC_ID FROM(YYYY-MM-DD) TO(YYYY-MM-DD) CODE [CODE...]
AMC_ID is AMFI's `mf` query parameter (64 = PPFAS, 9 = HDFC; confirmed from the responses).
"""
from __future__ import annotations

import csv
import hashlib
import ssl
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

URL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx?mf={mf}&tp=1&frmdt={frm}&todt={to}"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def fmt(d: date) -> str:
    return d.strftime("%d-%b-%Y")


def windows(start: date, end: date, days: int = 89):
    cur = start
    while cur <= end:
        nxt = min(cur + timedelta(days=days), end)
        yield cur, nxt
        cur = nxt + timedelta(days=1)


def main(argv):
    out, name, mf, frm, to = Path(argv[0]), argv[1], argv[2], date.fromisoformat(argv[3]), date.fromisoformat(argv[4])
    codes = set(argv[5:])
    out.mkdir(parents=True, exist_ok=True)
    ctx = ssl.create_default_context(cafile="/root/.ccr/ca-bundle.crt")
    kept: list[str] = []
    header = None
    chunks = []
    for a, b in windows(frm, to):
        u = URL.format(mf=mf, frm=fmt(a), to=fmt(b))
        for attempt in range(4):
            try:
                r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=120, context=ctx)
                data = r.read()
                if "text/plain" not in (r.headers.get("Content-Type") or ""):
                    raise RuntimeError("non-text response")
                break
            except Exception as e:   # retry with backoff
                print("retry", u, e, file=sys.stderr)
                data = None
        if data is None:
            chunks.append([u, 0, "FAILED"])
            continue
        chunks.append([u, len(data), hashlib.sha256(data).hexdigest()])
        for line in data.decode("utf-8", "replace").splitlines():
            if header is None and line.startswith("Scheme Code"):
                header = line
            if line.split(";", 1)[0] in codes:
                kept.append(line)
    # de-duplicate (windows do not overlap, but be safe) and sort by code then date
    def key(l):
        p = l.split(";")
        from datetime import datetime
        return p[0], datetime.strptime(p[-1], "%d-%b-%Y")
    uniq = sorted(set(kept), key=key)
    (out / f"{name}_extract.txt").write_text((header or "") + "\n" + "\n".join(uniq) + "\n", encoding="utf-8")
    with (out / f"{name}_chunks.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["URL", "Bytes", "SHA256"])
        w.writerows(chunks)
    print(f"{name}: {len(uniq)} lines, {len(chunks)} chunks, failed={sum(1 for c in chunks if c[2]=='FAILED')}")


if __name__ == "__main__":
    main(sys.argv[1:])
