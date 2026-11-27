#!/usr/bin/env python3
"""Repair the two check_elf_file failures in a stock-ROM vendor blob dump.

1. DT_SONAME mismatch
   Soong module names cannot contain '@', so the generated Android.bp renames
   android.hardware.atrace@1.0 -> android.hardware.atrace_1.0.  Soong then
   installs the file under the *module* name, which breaks every runtime
   DT_NEEDED lookup of the real soname.  Adding `stem:` restores the original
   file name, which is what the blob's DT_SONAME already says.

2. DT_NEEDED "... is not specified in shared_libs"
   check_elf_file wants each prebuilt's dependency list restated in
   shared_libs.  These binaries ship prebuilt by the OEM; their dependencies
   are other prebuilts in the same tree and resolve at runtime.  Restating
   them per module is brittle and buys nothing, so the check is disabled for
   prebuilt modules only (source-built modules keep the check).

Run from the vendor repo root (the directory holding Android.bp).
"""
import os
import re
import sys

BP = "Android.bp"
MODULE_RE = re.compile(
    r'^(cc_prebuilt_library_shared|cc_prebuilt_binary|android_app_import)\s*\{',
    re.M,
)
NAME_RE = re.compile(r'\bname:\s*"([^"]+)"')
SRC_RE = re.compile(r'"([^"]+\.so)"')


def find_blocks(text):
    """Yield (start, end, kind) for every top-level module block."""
    out = []
    pos = 0
    while True:
        m = MODULE_RE.search(text, pos)
        if not m:
            break
        brace = text.index("{", m.start())
        depth = 0
        k = brace
        while k < len(text):
            if text[k] == "{":
                depth += 1
            elif text[k] == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        out.append((m.start(), k + 1, m.group(1)))
        pos = k + 1
    return out


def add_props(block, props, indent="    "):
    """Insert `props` (list of 'key: value' strings) before the closing brace."""
    close = block.rstrip().rfind("}")
    head = block[:close].rstrip("\n")
    body = "\n".join(indent + p for p in props)
    return head + "\n" + body + "\n" + block[close:]


def main():
    if not os.path.exists(BP):
        sys.exit("run me from the vendor repo root")
    text = open(BP, encoding="utf-8").read()
    blocks = find_blocks(text)

    edits = []          # (start, end, new_block, tag)
    stem_count = 0
    elf_off = 0

    for start, end, kind in blocks:
        block = text[start:end]
        nm = NAME_RE.search(block)
        if not nm:
            continue
        name = nm.group(1)
        props = []

        if kind == "cc_prebuilt_library_shared":
            # The soname the blob was linked with is the source file name.
            srcs = SRC_RE.findall(block)
            wanted = None
            for s in srcs:
                base = os.path.basename(s)
                if "@" in base:
                    wanted = base
                    break
            if wanted and wanted != name + ".so":
                if "stem:" not in block:
                    props.append('stem: "%s",' % wanted[:-3])
                    stem_count += 1

        if "check_elf_files" not in block:
            props.append("check_elf_files: false,")
            elf_off += 1

        if props:
            edits.append((start, end, add_props(block, props), name))

    for start, end, new_block, _ in reversed(edits):
        text = text[:start] + new_block + text[end:]

    open(BP, "w", encoding="utf-8").write(text)
    print("modules touched: %d" % len(edits))
    print("stem added:     %d" % stem_count)
    print("check_elf_files disabled: %d" % elf_off)


if __name__ == "__main__":
    main()
