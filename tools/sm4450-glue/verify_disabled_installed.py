#!/usr/bin/env python3
"""Verify that disabled vendor prebuilts are still installed from source.

For every module we marked installable:false in Android.bp, work out the
installed filename, then look it up in out/soong/installs-lineage_sky.mk --
the list soong itself produced. If the filename is present, some module (the
source-built HAL interface, normally) still installs it, so disabling the
prebuilt is safe. If absent, disabling it silently removed the library from the
image and the build would boot-loop.

Read-only. Run from the vendor repo root.
"""
import os
import re
import sys

BP = "Android.bp"
INSTALLS = "../../../out/soong/installs-lineage_sky.mk"
NAME_RE = re.compile(r'\bname:\s*"([^"]+)"')
STEM_RE = re.compile(r'\bstem:\s*"([^"]+)"')
OFF_RE = re.compile(r"installable:\s*false")


def blocks(text):
    for m in re.finditer(r"^[A-Za-z_][A-Za-z0-9_]*\s*\{", text, re.M):
        i = text.find("{", m.start())
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
                    yield text[m.start():j + 1]
                    break
            j += 1


def main():
    text = open(BP, encoding="utf-8").read()
    dis = {}
    for body in blocks(text):
        if not OFF_RE.search(body):
            continue
        nm = NAME_RE.search(body)
        if not nm:
            continue
        is_bin = "cc_prebuilt_binary" in body[:64]
        st = STEM_RE.search(body)
        base = st.group(1) if st else nm.group(1)
        dis[nm.group(1)] = base if is_bin else base + ".so"

    if not os.path.exists(INSTALLS):
        print("MISSING %s -- run a build first" % INSTALLS)
        return 1
    inst = open(INSTALLS, encoding="utf-8", errors="replace").read()

    present, absent = [], []
    for mod, fn in sorted(dis.items()):
        # the installs file lists full paths, e.g. out/.../vendor/lib64/foo.so
        if re.search(r"/" + re.escape(fn) + r"(\s|$)", inst, re.M):
            present.append(mod)
        else:
            absent.append((mod, fn))

    print("disabled prebuilts:      %d" % len(dis))
    print("still installed (good):  %d" % len(present))
    print("NOT installed (BAD):     %d" % len(absent))
    for mod, fn in absent:
        print("   !! %-55s %s" % (mod, fn))
    return 0


if __name__ == "__main__":
    sys.exit(main())
