#!/usr/bin/env python3
"""Resolve vendor-prebuilt vs source-built HAL collisions.

Background
----------
A stock-ROM vendor dump ships prebuilt copies of the HIDL/AIDL interface
libraries the platform also builds from source (hardware/interfaces,
vendor/qcom/opensource/interfaces, hardware/xiaomi/interfaces ...).  Restoring
the original `@`-bearing filename with `stem:` makes both modules install to the
same path, and soong aborts with either

    packaging conflict at lib64/foo@1.0.so
    multiple rules generate out/target/product/.../foo@1.0.so

The source-built copy is the correct one: it is ABI-matched to the rest of the
platform and it is what the HIDL manifest expects.  So mark the *prebuilt*
`installable: false` -- the module still exists, so every other prebuilt that
lists it in `shared_libs:` keeps resolving, but nothing is installed twice.

Usage (from the vendor repo root, the dir holding Android.bp):
    python3 fix_hal_collisions.py              # report only
    python3 fix_hal_collisions.py --apply      # write the changes
"""
import glob
import os
import re
import sys

BP = "Android.bp"
ROOT = "../../.."  # repo root, relative to vendor/xiaomi/<name>
SRC_GLOBS = [
    "hardware/**/Android.bp",
    "vendor/qcom/**/Android.bp",
    "device/**/Android.bp",
    "vendor/xiaomi/**/Android.bp",
]
IFACE_RE = re.compile(r"(?:hidl_interface|aidl_interface)\s*\{")
NAME_RE = re.compile(r'\bname:\s*"([^"]+)"')
STEM_RE = re.compile(r'\bstem:\s*"([^"]+)"')
PREBUILT_RE = re.compile(r"cc_prebuilt_(?:library_shared|binary)\s*\{")
ALREADY_RE = re.compile(r"^\s*installable:\s*false,", re.M)


def brace_blocks(text, start_re):
    """Yield (header_start, body) for each `<type> { ... }` block matching start_re."""
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


def source_interfaces():
    """Names of every HAL interface the platform builds from source."""
    names = set()
    for pat in SRC_GLOBS:
        for bp in glob.glob(os.path.join(ROOT, pat), recursive=True):
            if "/out/" in bp.replace("\\", "/"):
                continue
            try:
                s = open(bp, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            if "hidl_interface" not in s and "aidl_interface" not in s:
                continue
            for _, body in brace_blocks(s, IFACE_RE):
                m = NAME_RE.search(body)
                if m:
                    names.add(m.group(1))
    return names


def main(argv):
    apply = "--apply" in argv
    text = open(BP, encoding="utf-8").read()
    src = source_interfaces()
    print("source-built interfaces: %d" % len(src))

    edits, hit = [], []
    for start, body in brace_blocks(text, PREBUILT_RE):
        stem = STEM_RE.search(body)
        if not stem:
            continue
        if stem.group(1) not in src:
            continue
        if ALREADY_RE.search(body):
            continue
        nm = NAME_RE.search(body)
        brace = body.index("{")
        edits.append((start + brace + 1, "\n    installable: false,"))
        hit.append(nm.group(1) if nm else stem.group(1))

    print("%s installable:false -> %d"
          % ("would mark" if not apply else "marked", len(hit)))
    if not apply:
        for h in hit[:20]:
            print("   " + h)
        if len(hit) > 20:
            print("   ... %d more" % (len(hit) - 20))
        return 0

    for pos, new in sorted(edits, reverse=True):
        text = text[:pos] + new + text[pos:]
    open(BP, "w", encoding="utf-8").write(text)
    print("braces %d/%d" % (text.count("{"), text.count("}")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
