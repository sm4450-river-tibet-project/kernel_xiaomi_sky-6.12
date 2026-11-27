#!/usr/bin/env python3
"""Auto-repair composite objects that have `<name>-objs += ...` but no
`obj-$(CONFIG_X) += <name>.o` line.

The CLO soc-repo overlay ships Makefile *fragments*: they list a module's
member objects (`qcom_ipc_logging-objs += ipc_logging.o`) but the matching
`obj-... += qcom_ipc_logging.o` line lived in a part of CLO's Makefile the
fragment extraction dropped.  Nothing builds those modules, so every consumer
fails at modpost with `"symbol" [foo.ko] undefined!`.

Rather than chase symbols one at a time, this script:
  1. reads the modpost errors from a build log,
  2. finds which .c file exports each symbol,
  3. finds which composite object that .c belongs to,
  4. checks whether any obj- line already builds that composite,
  5. appends the missing obj- line, inferring the CONFIG from the Kconfig
     that guards the composite (or from the composite name).

Usage: fix_missing_obj.py <build-log> [--apply]
"""
import os
import re
import subprocess
import sys

SRC = os.path.expanduser("~/los/kernel/xiaomi/sky")


def modpost_symbols(logpath):
    """(symbol, consumer) pairs from `ERROR: modpost: "sym" [file] undefined!`."""
    out = []
    pat = re.compile(r'ERROR: modpost: "([^"]+)" \[([^\]]+)\] undefined!')
    try:
        for line in open(logpath, encoding="utf-8", errors="replace"):
            m = pat.search(line)
            if m:
                out.append((m.group(1), m.group(2)))
    except OSError:
        pass
    return out


def find_exporter(sym):
    """Relative path of the .c file that EXPORT_SYMBOLs `sym`."""
    for pat in ("EXPORT_SYMBOL_GPL(%s)" % sym, "EXPORT_SYMBOL(%s)" % sym):
        r = subprocess.run(
            ["grep", "-rl", "--include=*.c", pat, "."],
            cwd=SRC, capture_output=True, text=True)
        for line in r.stdout.split():
            return line.lstrip("./")
    return None


def composite_owner(cfile):
    """(Makefile, composite name) that builds `cfile`, or None."""
    d = os.path.dirname(cfile)
    base = os.path.basename(cfile)[:-2] + ".o"
    for mkname in ("Makefile", "Kbuild"):
        mk = os.path.join(d, mkname) if d else mkname
        full = os.path.join(SRC, mk)
        if not os.path.exists(full):
            continue
        t = open(full, encoding="utf-8", errors="surrogateescape").read()
        # `<name>-objs| -y += ... base ...`
        for m in re.finditer(r'^([A-Za-z0-9_\-]+)-(?:objs|y)\s*[:+]?=\s*(.*)$',
                             t, re.M):
            if re.search(r'\b%s\b' % re.escape(base), m.group(2)):
                return mk, m.group(1), t
    return None


def infer_config(name, mkdir):
    """CONFIG_ symbol that guards `name`, read from the directory's Kconfig.

    CLO names the composite object after the module, so the Kconfig entry
    usually carries the same name: `qcom_ipc_logging` -> CONFIG_IPC_LOGGING,
    `qcom_dma_heaps` -> CONFIG_QCOM_DMABUF_HEAPS.  We look for a config whose
    name shares a long prefix/suffix with the composite before falling back to
    a literal transliteration.
    """
    knames = []
    kpath = os.path.join(SRC, mkdir, "Kconfig")
    if os.path.exists(kpath):
        try:
            kt = open(kpath, encoding="utf-8", errors="surrogateescape").read()
            knames = re.findall(r'^config\s+([A-Z0-9_]+)\s*$', kt, re.M)
        except OSError:
            knames = []
    want = name.upper().replace("-", "_")
    if want in knames:
        return "CONFIG_" + want
    # longest common token overlap
    best, score = None, 0
    for k in knames:
        common = 0
        for a, b in zip(want.split("_"), k.split("_")):
            if a != b:
                break
            common += 1
        if common > score:
            best, score = k, common
    if best and score >= 1:
        return "CONFIG_" + best
    return "CONFIG_" + want


def config_enabled(cfg):
    """True when `cfg` appears in the build .config at all (set or unset)."""
    path = os.path.expanduser("~/kvtest/.config")
    try:
        t = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return True
    name = cfg[len("CONFIG_"):]
    return re.search(r'^(CONFIG_%s=|# CONFIG_%s is not set)'
                     % (re.escape(name), re.escape(name)), t, re.M) is not None


def main():
    if len(sys.argv) < 2:
        print("usage: fix_missing_obj.py <build-log> [--apply]")
        return 2
    apply = "--apply" in sys.argv
    syms = modpost_symbols(sys.argv[1])
    if not syms:
        print("no modpost undefined symbols found")
        return 0

    seen = set()
    for sym, consumer in syms:
        if sym in seen:
            continue
        seen.add(sym)
        cfile = find_exporter(sym)
        if not cfile:
            print("?? %-40s exporter not found (%s)" % (sym, consumer))
            continue
        owner = composite_owner(cfile)
        if not owner:
            print("?? %-40s %s has no composite owner" % (sym, cfile))
            continue
        mk, name, text = owner
        if re.search(r'^obj-[^\s]*\s*\+?=.*\b%s\.o\b' % re.escape(name),
                     text, re.M):
            print("ok %-40s %s already built" % (sym, name))
            continue
        cfg = infer_config(name, os.path.dirname(mk) or ".")
        if not config_enabled(cfg):
            print("-- %-40s %s not in .config, skipping" % (sym, cfg))
            continue
        print("%s %-40s %s -> %s (%s)"
              % ("ADD" if apply else "would add", sym, name, cfg, mk))
        if apply:
            with open(os.path.join(SRC, mk), "a",
                      encoding="utf-8", errors="surrogateescape") as f:
                f.write("obj-$(%s) += %s.o\n" % (cfg, name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
