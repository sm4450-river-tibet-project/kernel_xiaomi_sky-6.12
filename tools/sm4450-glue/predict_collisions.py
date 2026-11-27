#!/usr/bin/env python3
"""Predict vendor-prebuilt vs source-built install-path collisions.

Scans the vendor Android.bp for every prebuilt we still install (i.e. not
already `installable: false`), works out the filename each one lands on, then
checks whether any other tree in the repo builds a module that lands on the same
path. Those are the pairs soong will report as `packaging conflict` or
`multiple rules generate`.

Read-only. Run from the vendor repo root.
"""
import glob
import os
import re
import sys

BP = "Android.bp"
ROOT = "../../.."
SRC_GLOBS = [
    "hardware/**/Android.bp",
    "vendor/qcom/**/Android.bp",
    "vendor/xiaomi/**/Android.bp",
    "device/**/Android.bp",
    "system/**/Android.bp",
    "frameworks/**/Android.bp",
    "external/**/Android.bp",
]
PREBUILT_RE = re.compile(r"cc_prebuilt_(?:library_shared|binary)\s*\{")
SOURCE_RE = re.compile(r"cc_library_shared\s*\{|cc_library\s*\{")
NAME_RE = re.compile(r'\bname:\s*"([^"]+)"')
STEM_RE = re.compile(r'\bstem:\s*"([^"]+)"')
OFF_RE = re.compile(r"installable:\s*false")


def blocks(text, start_re):
    """Yield the full text of each `<type> { ... }` block matching start_re."""
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
                    yield m.start(), text[m.start():j + 1]
                    break
            j += 1


def install_name(body, is_binary):
    stem = STEM_RE.search(body)
    name = NAME_RE.search(body)
    if not name:
        return None
    base = stem.group(1) if stem else name.group(1)
    return base if is_binary else base + ".so"


def collect(text, start_re, want_installed_only):
    out = {}
    for _, body in blocks(text, start_re):
        if want_installed_only and OFF_RE.search(body):
            continue
        name = NAME_RE.search(body)
        if not name:
            continue
        is_bin = "cc_prebuilt_binary" in body[:64]
        fn = install_name(body, is_bin)
        if fn:
            out.setdefault(fn, []).append(name.group(1))
    return out


def main():
    ours = collect(open(BP, encoding="utf-8").read(), PREBUILT_RE, True)
    print("prebuilts we still install: %d" % len(ours))

    src = {}
    scanned = 0
    for pat in SRC_GLOBS:
        for bp in glob.glob(os.path.join(ROOT, pat), recursive=True):
            if "/out/" in bp.replace("\\", "/"):
                continue
            try:
                s = open(bp, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            scanned += 1
            for fn, names in collect(s, SOURCE_RE, False).items():
                src.setdefault(fn, []).extend(names)
    print("scanned %d Android.bp, %d source-built lib filenames" % (scanned, len(src)))

    both = sorted(set(ours) & set(src))
    print("STILL COLLIDING: %d" % len(both))
    for x in both:
        print("  %s | ours=%s | src=%s" % (x, ours[x][:2], src[x][:2]))

    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            for x in both:
                f.write(x + "\n")
        print("wrote %d to %s" % (len(both), sys.argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
