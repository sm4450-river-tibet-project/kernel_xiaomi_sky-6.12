#!/usr/bin/env python3
"""Cross-check PRODUCT_PACKAGES entries reported missing against Android.bp state.

For every module name the build says does not exist, classify it:
  DISABLED  - a module with that name exists in Android.bp but is installable:false
              (our own doing; the source-built copy installs instead)
  ABSENT    - no module with that name exists at all in the vendor .bp
  OTHER     - exists and is installable, so the missing reason is something else

Read-only.
"""
import re
import sys

BP = "Android.bp"
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
                    yield text[m.start():j + 1]
                    break
            j += 1


def main():
    text = open(BP, encoding="utf-8").read()
    state = {}
    for body in blocks(text):
        for nm in NAME_RE.findall(body):
            state[nm] = "DISABLED" if OFF_RE.search(body) else "INSTALLABLE"

    wanted = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
    buckets = {"DISABLED": [], "ABSENT": [], "INSTALLABLE": []}
    for w in wanted:
        buckets[state.get(w, "ABSENT")].append(w)

    for k in ("DISABLED", "ABSENT", "INSTALLABLE"):
        print("%-11s %d" % (k, len(buckets[k])))
    print()
    for k in ("ABSENT", "INSTALLABLE"):
        if buckets[k]:
            print("--- %s ---" % k)
            for x in buckets[k]:
                print("  ", x)
    print()
    print("bp modules total: %d" % len(state))
    return 0


if __name__ == "__main__":
    sys.exit(main())
