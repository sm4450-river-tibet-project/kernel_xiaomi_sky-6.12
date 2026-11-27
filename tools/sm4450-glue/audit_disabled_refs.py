#!/usr/bin/env python3
"""Find every PRODUCT_PACKAGES reference to an installable:false module.

The build fails at main.mk:1074 when a module listed in PRODUCT_PACKAGES no
longer exists. Rather than fixing one report at a time, scan all hand-written
and generated makefiles under device/ and vendor/ for package names that match
a disabled prebuilt.

Also reports modules that are disabled AND whose installed filename is not
provided by any other module (via out/soong/installs-*.mk), which is the
dangerous class: those libs vanish from the image.

Read-only. Run from the vendor repo root.
"""
import glob
import os
import re
import sys

BP = "Android.bp"
ROOT = "../../.."
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
    print("disabled modules: %d" % len(dis))

    # 1. references from .mk files
    hits = []
    for pat in ("device/**/*.mk", "vendor/**/*.mk"):
        for mk in glob.glob(os.path.join(ROOT, pat), recursive=True):
            if "/out/" in mk.replace("\\", "/"):
                continue
            try:
                lines = open(mk, encoding="utf-8", errors="replace").read().split("\n")
            except OSError:
                continue
            for i, ln in enumerate(lines, 1):
                tok = ln.strip().rstrip("\\").strip()
                if tok in dis:
                    hits.append((mk.replace("\\", "/"), i, tok))
    print("\n.mk references to disabled modules: %d" % len(hits))
    seen = set()
    for mk, i, tok in hits:
        rel = mk.split(ROOT.replace("\\", "/") + "/")[-1]
        key = (rel, tok)
        if key in seen:
            continue
        seen.add(key)
        print("   %s:%d  %s" % (rel, i, tok))

    # 2. disabled modules with no remaining installer
    if os.path.exists(INSTALLS):
        inst = open(INSTALLS, encoding="utf-8", errors="replace").read()
        orphan = [(m, f) for m, f in sorted(dis.items())
                  if not re.search(r"/" + re.escape(f) + r"(\s|$)", inst, re.M)]
        print("\ndisabled with NO remaining installer: %d" % len(orphan))
        for m, f in orphan:
            print("   !! %-55s %s" % (m, f))
    else:
        print("\n(no %s; run a build to check orphans)" % INSTALLS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
