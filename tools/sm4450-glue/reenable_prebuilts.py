#!/usr/bin/env python3
"""Re-enable specific prebuilts and re-add them to PRODUCT_PACKAGES.

Some `installable: false` decisions are wrong: when the disabled module is a
HIDL *interface* library whose implementation (`<name>-impl`) and service are
still installed, nothing else provides the interface .so and the vendor
services fail to load at runtime.

This tool undoes that for a named set:
  1. removes `installable: false,` from the matching Android.bp blocks
  2. appends the module names back into the PRODUCT_PACKAGES block of a .mk

Usage (from the vendor repo root):
  reenable_prebuilts.py --list names.txt --mk sm4450-common-vendor.mk [--apply]
"""
import re
import sys

BP = "Android.bp"


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


def main(argv):
    apply = "--apply" in argv
    lst = argv[argv.index("--list") + 1]
    mkpath = argv[argv.index("--mk") + 1]
    names = set(l.strip() for l in open(lst, encoding="utf-8") if l.strip())

    text = open(BP, encoding="utf-8").read()
    edits = []
    found = set()
    for start, brace, end in blocks(text):
        body = text[start:end]
        nm = re.search(r'\bname:\s*"([^"]+)"', body)
        if not nm or nm.group(1) not in names:
            continue
        found.add(nm.group(1))
        m = re.search(r"^\s*installable:\s*false,\s*\n", body, re.M)
        if m:
            edits.append((start + m.start(), start + m.end()))

    print("requested: %d" % len(names))
    print("found in Android.bp: %d" % len(found))
    for n in sorted(names - found):
        print("   !! not found:", n)
    print("installable:false lines to remove: %d" % len(edits))

    newtext = text
    for s, e in sorted(edits, reverse=True):
        newtext = newtext[:s] + newtext[e:]

    mk = open(mkpath, encoding="utf-8").read()
    add = [n for n in sorted(found)
           if not re.search(r"(?m)^\s+" + re.escape(n) + r"\s*(\\|$)", mk)]
    print("to re-add to %s: %d" % (mkpath, len(add)))

    if apply:
        open(BP, "w", encoding="utf-8", newline="\n").write(newtext)
        if add:
            # append into the first PRODUCT_PACKAGES += block
            m = re.search(r"(?m)^PRODUCT_PACKAGES \+= \\\n", mk)
            if not m:
                print("!! no PRODUCT_PACKAGES block in", mkpath)
                return 1
            # find the end of that block (last line ending with backslash)
            pos = m.end()
            last = pos
            while True:
                nl = mk.find("\n", last)
                if nl < 0:
                    break
                line = mk[last:nl]
                if line.rstrip().endswith("\\"):
                    last = nl + 1
                else:
                    break
            ins = "".join("    %s \\\n" % n for n in add)
            mk = mk[:last] + ins + mk[last:]
            open(mkpath, "w", encoding="utf-8", newline="\n").write(mk)
        print("APPLIED")
    else:
        print("(report only; pass --apply)")
        for n in add:
            print("   +", n)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
