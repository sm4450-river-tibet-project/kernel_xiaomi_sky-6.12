#!/usr/bin/env python3
"""Restore local includes that CLO rewrote to <linux/...> in security/selinux.

The CLO soc-repo overlay was extracted from a tree with a different include
layout, so it "normalizes" local includes to the <linux/...> form.  That is
actively wrong for security/selinux: the subtree has its own include/ dir
(security.h, objsec.h, ima.h, audit.h) and those headers are completely
different files from anything of the same name under include/linux/.
Resolving the angle form successfully therefore proves nothing.

The rewrite is detected by diffing against ACK's twin of each file: if ACK
wrote `#include "foo.h"` and CLO wrote `#include <linux/foo.h>`, restore the
local form.  Scope is deliberately limited to security/selinux/ because a
tree-wide restorer over-corrects (43 errors) -- plenty of other subsystems
legitimately want <linux/security.h> and friends.

Run with --apply to rewrite; without it, report only.
"""
import os
import re
import subprocess
import sys

SRC = os.path.expanduser("~/los/kernel/xiaomi/sky")
ACK = os.path.expanduser("~/ack612")
APPLY = "--apply" in sys.argv
PREFIX = "security/selinux/"


def local_header(rel, base):
    """Path of the subtree's own `base`, relative to the includer."""
    here = os.path.dirname(rel)
    for cand in (os.path.join(SRC, PREFIX, "include", base),
                 os.path.join(SRC, here, base)):
        if os.path.exists(cand):
            return os.path.relpath(cand, os.path.join(SRC, here)) \
                .replace(os.sep, "/")
    return None


def main():
    if not os.path.isdir(SRC):
        print("ERROR: %s missing" % SRC)
        return 1

    files = subprocess.run(["git", "ls-files", "*.c", "*.h"], cwd=SRC,
                           capture_output=True, text=True).stdout.split()
    fixed = 0
    touched = []

    for rel in files:
        if not rel.startswith(PREFIX):
            continue
        ack = os.path.join(ACK, rel)
        if not os.path.exists(ack):
            continue
        try:
            text = open(os.path.join(SRC, rel), encoding="utf-8",
                        errors="surrogateescape").read()
            atext = open(ack, encoding="utf-8",
                         errors="surrogateescape").read()
        except OSError:
            continue
        if text == atext or "<linux/" not in text:
            continue

        # Basenames ACK included locally, that CLO turned into <linux/x>.
        ack_local = set(re.findall(r'^\s*#\s*include\s+"([^"/]+)"',
                                   atext, re.M))
        rewritten = {}
        for base in ack_local:
            if "<linux/%s>" % base not in text:
                continue
            # Prefer the exact spelling ACK used; the build passes
            # -I security/selinux/include, so the bare name resolves.
            rewritten[base] = base if os.path.exists(
                os.path.join(SRC, PREFIX, "include", base)) \
                else local_header(rel, base)
            if not rewritten[base]:
                del rewritten[base]
        if not rewritten:
            continue

        out = []
        seen = set()
        changed = False
        for line in text.splitlines(keepends=True):
            nl = "\n" if line.endswith("\n") else ""
            body = line[:-1] if nl else line
            m = re.match(r'^(\s*#\s*include\s+)<linux/([^>]+)>(.*)$', body)
            if m and m.group(2) in rewritten:
                newline = '%s"%s"%s%s' % (m.group(1), rewritten[m.group(2)],
                                          m.group(3), nl)
                changed = True
                fixed += 1
                # Two different CLO includes can collapse onto the same local
                # header; keep the first, drop the duplicate.
                if newline.strip() in seen:
                    continue
                seen.add(newline.strip())
                out.append(newline)
            else:
                if body.strip().startswith("#include"):
                    seen.add(body.strip())
                out.append(line)
        if changed:
            touched.append(rel)
            if APPLY:
                open(os.path.join(SRC, rel), "w", encoding="utf-8",
                     errors="surrogateescape").write("".join(out))

    print("selinux local includes restored: %d across %d files"
          % (fixed, len(touched)))
    for t in touched:
        print("  " + t)
    return 0


if __name__ == "__main__":
    sys.exit(main())
