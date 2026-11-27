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

# Header fix_kbuild.py writes before every delta block.  Stripped before
# diffing so re-running over an already-merged file is a no-op.
MARKER = "# --- CLO soc-repo overlay additions (restored by fix_kbuild.py) ---"

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
#
# drivers/block/zram is skipped as a whole.  CLO's overlay ships an older zram
# generation (pre-6.7 zcomp API: zcomp_create(const char *), no zcomp_params /
# zcomp_ctx / zcomp_req) for zcomp.c, zcomp.h, zram_drv.c and zram_drv.h, but
# the per-algorithm backends in this tree are ACK's and call the new API --
# mixing them yields 85 "incomplete definition of type 'struct zcomp_params'"
# errors plus "too few arguments to function call" in the module build.  ACK's
# set is internally consistent, so keep all four.
SKIP = {"arch/arm64/boot/dts/Makefile", "Makefile",
        "drivers/block/zram/zcomp.c", "drivers/block/zram/zcomp.h",
        "drivers/block/zram/zram_drv.c", "drivers/block/zram/zram_drv.h"}

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
        # `hwtracing/` is redundant when the file already descends into
        # `hwtracing/stm/` and `hwtracing/coresight/` individually: the flat
        # `obj-y += hwtracing/` makes the tree recurse into those dirs a
        # second time, which builds every .o twice and races the linker.
        if any(g.startswith(tok) for g in guarded):
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


def _obj_has_source(srcdir, obj):
    """True when some make rule could actually produce <obj> from a source
    file in `srcdir`.  CLO's fragments reference object names that do not
    exist -- drivers/block/Makefile asks for virtio_block.o while the file on
    disk is virtio_blk.c, drivers/regulator/Makefile asks for
    qti_fixed_regulator.o while the source never shipped in the overlay --
    and make dies with "No rule to make target ... Stop." before compiling
    anything else in that directory."""
    base = obj[:-2] if obj.endswith("/") is False and obj.endswith(".o") else obj
    if obj.endswith("/"):
        return os.path.isdir(os.path.join(srcdir, obj))
    stem = obj[:-2]
    stem = stem.rsplit("/", 1)[-1]
    for ext in (".c", ".S", ".s", ".cxx"):
        if os.path.exists(os.path.join(srcdir, stem + ext)):
            return True
    # Composite objects have no source of their own; they are built from a
    # `<name>-objs`/`<name>-y` list.
    return False


def makefile_delta(ack, clo, srcdir="."):
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

    # Drop duplicate object members.  CLO's fragments restate whole lines:
    # arm-smmu/Makefile ends up with `obj-$(CONFIG_ARM_SMMU) += arm_smmu.o`
    # twice and `arm_smmu-objs` listing arm-smmu.o twice, so the composite
    # object contains every symbol twice and the build fails with
    # "redefinition of 'nvidia_smmu_impl_init'".
    ack_objs = set(re.findall(r'\b([A-Za-z0-9_+.-]+\.o)\b', ack))
    ack_lines = {l.strip() for l in ack.splitlines() if l.strip()}

    def has_src(obj):
        # Strip a leading directory and the .o suffix before probing.
        stem = obj[:-2].rsplit("/", 1)[-1]
        return any(os.path.exists(os.path.join(srcdir, stem + e))
                   for e in (".c", ".S", ".s", ".cxx"))

    filtered = []
    for line in out:
        s = line.strip()
        if not s:
            filtered.append(line)
            continue
        objrefs = re.findall(r'\b([A-Za-z0-9_+.-]+\.o)\b', s)
        if objrefs:
            # A CLO line that ACK already has verbatim is redundant.
            if s in ack_lines:
                continue
            # Drop object names with no source in this directory: CLO's
            # fragments carry typos (virtio_block.o vs virtio_blk.c) and stale
            # references (qti_fixed_regulator.o) that make dies on with
            # "No rule to make target".
            m = re.match(r'^(.*?\+?=)\s*(.*)$', s)
            if m and m.group(1).endswith("="):
                # Objects named on the right-hand side, and any `<name>.o` in
                # the make-variable name on the left (`CFLAGS_qti_fixed_regulator.o`).
                lhs_objs = re.findall(r'\b([A-Za-z0-9_+.-]+\.o)\b', m.group(1))
                if lhs_objs and not any(has_src(o) for o in lhs_objs):
                    continue
                members = m.group(2).split()
                keep = [t for t in members
                        if not re.match(r'^[A-Za-z0-9_+.-]+\.o$', t)
                        and t.endswith("/") is False
                        or (re.match(r'^[A-Za-z0-9_+.-]+\.o$', t)
                            and t not in ack_objs and has_src(t))]
                if not keep:
                    continue
                if keep != members:
                    line = m.group(1) + " " + " ".join(keep) + "\n"
                filtered.append(line)
                continue
            # A `CFLAGS_foo.o := ...` style line for an object that does not
            # exist is dead weight too.
            if all(re.match(r'^[A-Za-z0-9_+.-]+\.o$', o) and not has_src(o)
                   for o in objrefs):
                continue
        filtered.append(line)
    return "".join(filtered)


