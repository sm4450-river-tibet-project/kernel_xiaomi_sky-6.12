#!/usr/bin/env python3
"""Keep sm4450-common-vendor.mk in sync with Android.bp installable:false flags.

A prebuilt marked `installable: false` no longer produces an install path, so it
also stops existing as a module that PRODUCT_PACKAGES can resolve -- make then
fails with "includes non-existent modules in PRODUCT_PACKAGES". The module has
to be dropped from the generated package list as well.

This tool removes every PRODUCT_PACKAGES entry whose module is marked
installable:false in Android.bp, and (in report mode) prints the source-built
module that provides the same installed filename, so nothing silently vanishes
from the image.

Usage:
  sync_vendor_mk.py                 report only
  sync_vendor_mk.py --apply         rewrite sm4450-common-vendor.mk
"""
import glob
import os
import re
import sys

BP = "Android.bp"
MK = "sm4450-common-vendor.mk"
ROOT = "../../.."
NAME_RE = re.compile(r'\bname:\s*"([^"]+)"')
STEM_RE = re.compile(r'\bstem:\s*"([^"]+)"')
OFF_RE = re.compile(r"installable:\s*false")
SRC_GLOBS = [
    "hardware/**/Android.bp",
    "vendor/qcom/**/Android.bp",
    "device/**/Android.bp",
]


def blocks(text, start_re):
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
                    yield text[m.start():j + 1]
                    break
            j += 1


def disabled_map(text):
    """module name -> installed filename, for installable:false prebuilts."""
    out = {}
    pat = re.compile(r"cc_prebuilt_(?:library_shared|binary)\s*\{")
    for body in blocks(text, pat):
        if not OFF_RE.search(body):
            continue
        nm = NAME_RE.search(body)
        if not nm:
            continue
        is_bin = "cc_prebuilt_binary" in body[:64]
        st = STEM_RE.search(body)
        base = st.group(1) if st else nm.group(1)
        out[nm.group(1)] = base if is_bin else base + ".so"
    return out


def source_index():
    """installed filename -> source-built module name.

    Includes hidl_interface / aidl_interface, whose generated cc_library keeps
    the '@' in its module name and therefore installs under exactly that name.
    """
    idx = {}
    pat = re.compile(
        r"cc_library_shared\s*\{|cc_library\s*\{"
        r"|hidl_interface\s*\{|aidl_interface\s*\{"
    )
    for g in SRC_GLOBS:
        for bp in glob.glob(os.path.join(ROOT, g), recursive=True):
            if "/out/" in bp.replace("\\", "/"):
                continue
            try:
                s = open(bp, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for body in blocks(s, pat):
                if re.match(r"\s*(hidl_interface|aidl_interface)", body):
                    # hidl_interface puts the version in the module name itself
                    # ("vendor.nxp.nxpnfc@1.0"), so the installed file is simply
                    # that name plus .so.
                    nm = NAME_RE.search(body)
                    if nm and "@" in nm.group(1):
                        idx.setdefault(nm.group(1) + ".so", "<hidl>")
                    continue
                nm = NAME_RE.search(body)
                if not nm:
                    continue
                st = STEM_RE.search(body)
                idx.setdefault((st.group(1) if st else nm.group(1)) + ".so", nm.group(1))
    return idx


def main(argv):
    apply = "--apply" in argv
    dis = disabled_map(open(BP, encoding="utf-8").read())
    src = source_index()

    lines = open(MK, encoding="utf-8").read().split("\n")
    kept, dropped = [], []
    for ln in lines:
        s = ln.strip()
        tok = s.rstrip("\\").strip()
        if tok in dis:
            dropped.append(tok)
            continue
        kept.append(ln)

    # A dropped entry can leave a dangling "PRODUCT_PACKAGES += \" with no body,
    # or a trailing backslash on the last surviving line. Normalise both.
    text = "\n".join(kept)
    text = re.sub(r"(PRODUCT_PACKAGES \+= \\\n)\s*\n", r"\1", text)
    text = re.sub(r"\\\n(?!\s*\S)", "\n", text)
    text = re.sub(r" \\\n\s*\\\n", " \\\n", text)
    text = re.sub(r"\n\n\n+", "\n\n", text)
    text = re.sub(r"[ \t]+\\\n\n", "\n\n", text)

    print("disabled modules: %d" % len(dis))
    print("dropped from PRODUCT_PACKAGES: %d" % len(dropped))
    missing_replacement = [d for d in dropped if dis[d] not in src]
    print("dropped WITHOUT a source-built replacement: %d" % len(missing_replacement))
    for d in missing_replacement:
        print("   !! %-55s %s" % (d, dis[d]))
    print()
    for d in dropped:
        print("   %-55s -> %s" % (d, src.get(dis[d], "<none>")))

    if apply:
        with open(MK, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("\nwrote %s" % MK)
        print("PRODUCT_PACKAGES entries left: %d" %
              len(re.findall(r"^\s{4}\S", text, re.M)))
    else:
        print("\n(report only; pass --apply to rewrite %s)" % MK)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
