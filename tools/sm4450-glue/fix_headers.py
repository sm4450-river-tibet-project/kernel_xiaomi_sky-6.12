#!/usr/bin/env python3
"""Reconcile CLO overlay headers with ACK where ACK-only code needs symbols.

CLO's soc-repo overlay ships modified copies of a handful of headers. Where the
C file in our tree is ACK's version but the header is CLO's, the build fails on
symbols CLO removed. This restores just those symbols, keeping CLO's additions.

  python3 fix_headers.py            # report
  python3 fix_headers.py --apply    # patch
"""
import os
import re
import sys

ACK = os.path.expanduser("~/ack612")
SRC = os.path.expanduser("~/los/kernel/xiaomi/sky")
APPLY = "--apply" in sys.argv

# header -> symbols ACK defines that CLO dropped
NEEDED = {
    "include/linux/arm_ffa.h": [
        "FFA_FEAT_RXTX_MIN_SZ_MASK",
        "FFA_PARTITION_HYP_CREATE_VM",
        "FFA_PARTITION_HYP_DESTROY_VM",
        "FFA_VM_CREATION_MSG",
        "FFA_VM_DESTRUCTION_MSG",
        "FFA_SRC_ENDPOINT_MASK",
    ],
}

# header -> whole ACK function bodies CLO dropped, anchored on the line that
# precedes them in ACK (so we splice at the right place, not at EOF).
NEEDED_FUNCS = {
    "include/linux/arm_ffa.h": [
        # ffa.c is ACK's and calls this on two error paths.
        ("static inline int linux_errno_to_ffa(int errno)", "#endif /* _LINUX_ARM_FFA_H */"),
    ],
}

DEF = re.compile(r'^#define\s+([A-Za-z0-9_]+)\b')


def defines(text):
    """name -> the *whole* #define line (value included)."""
    out = {}
    for line in text.splitlines():
        m = DEF.match(line)
        if m:
            out[m.group(1)] = line
    return out


def main():
    for rel, syms in NEEDED.items():
        ack = open(os.path.join(ACK, rel), encoding="utf-8").read()
        cur_path = os.path.join(SRC, rel)
        cur = open(cur_path, encoding="utf-8").read()
        have = defines(cur)
        missing = [s for s in syms if s not in have]
        print("%s: %d/%d present, missing %d" % (rel, len(syms) - len(missing),
                                                 len(syms), len(missing)))
        if not missing:
            continue
        ack_defs = defines(ack)
        add = []
        for s in missing:
            if s in ack_defs:
                add.append(ack_defs[s])
                print("  + %s" % ack_defs[s].strip())
            else:
                print("  ! %s not in ACK either" % s)
        if not add or not APPLY:
            continue
        out = cur
        if not out.endswith("\n"):
            out += "\n"
        out += ("\n/* ACK symbols restored by fix_headers.py (CLO overlay dropped\n"
                " * them while the .c files here are ACK's) */\n" + "\n".join(add) + "\n")
        with open(cur_path, "w", encoding="utf-8") as f:
            f.write(out)
        print("  patched")

    # whole functions CLO dropped but our (ACK) .c files call
    for rel, funcs in NEEDED_FUNCS.items():
        ack = open(os.path.join(ACK, rel), encoding="utf-8").read()
        cur_path = os.path.join(SRC, rel)
        cur = open(cur_path, encoding="utf-8").read()
        for sig, anchor in funcs:
            if sig in cur:
                print("%s: %s already present" % (rel, sig.split("(")[0]))
                continue
            # pull the ACK function body: from its comment/sig line to the
            # closing brace that ends it.
            lines = ack.splitlines()
            start = next((i for i, l in enumerate(lines) if l.startswith(sig)), None)
            if start is None:
                print("  ! %s not found in ACK" % sig)
                continue
            end = start
            depth = 0
            started = False
            while end < len(lines):
                depth += lines[end].count("{") - lines[end].count("}")
                if "{" in lines[end]:
                    started = True
                if started and depth == 0:
                    break
                end += 1
            body = "\n".join(lines[start:end + 1])
            if anchor not in cur:
                print("  ! anchor %r missing in %s" % (anchor, rel))
                continue
            cur = cur.replace(
                anchor,
                "/* restored by fix_headers.py: CLO overlay dropped it, but the\n"
                " * .c files in this tree are ACK's and still call it */\n"
                + body + "\n\n" + anchor, 1)
            print("  + %s (%d lines)" % (sig.split("(")[0], end - start + 1))
        if APPLY:
            with open(cur_path, "w", encoding="utf-8") as f:
                f.write(cur)
            print("  patched funcs")


if __name__ == "__main__":
    main()
