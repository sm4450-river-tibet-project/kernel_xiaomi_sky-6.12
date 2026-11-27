#!/bin/bash
# Rebuild the sky kernel glue (ACK base + CLO soc-repo overlay) and optionally
# compile it.  Our kernel repo is the ACK android16-6.12 tree with CLO's qcom
# 6.12 overlay copied over it; the overlay ships delta-only build files, so a
# plain copy clobbers full ACK files.  fix_kbuild.py restores them.
#
#   bash ~/apply_merge.sh            # glue only
#   bash ~/apply_merge.sh --test     # glue + gki_defconfig parse
#   bash ~/apply_merge.sh --build    # glue + config + full Image/dtbs build
set -u
K=$HOME/los/kernel/xiaomi/sky
PRE=$HOME/los/prebuilts
CLANG=$PRE/clang/host/linux-x86/clang-r596125/bin
HOSTINC="-I$PRE/kernel-build-tools/linux-x86/include"
HOSTLIB="-L$PRE/kernel-build-tools/linux-x86/lib64 -Wl,-rpath,$PRE/kernel-build-tools/linux-x86/lib64"
CLO=https://git.codelinaro.org/api/v4/projects/60268/repository/files
REF=kernel.lnx.6.12.r70-rel
cd "$K" || exit 1
git checkout -- . || exit 1
python3 "$HOME/fix_kbuild.py" --apply

python3 - <<'EOF'
p = "scripts/Makefile.lib"
t = open(p).read()
old = "# If CONFIG_OF_ALL_DTBS is enabled, all DT blobs are built\ndtb-$(CONFIG_OF_ALL_DTBS)       += $(dtb-)\n\n"
new = ("# ponytail: dropped the legacy `dtb-$(CONFIG_OF_ALL_DTBS) += $(dtb-)` line --\n"
       "# with OF_ALL_DTBS unset it becomes `dtb- += $(dtb-)`, a self-referencing\n"
       "# recursive variable that aborts every build.\n\n")
if old in t:
    open(p, "w").write(t.replace(old, new, 1))
    print("patched scripts/Makefile.lib")
else:
    print("scripts/Makefile.lib: already patched or pattern moved")

# ACK's Makefile.build includes scripts/Makefile.dtbs, which owns dtb-y and
# prefixes it with $(obj).  CLO moved that logic into Makefile.lib *and* added
# a second addprefix block -- keeping both prefixes dtb-y twice.  Strip CLO's
# copy so only Makefile.dtbs does it.
t = open(p).read()
start = t.find("# --- CLO soc-repo overlay additions (restored by fix_kbuild.py) ---\nifdef need-dtbslist")
if start != -1:
    end = t.find("modkern_aflags = ", start)
    if end == -1:
        print("Makefile.lib: end marker not found, left alone")
    else:
        t = t[:start] + t[end:]
        open(p, "w").write(t)
        print("Makefile.lib: removed CLO's duplicate dtbs block")
else:
    print("Makefile.lib: CLO dtbs block already gone")
EOF

# CLO's Makefile fragments often end with an unconditional "obj-y += <dir>/"
# block listing subdirs ACK already adds under obj-$(CONFIG_...).  fix_kbuild.py
# drops those blocks; keeping them recurses twice and every .o links twice.


# scripts/Makefile.build must be ACK's.  CLO's 518-line copy drops
# `include scripts/Makefile.dtbs` and reads `-include include/config/auto.conf`
# (relative) instead of `$(objtree)/...`, which makes out-of-tree builds
# resolve targets like scripts/basic/scripts/basic/fixdep.
curl -sSL --max-time 120 \
  "https://raw.githubusercontent.com/aosp-mirror/kernel_common/android16-6.12/scripts/Makefile.build" \
  -o scripts/Makefile.build
echo "scripts/Makefile.build: $(wc -l < scripts/Makefile.build) lines (ACK ships 561)"

