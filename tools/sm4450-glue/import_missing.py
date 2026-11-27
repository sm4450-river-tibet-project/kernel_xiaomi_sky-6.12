#!/usr/bin/env python3
"""Complete the CLO soc-repo overlay import.

kernel/xiaomi/sky was built as ACK android16-6.12 + CLO's qcom 6.12 overlay, but
the import dropped some overlay files (e.g. include/dt-bindings/arm/msm/
qcom_dma_heap_dt_constants.h, which ravelin-dma-heaps.dtsi includes).  This walks
the CLO tree for the release ref and fetches anything our repo lacks.

  python3 import_missing.py            # report only
  python3 import_missing.py --apply    # fetch the missing files
"""
import json
import os
import subprocess
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

BASE = "https://git.codelinaro.org/api/v4/projects/60268/repository"
REF = "kernel.lnx.6.12.r70-rel"
SRC = os.path.expanduser("~/los/kernel/xiaomi/sky")
APPLY = "--apply" in sys.argv


def curl(url, binary=False):
    r = subprocess.run(["curl", "-sS", "--max-time", "120", url], capture_output=True)
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def clo_paths():
    out, page = [], 1
    while True:
        d = json.loads(curl("%s/tree?ref=%s&recursive=true&per_page=100&page=%d"
                            % (BASE, REF, page)))
        if not d:
            break
        out += [e["path"] for e in d if e.get("type") == "blob"]
        if len(d) < 100:
            break
        page += 1
    return out


def fetch(path):
    q = urllib.parse.quote(path, safe="")
    blob = curl("%s/files/%s/raw?ref=%s" % (BASE, q, REF), binary=True)
    if not blob:
        return path, "EMPTY"
    dest = os.path.join(SRC, path)
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    with open(dest, "wb") as f:
        f.write(blob)
    return path, len(blob)


def main():
    paths = clo_paths()
    print("CLO overlay files: %d" % len(paths))
    tracked = set(subprocess.run(["git", "-C", SRC, "ls-files"],
                                 capture_output=True, text=True).stdout.split("\n"))
    missing = [p for p in paths if p not in tracked
               and not os.path.exists(os.path.join(SRC, p))]
    print("missing from our repo: %d" % len(missing))
    for p in missing[:25]:
        print("  " + p)
    if len(missing) > 25:
        print("  ... %d more" % (len(missing) - 25))
    if not APPLY or not missing:
        return
    ok = bad = 0
    with ThreadPoolExecutor(max_workers=16) as ex:
        for path, res in ex.map(fetch, missing):
            if res == "EMPTY":
                bad += 1
                print("  FAILED %s" % path)
            else:
                ok += 1
    print("fetched %d, failed %d" % (ok, bad))


if __name__ == "__main__":
    main()
