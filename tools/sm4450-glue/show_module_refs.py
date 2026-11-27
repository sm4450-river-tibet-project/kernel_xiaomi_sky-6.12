#!/usr/bin/env python3
"""Show shared_libs/installable state for modules matching a substring.

Read-only diagnostic. Run from the vendor repo root.
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
                    yield text[m.start():j + 1]
                    break
            j += 1


def main(argv):
    needles = argv or ["AGMIPC", "hardware.pal"]
    text = open(BP, encoding="utf-8").read()
    for body in blocks(text):
        nm = re.search(r'\bname:\s*"([^"]+)"', body)
        if not nm:
            continue
        if not any(n in nm.group(1) for n in needles):
            continue
        print(nm.group(1))
        print("   installable: false" if "installable: false" in body else "   installable: YES")
        for m in re.finditer(r"shared_libs:\s*\[(.*?)\]", body, re.S):
            libs = re.findall(r'"([^"]+)"', m.group(1))
            hit = [x for x in libs if any(n in x for n in needles)]
            if hit:
                print("   shared_libs hit:", hit)
        for m in re.finditer(r"required:\s*\[(.*?)\]", body, re.S):
            libs = re.findall(r'"([^"]+)"', m.group(1))
            hit = [x for x in libs if any(n in x for n in needles)]
            if hit:
                print("   required hit:", hit)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