# scripts/Kbuild.include must be ACK's: CLO's copy calls `scripts/basic/fixdep`
# (relative) instead of `$(objtree)/scripts/basic/fixdep`, which breaks every
# out-of-tree build with "No rule to make target
# 'scripts/basic/scripts/basic/fixdep'".
curl -sSL --max-time 120 \
  "https://raw.githubusercontent.com/aosp-mirror/kernel_common/android16-6.12/scripts/Kbuild.include" \
  -o scripts/Kbuild.include
echo "scripts/Kbuild.include: $(wc -l < scripts/Kbuild.include) lines"
curl -sSL --max-time 120 \
  "https://raw.githubusercontent.com/aosp-mirror/kernel_common/android16-6.12/scripts/genksyms/parse.y" \
  -o scripts/genksyms/parse.y
echo "scripts/genksyms/parse.y: $(wc -l < scripts/genksyms/parse.y) lines (ACK ships 520)"

# CLO's overlay headers drop symbols the ACK .c files still use (arm_ffa.h
# lost the FFA VM-creation constants).  Restore just those.
python3 "$HOME/fix_headers.py" --apply

# CLO pins clang-r536225; the tree only has r596125.  The newer clang adds
# warnings that -Werror turns into hard errors in untouched upstream code,
# so drop WERROR for this bring-up build.
#
# DEBUG_INFO_BTF is disabled too: the merged config exceeds BTF's 4096-entry
# per-CPU variable limit and `BTFIDS vmlinux` dies with "load BTF from vmlinux:
# Invalid argument" after a successful link.  Nothing on the device consumes
# vmlinux BTF; pahole-style introspection is not needed for a boot test.
python3 - <<'EOF'
p = "arch/arm64/configs/gki_defconfig"
t = open(p).read()
add = []
if "\n# CONFIG_WERROR is not set" not in t:
    add.append("# CONFIG_WERROR is not set")
if "\n# CONFIG_DEBUG_INFO_BTF is not set" not in t:
    add.append("# CONFIG_DEBUG_INFO_BTF is not set")
if add:
    open(p, "w").write(t.rstrip("\n") + "\n\n" + "\n".join(add) + "\n")
    print("gki_defconfig: " + ", ".join(a.lstrip("# ") for a in add))
else:
    print("gki_defconfig: WERROR/BTF already disabled")
EOF

cd arch/arm64/boot/dts || exit 1
rm -rf vendor
ln -s ../../../../../sky-devicetrees vendor || exit 1
echo "dts/vendor -> $(readlink vendor)"

[ "${1:-}" = "--test" ] || [ "${1:-}" = "--build" ] || exit 0

export PATH=$CLANG:$PRE/build-tools/linux-x86/bin:$PATH
cd "$K" || exit 1
rm -rf "$HOME/kvtest"
make ARCH=arm64 O="$HOME/kvtest" LLVM=1 HOSTCFLAGS="$HOSTINC" HOSTLDFLAGS="$HOSTLIB" \
     gki_defconfig > "$HOME/kvtest.log" 2>&1
echo "DEFCONFIG_EXIT=$?"
(cd "$HOME/kvtest" && "$K/scripts/kconfig/merge_config.sh" -m -O "$HOME/kvtest" \
     "$HOME/kvtest/.config" "$K/arch/arm64/configs/vendor/parrot_perf.config") \
     > "$HOME/kmerge.log" 2>&1
make ARCH=arm64 O="$HOME/kvtest" LLVM=1 HOSTCFLAGS="$HOSTINC" HOSTLDFLAGS="$HOSTLIB" \
     olddefconfig > "$HOME/kolddef.log" 2>&1
echo "OLDDEFCONFIG_EXIT=$?  $(grep -m1 '^CONFIG_ARCH_RAVELIN=' "$HOME/kvtest/.config")"
echo "total CONFIG_: $(grep -c '^CONFIG_' "$HOME/kvtest/.config")"
[ "${1:-}" = "--build" ] || exit 0

setsid nohup make ARCH=arm64 O="$HOME/kvtest" LLVM=1 HOSTCFLAGS="$HOSTINC" \
     HOSTLDFLAGS="$HOSTLIB" -j96 Image dtbs > "$HOME/kbuild.log" 2>&1 < /dev/null &
sleep 2
echo "build started -> ~/kbuild.log"