def normalize_includes(root="."):
    """Rewrite CLO's tree-root-relative `#include "a/b/c.h"` to the
    file-relative form ACK uses.

    CLO's overlay files are written against a build that passes -I$(srctree),
    so they include headers as `#include "drivers/pinctrl/core.h"`.  ACK's
    Makefile.build only adds -I$(src) and -I$(obj), so the same line fails
    with "file not found".  The header is right there next to the includer's
    parent -- rewrite to the relative path."""
    import glob
    changed = 0
    for path in glob.glob(os.path.join(root, "**", "*.c"), recursive=True) + \
                glob.glob(os.path.join(root, "**", "*.h"), recursive=True):
        if "/.git/" in path or path.startswith(".git"):
            continue
        try:
            text = open(path, encoding="utf-8", errors="surrogateescape").read()
        except OSError:
            continue
        if '#include "' not in text and "#include <" not in text:
            continue
        here = os.path.dirname(os.path.relpath(path, root))
        out, hits = [], 0
        for line in text.splitlines(True):
            # Keep the line terminator out of the match: `(.*)$` on a string
            # that still ends with "\n" makes `.` swallow nothing but the
            # trailing newline ends up in group(3) and gets written back -- but
            # splitlines(True) lines are re-joined below, so matching without
            # DOTALL and rebuilding from parts is what keeps them separate.
            body = line.rstrip("\n")
            nl = line[len(body):]
            m = re.match(r'^(\s*#\s*include\s+)"([^"]+)"(.*)$', body)
            if m and "/" in m.group(2) and not m.group(2).startswith("."):
                root_rel = m.group(2)
                if os.path.exists(os.path.join(root, root_rel)):
                    rel = os.path.relpath(os.path.join(root, root_rel),
                                          os.path.join(root, here))
                    body = '%s"%s"%s' % (m.group(1), rel, m.group(3))
                    hits += 1
            elif m and "/" not in m.group(2) and not m.group(2).startswith("."):
                # Bare quoted name that is not next to the includer: CLO writes
                # `#include "mem-prot.h"` for a header that lives under
                # include/linux/.  Rewrite to the angle form so the normal
                # search path finds it.  Leave it alone when the header really
                # does sit next to the includer.
                if not os.path.exists(os.path.join(root, here, m.group(2))):
                    for pref in ("include/linux/", "include/"):
                        if os.path.exists(os.path.join(root, pref + m.group(2))):
                            body = '%s<%s>%s' % (
                                m.group(1),
                                pref[len("include/"):] + m.group(2),
                                m.group(3))
                            hits += 1
                            break
            else:
                # CLO also writes <soc/qcom/foo.h> for headers that live under
                # include/linux/soc/qcom/.  ACK only puts include/ and
                # include/uapi/ on the search path, so rewrite to the full
                # include-relative form.
                a = re.match(r'^(\s*#\s*include\s+)<([^>]+)>(.*)$', body)
                if a and "/" in a.group(2):
                    # Include spelled with the tree root baked in:
                    # `#include <include/linux/arm-smccc.h>`.  Strip the
                    # `include/` prefix so it resolves against -I$(srctree)/include.
                    if a.group(2).startswith("include/"):
                        body = '%s<%s>%s' % (a.group(1), a.group(2)[len("include/"):],
                                             a.group(3))
                        hits += 1
                        out.append(body + nl)
                        continue
                    # If the include already resolves against include/, leave
                    # it alone -- `-I$(srctree)/include` is always on the path,
                    # and rewriting would point at the wrong header (e.g.
                    # <soc/qcom/socinfo.h> vs <linux/soc/qcom/socinfo.h> are
                    # two different files with different enum feature_code).
                    if os.path.exists(os.path.join(root, "include", a.group(2))):
                        out.append(body + nl)
                        continue
                    for pref in ("include/linux/", "include/"):
                        if os.path.exists(os.path.join(root, pref + a.group(2))):
                            body = '%s<%s>%s' % (a.group(1),
                                                 pref[len("include/"):] + a.group(2),
                                                 a.group(3))
                            hits += 1
                            break
            out.append(body + nl)
        if hits:
            open(path, "w", encoding="utf-8",
                 errors="surrogateescape").writelines(out)
            changed += 1
            print("  include-fix %s: %d line(s)"
                  % (os.path.relpath(path, root), hits))
    return changed


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
        # The committed tree already contains our previous merge output, so
        # `git checkout -- .` restores a file that ends in
        # "# --- CLO soc-repo overlay additions ... ---".  Strip those marker
        # lines before diffing, otherwise every run appends another marker and
        # another copy of the delta.
        if MARKER in clo:
            clo = "".join(l for l in clo.splitlines(True)
                          if l.strip() != MARKER)
        if ack == clo:
            same += 1
            continue
        na, nc = len(nb(ack)), len(nb(clo))
        # Line count is a red herring: CLO's supersets can still DROP ACK
        # lines (drivers/spmi/Makefile adds 3 lines and loses the one that
        # builds spmi.o).  Merge whenever ACK content is missing.
        lost = {l.strip() for l in nb(ack)} - {l.strip() for l in nb(clo)}
        if not lost:
            # CLO is a superset of ACK here -- but its extra lines can still
            # duplicate ACK object members (arm-smmu/Makefile restates
            # `obj-$(CONFIG_ARM_SMMU) += arm_smmu.o` and lists arm-smmu.o again
            # in arm_smmu-objs, so the composite object gets every symbol
            # twice).  Run the same dedupe pass over CLO's extra lines and keep
            # CLO's file only if nothing redundant is left.
            if "Kconfig" in os.path.basename(rel):
                sup += 1
                continue
            delta = makefile_delta(ack, clo,
                                   os.path.dirname(os.path.join(SRC, rel)))
            if not nb(delta):
                sup += 1
                continue
            merged = ack
            if not merged.endswith("\n"):
                merged += "\n"
            merged += ("\n# --- CLO soc-repo overlay additions "
                       "(restored by fix_kbuild.py) ---\n" + delta)
            if APPLY:
                with open(c, "w", encoding="utf-8",
                          errors="surrogateescape") as f:
                    f.write(merged)
            continue
        delta = kconfig_delta(ack, clo) if "Kconfig" in os.path.basename(rel) \
            else makefile_delta(ack, clo, os.path.dirname(os.path.join(SRC, rel)))
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
        k = normalize_includes(SRC)
        print(f"tree-root includes rewritten: {k}")
    if not APPLY:
        print("\n(dry run - pass --apply to write)")


if __name__ == "__main__":
    main()
