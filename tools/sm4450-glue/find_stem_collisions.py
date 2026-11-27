#!/usr/bin/env python3
"""Find vendor prebuilt stems that collide with source-built HAL interfaces.

A `stem:` restores the original `@`-bearing filename so DT_NEEDED lookups work.
But when the platform also builds that same HAL from source (hidl_interface /
aidl_interface under hardware/ or vendor/qcom/), both land on the same install
path and soong aborts with `multiple rules generate <path>`.

Reports the collision list; pair with fix_pkg_conflicts.py to disable them.
Run from the vendor repo root.
"""
import glob
import os
import re
import sys

BP = "Android.bp"
ROOT = "../../.."  # repo root, relative to the vendor repo (vendor/xiaomi/<name>)
SRC_GLOBS = [
    "hardware/**/Android.bp",
    "vendor/qcom/**/Android.bp",
    "device/**/Android.bp",
]
IFACE_RE = re.compile(r"(?:hidl_interface|aidl_interface)\s*\{")
NAME_RE = re.compile(r'\bname:\s*"([^"]+)"')


def blocks(text, start_re):
    """Yield the body of each `<type> { ... }` block whose type matches start_re."""
    for m in start_re.finditer(text):
        i = text.find("{", m.start())
        if i < 0:
            continue
        depth = 0
        j = i
        while j < len(text):
            c = text[j]
            if c == '"':
                j += 1
                while j < len(text) and text[j] != '"':
                    if text[j] == "\\":
                        j += 1
                    j += 1
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    yield text[i:j]
                    break
            j += 1


def main():
    t = open(BP, encoding="utf-8").read()
    stems = set(re.findall(r'\bstem:\s*"([^"]+)"', t))
    print("stems in %s: %d" % (BP, len(stems)))

    src = set()
    files = 0
    for pat in SRC_GLOBS:
        for bp in glob.glob(os.path.join(ROOT, pat), recursive=True):
            if "/out/" in bp.replace("\\", "/"):
                continue
            try:
                s = open(bp, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            files += 1
            for body in blocks(s, IFACE_RE):
                m = NAME_RE.search(body)
                if m:
                    src.add(m.group(1))
    print("scanned %d Android.bp, %d source-built interfaces" % (files, len(src)))

    hit = sorted(stems & src)
    print("COLLIDING stems: %d" % len(hit))
    for h in hit:
        print(h)

    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            for h in hit:
                f.write(h + ".so\n")
        print("wrote %d names to %s" % (len(hit), sys.argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
