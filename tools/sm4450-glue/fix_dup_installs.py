#!/usr/bin/env python3
"""Disable vendor prebuilts whose install target is duplicated by a source build.

Source of truth is out/soong/installs-*.mk: it lists the final install target
and the intermediate that produces it. If a target appears twice and exactly
one producer is a vendor/xiaomi/sm4450-common prebuilt, the prebuilt must stop
installing -- kati otherwise dies with "overriding commands for target".

This is strictly better than scanning Android.bp trees by hand: it sees every
producer (hardware/interfaces, frameworks/hardware/interfaces, all-versions
util modules, ...) because soong already resolved them.

Usage (from the vendor repo root):
  fix_dup_installs.py                report
  fix_dup_installs.py --apply        mark the prebuilts installable:false
  fix_dup_installs.py --apply --mk sm4450-common-vendor.mk
"""
import os
import re
import sys
from collections import defaultdict

INSTALLS = "../../../out/soong/installs-lineage_sky.mk"
BP = "Android.bp"
PREBUILT_TAG = "/vendor/xiaomi/sm4450-common/"
RULE_RE = re.compile(r"^(out/target/product/\S+?):\s+(\S+)")
NAME_RE = re.compile(r'\bname:\s*"([^"]+)"')
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
                    yield m.start(), i, j + 1
                    break
            j += 1


def find_dupes():
    """install target -> list of (intermediate path, is_prebuilt)."""
    targets = defaultdict(list)
    with open(INSTALLS, encoding="utf-8", errors="replace") as f:
        for ln in f:
            m = RULE_RE.match(ln)
            if m:
                targets[m.group(1)].append(m.group(2))
    out = {}
    for t, srcs in targets.items():
        if len(srcs) < 2:
            continue
        pb = [s for s in srcs if PREBUILT_TAG in s]
        src = [s for s in srcs if PREBUILT_TAG not in s]
        if pb and src:
            out[t] = (pb, src)
    return out


def module_for(intermediate):
    """out/soong/.intermediates/<dir>/<module>/<variant>/<file> -> module."""
    parts = intermediate.split("/")
    try:
        i = parts.index(".intermediates")
    except ValueError:
        return None
    rest = parts[i + 1:]
    if len(rest) < 3:
        return None
    # module name is the last component before the variant dir
    return rest[-3]


def main(argv):
    apply = "--apply" in argv
    mkpath = None
    if "--mk" in argv:
        mkpath = argv[argv.index("--mk") + 1]

    dupes = find_dupes()
    print("duplicated targets with a vendor prebuilt: %d" % len(dupes))

    mods = set()
    unresolved = []
    for t, (pb, src) in sorted(dupes.items()):
        m = module_for(pb[0])
        if m:
            mods.add(m)
        else:
            unresolved.append(t)
    print("distinct prebuilt modules to disable: %d" % len(mods))
    for t in unresolved:
        print("   !! could not resolve module for", t)

    text = open(BP, encoding="utf-8").read()
    have = set()
    already = set()
    edits = []
    for start, brace, end in blocks(text):
        body = text[start:end]
        nm = NAME_RE.search(body)
        if not nm or nm.group(1) not in mods:
            continue
        have.add(nm.group(1))
        if OFF_RE.search(body):
            already.add(nm.group(1))
            continue
        edits.append(brace + 1)
    print("already disabled: %d" % len(already))
    print("installable:false lines to add: %d" % len(edits))
    for n in sorted(mods - have):
        print("   !! module not found in Android.bp:", n)

    if apply and edits:
        new = text
        for pos in sorted(edits, reverse=True):
            new = new[:pos] + "\n    installable: false," + new[pos:]
        open(BP, "w", encoding="utf-8", newline="\n").write(new)
        print("APPLIED to %s" % BP)

    if apply and mkpath:
        mk = open(mkpath, encoding="utf-8").read()
        lines = mk.split("\n")
        kept, dropped = [], []
        for ln in lines:
            tok = ln.strip().rstrip("\\").strip()
            if tok in mods:
                dropped.append(tok)
                continue
            kept.append(ln)
        mk2 = "\n".join(kept)
        mk2 = re.sub(r"(PRODUCT_PACKAGES \+= \\\n)\s*\n", r"\1", mk2)
        mk2 = re.sub(r"\\\n(?!\s*\S)", "\n", mk2)
        mk2 = re.sub(r"\n\n\n+", "\n\n", mk2)
        open(mkpath, "w", encoding="utf-8", newline="\n").write(mk2)
        print("dropped %d entries from %s" % (len(dropped), mkpath))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
