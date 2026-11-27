#!/usr/bin/env python3
"""Find duplicate install targets in out/soong/installs-*.mk.

kati fails with "overriding commands for target X, previously defined at Y"
when two modules install the same file. The installs .mk lists every one, so
this finds them all at once instead of one build at a time.

Read-only. Run from the vendor repo root (or pass the installs path).
"""
import re
import sys
from collections import defaultdict

INSTALLS = "../../../out/soong/installs-lineage_sky.mk"
RULE_RE = re.compile(r"^(out/target/product/\S+?):\s+(\S+)")


def main(argv):
    path = argv[0] if argv else INSTALLS
    targets = defaultdict(list)
    with open(path, encoding="utf-8", errors="replace") as f:
        for ln in f:
            m = RULE_RE.match(ln)
            if m:
                targets[m.group(1)].append(m.group(2))

    dupes = {t: srcs for t, srcs in targets.items() if len(srcs) > 1}
    print("install targets: %d" % len(targets))
    print("DUPLICATED targets: %d" % len(dupes))

    # classify: is one side a vendor prebuilt and the other a source build?
    vendor_pb = 0
    for t, srcs in sorted(dupes.items()):
        tag = []
        for s in srcs:
            if "/vendor/xiaomi/sm4450-common/" in s:
                tag.append("PREBUILT")
            else:
                tag.append("source")
        if "PREBUILT" in tag and "source" in tag:
            vendor_pb += 1
        print("\n%s" % t)
        for s, g in zip(srcs, tag):
            print("   [%s] %s" % (g, s[:150]))
    print("\nprebuilt-vs-source duplicates: %d" % vendor_pb)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
