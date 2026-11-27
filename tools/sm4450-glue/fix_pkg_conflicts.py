#!/usr/bin/env python3
"""Vendor prebuilt collision repair.

Soong refuses to build when a prebuilt in the vendor tree installs to the same
path as a source-built module.  The source-built copy is the one we want (it
matches the rest of the platform), so mark the prebuilt `installable: false`
instead of deleting it -- module references from other prebuilts stay
resolvable.

Usage:  python3 fix_pkg_conflicts.py <soong_log>
Run from the vendor repo root (the directory holding Android.bp).
"""
import re
import sys

BP = "Android.bp"


def scan_blocks(text):
    """Return [(start, end)] character offsets of every top-level { } block."""
    blocks = []
    i, n = 0, len(text)
    depth = 0
    start = None
    in_str = in_line = in_block = False
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_line:
            if c == "\n":
                in_line = False
            i += 1
            continue
        if in_block:
            if c == "*" and nxt == "/":
                in_block = False
                i += 2
                continue
            i += 1
            continue
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == "/" and nxt == "/":
            in_line = True
            i += 2
            continue
        if c == "/" and nxt == "*":
            in_block = True
            i += 2
            continue
        if c == '"':
            in_str = True
            i += 1
            continue
        if c == "{":
            depth += 1
            if depth == 1:
                # include the module-type header that precedes the brace
                ls = text.rfind("\n", 0, i) + 1
                start = ls
        elif c == "}":
            depth -= 1
            if depth == 0 and start is not None:
                blocks.append((start, i + 1))
                start = None
        i += 1
    return blocks


NAME_RE = re.compile(r'\bname:\s*"([^"]+)"')
STEM_RE = re.compile(r'\bstem:\s*"([^"]+)"')
ALREADY_RE = re.compile(r'^\s*installable:\s*false,', re.M)
CONFLICT_RE = re.compile(r'packaging conflict at (\S+):')


def main(argv):
    dry = "--dry" in argv
    argv = [a for a in argv if a != "--dry"]
    if not argv:
        print("usage: fix_pkg_conflicts.py [--dry] <file-with-conflict-paths>")
        return 1
    raw = open(argv[0], encoding="utf-8", errors="replace").read()
    conflicts = {m.rsplit("/", 1)[-1] for m in CONFLICT_RE.findall(raw)}
    if not conflicts:
        conflicts = {ln.strip().rsplit("/", 1)[-1] for ln in raw.splitlines() if ln.strip()}
    if not conflicts:
        print("no conflicts in input")
        return 0
    print("conflicts: %d" % len(conflicts))

    text = open(BP, encoding="utf-8").read()
    blocks = scan_blocks(text)

    edits = []
    hit = []
    for s, e in blocks:
        body = text[s:e]
        is_lib = "cc_prebuilt_library_shared" in body
        is_bin = "cc_prebuilt_binary" in body
        if not (is_lib or is_bin):
            continue
        nm = NAME_RE.search(body)
        if not nm:
            continue
        stem = STEM_RE.search(body)
        base = stem.group(1) if stem else nm.group(1)
        fname = base if is_bin else base + ".so"
        if fname not in conflicts:
            continue
        if ALREADY_RE.search(body):
            continue
        brace = body.index("{")
        edits.append((s + brace + 1, '\n    installable: false,'))
        hit.append(nm.group(1))

    for pos, new in sorted(edits, reverse=True):
        text = text[:pos] + new + text[pos:]

    open(BP, "w", encoding="utf-8").write(text)
    print("marked installable:false -> %d" % len(hit))
    for h in hit:
        print("   " + h)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
