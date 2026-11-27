#!/usr/bin/env python3
"""Repair the sky kernel tree's build glue.

kernel/xiaomi/sky = ACK android16-6.12 full tree with CLO's qcom 6.12 soc-repo
overlay copied over it. CLO's overlay ships *delta-only* build files
(mm/Makefile = 6 lines where ACK has 152), so the copy replaced full ACK files
with fragments. C files are byte-identical to ACK; only the glue is broken.

Fix: for every build file where the CLO side is a fragment (loses >30% of the
ACK non-blank lines), restore the ACK content and append the CLO-only lines.
Files where CLO is a superset are left alone.

  python3 fix_kbuild.py            # dry run, report
  python3 fix_kbuild.py --apply    # write
"""
import os
import re
import subprocess
import sys

ACK = os.path.expanduser("~/ack612")
SRC = os.path.expanduser("~/los/kernel/xiaomi/sky")
APPLY = "--apply" in sys.argv

SYM = re.compile(r'^(?:menu)?config\s+([A-Za-z0-9_]+)', re.M)
SRC_RE = re.compile(r'^\s*(?:o|r|or)?source\s+"([^"]+)"', re.M)
EXT_PREFIX = re.compile(r'\$\(KCONFIG_EXT_PREFIX\)')
TOP = re.compile(r'^(?:menuconfig|config|menu|endmenu|if|endif|choice|endchoice'
                 r'|comment|mainmenu|(?:o|r|or)?source)\b')


def norm_src(path):
    """CLO writes source paths as $(KCONFIG_EXT_PREFIX)foo/bar; ACK writes foo/bar.
    Both resolve to the same file here, so compare with the prefix stripped."""
    return EXT_PREFIX.sub("", path).strip()


def is_build_file(name):
    base = os.path.basename(name)
    return base == "Kbuild" or base.startswith("Makefile") or base.startswith("Kconfig")


# CLO's dtbs machinery (scripts/Makefile.dtbs + Makefile.lib's multi-dtb-y) owns
# arch/arm64/boot/dts/Makefile and expects only the vendor subdir. Restoring
# ACK's per-platform subdir list makes each platform's dtb-y get the $(obj)/
# prefix twice ("No rule to make target .../allwinner/arch/arm64/.../x.dtb").
#
# The root Makefile is skipped too: CLO ships a whole 6.11-era copy, not a
# delta, so merging it appends a second `ifdef may-sync-config` body and a
# stray `else` ("Makefile:2219: *** extraneous 'else'"). ACK's is correct.
SKIP = {"arch/arm64/boot/dts/Makefile", "Makefile"}

# An obj-$(CONFIG_...) line that adds one or more directories.
GUARDED_DIRS = re.compile(r'^obj-\$\(CONFIG_[A-Z0-9_]+\)\s*\+?=\s*(.+)$')
# Any obj-* line (guarded or not) that adds one or more directories.
ANY_OBJ_DIRS = re.compile(r'^obj-[A-Za-z0-9_$()]+(?:-[A-Za-z0-9_$()]+)*\s*\+?=\s*(.+)$')
# An unconditional obj-y line adding one or more directories.
PLAIN_OBJY = re.compile(r'^obj-y\s*\+?=\s*(.+)$')


def dup_dir_block(line, guarded):
    """True when `line` is a plain `obj-y += <dir>/` that is redundant because
    the same Makefile already recurses into that path (or into its parent).

    CLO's fragments end with a flat list of every subdirectory; merging it in
    makes the tree descend into e.g. drivers/usb/gadget/function/ twice (once
    via gadget/, once directly) and every .o in it is linked twice.
    """
    m = PLAIN_OBJY.match(line)
    if not m:
        return False
    for tok in m.group(1).split():
        if not tok.endswith("/"):
            continue
        if tok in guarded:
            return True
        # `gadget/function/` is redundant when `gadget/` is already added.
        head = tok.split("/")[0] + "/"
        if head in guarded and head != tok:
            return True
    return False


def nb(text):
    return [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]


def kconfig_delta(ack, clo):
    """Return the CLO chunks that define symbols/sources ACK does not have."""
    have_sym = set(SYM.findall(ack))
    have_src = {norm_src(s) for s in SRC_RE.findall(ack)}
    lines = clo.splitlines(keepends=True)
    out = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if re.match(r'^choice\b', line):
            j = i + 1
            while j < n and not re.match(r'^endchoice\b', lines[j]):
                j += 1
            j = min(j + 1, n)
            block = "".join(lines[i:j])
            if any(s not in have_sym for s in SYM.findall(block)):
                out.append(block)
            i = j
            continue
        m = re.match(r'^(?:menuconfig|config)\s+([A-Za-z0-9_]+)', line)
        if m:
            j = i + 1
            while j < n and not TOP.match(lines[j]):
                j += 1
            if m.group(1) not in have_sym:
                out.extend(lines[i:j])
            i = j
            continue
        ms = re.match(r'^\s*(?:o|r|or)?source\s+"([^"]+)"', line)
        if ms:
            if norm_src(ms.group(1)) not in have_src:
                out.append(line)
            i += 1
            continue
        i += 1
    return "".join(out)


def drop_duplicate_sources(root="."):
    """Delete `source` lines that pull in a Kconfig file already sourced
    elsewhere.  A line counts as CLO's when ACK's twin of the same file does
    not contain it; the first ACK-owned occurrence is always kept."""
    import glob
    files = glob.glob(os.path.join(root, "**/Kconfig*"), recursive=True)
    # target -> [(path, line_index, line, is_clo)]
    hits = {}
    for path in files:
        try:
            lines = open(path, encoding="utf-8", errors="surrogateescape").read().splitlines(True)
        except OSError:
            continue
        rel = os.path.relpath(path, root)
        ack_path = os.path.join(ACK, rel)
        # CLO-only Kconfigs (Kconfig.msm, techpack/*) legitimately source files
        # ACK also reaches; they are gated behind their own if/endif and are
        # not what breaks the parse.  Only consider files ACK already had.
        if not os.path.exists(ack_path):
            continue
        ack_text = open(ack_path, encoding="utf-8", errors="surrogateescape").read()
        ack_src = {norm_src(m.group(1)) for m in SRC_RE.finditer(ack_text)}
        for i, line in enumerate(lines):
            m = re.match(r'^\s*(?:o|r|or)?source\s+"([^"]+)"', line)
            if not m:
                continue
            tgt = norm_src(m.group(1))
            # ACK's twin has this exact source line => it is ACK's, keep it.
            is_clo = tgt not in ack_src
            hits.setdefault(tgt, []).append((path, i, line, is_clo))
    # Collect every deletion first, then apply once per file.  Deleting inside
    # the per-target loop invalidates the indices computed for the other
    # targets in the same file (a second pass would delete the wrong line).
    victims = {}
    for tgt, occ in hits.items():
        if len(occ) < 2:
            continue
        clo_occ = [o for o in occ if o[3]]
        if not clo_occ:
            continue
        keep = next((o for o in occ if not o[3]), None)
        for path, i, line, _ in (clo_occ if keep else clo_occ[1:]):
            victims.setdefault(path, set()).add(i)
    dropped = 0
    for path, idxs in victims.items():
        try:
            lines = open(path, encoding="utf-8", errors="surrogateescape").read().splitlines(True)
        except OSError:
            continue
        for i in sorted(idxs, reverse=True):
            del lines[i]
        open(path, "w", encoding="utf-8", errors="surrogateescape").writelines(lines)
        dropped += len(idxs)
        print("  dedupe %s: -%d source line(s)"
              % (os.path.relpath(path, root), len(idxs)))
    return dropped


def makefile_delta(ack, clo):
    """Return the CLO blocks ACK does not already contain.

    Blocks are runs of non-blank lines, so a target and its recipe (and any
    backslash continuations) stay together -- appending single missing lines
    would orphan a recipe or a continuation and break the Makefile.

    Two kinds of CLO block are dropped even though ACK lacks them verbatim:

    * ``obj-y += <dir>/`` where ``<dir>/`` already appears in an
      ``obj-$(CONFIG_...)`` line of the ACK file. CLO's fragments end with a
      flat list of every subdir; keeping it recurses into the same directory
      twice and links every .o twice ("duplicate symbol: gs_alloc_req").
    * the same, for ``subdir-y``/``subdir-ccflags`` style flat lists.
    """
    have = {l.strip() for l in ack.splitlines()}
    guarded = set()
    for line in ack.splitlines():
        m = ANY_OBJ_DIRS.match(line)
        if m:
            guarded.update(t for t in m.group(1).split() if t.endswith("/"))
    blocks, cur = [], []
    for line in clo.splitlines(keepends=True):
        if line.strip():
            cur.append(line)
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    out = []
    for block in blocks:
        if all(l.strip() in have for l in block):
            continue
        keep = [l for l in block if not dup_dir_block(l, guarded)]
        if not keep:
            continue
        out.extend(keep)
        out.append("\n")
    return "".join(out)


def main():
    tracked = subprocess.run(["git", "-C", SRC, "ls-files"],
                             capture_output=True, text=True).stdout.split("\n")
    frag, sup, same, noack = [], 0, 0, 0
    for rel in tracked:
        if not rel or not is_build_file(rel) or rel in SKIP:
            continue
        a = os.path.join(ACK, rel)
        c = os.path.join(SRC, rel)
        if not os.path.exists(a):
            noack += 1
            continue
        ack = open(a, encoding="utf-8", errors="surrogateescape").read()
        clo = open(c, encoding="utf-8", errors="surrogateescape").read()
        if ack == clo:
            same += 1
            continue
        na, nc = len(nb(ack)), len(nb(clo))
        # Line count is a red herring: CLO's supersets can still DROP ACK
        # lines (drivers/spmi/Makefile adds 3 lines and loses the one that
        # builds spmi.o).  Merge whenever ACK content is missing.
        lost = {l.strip() for l in nb(ack)} - {l.strip() for l in nb(clo)}
        if not lost:
            sup += 1
            continue
        delta = kconfig_delta(ack, clo) if "Kconfig" in os.path.basename(rel) \
            else makefile_delta(ack, clo)
        merged = ack
        if not merged.endswith("\n"):
            merged += "\n"
        merged += ("\n# --- CLO soc-repo overlay additions (restored by fix_kbuild.py) ---\n"
                   + delta)
        frag.append((rel, na, nc, len(nb(delta))))
        if APPLY:
            with open(c, "w", encoding="utf-8", errors="surrogateescape") as f:
                f.write(merged)

    print(f"fragments repaired: {len(frag)}   supersets left alone: {sup}   "
          f"identical: {same}   no ACK twin: {noack}")
    for rel, na, nc, nd in sorted(frag, key=lambda x: -(x[1] - x[2]))[:25]:
        print(f"  {rel:55s} ACK {na:5d}  CLO {nc:4d}  +{nd:4d} delta lines")
    if APPLY:
        n = drop_duplicate_sources(SRC)
        print(f"duplicate `source` lines dropped: {n}")
    if not APPLY:
        print("\n(dry run - pass --apply to write)")


if __name__ == "__main__":
    main()
