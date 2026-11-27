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
#
# The same "take ACK's copy outright" rule covers scripts/Kbuild.include,
# scripts/genksyms/parse.y and the four drivers/block/zram files -- see
# ACK_OWNED below.  They all come from the local ~/ack612 checkout, which is
# the same android16-6.12 tree the raw.githubusercontent URLs would give us,
# but without depending on network access mid-build.
ACK=$HOME/ack612
ACK_OWNED="
scripts/Makefile.build
scripts/Kbuild.include
scripts/genksyms/parse.y
drivers/block/zram/zcomp.c
drivers/block/zram/zcomp.h
drivers/block/zram/zram_drv.c
drivers/block/zram/zram_drv.h
include/linux/io-pgtable-arm.h
drivers/iommu/arm/arm-smmu-v3/pkvm/io-pgtable-arm.c
scripts/dtc/util.c
drivers/usb/gadget/function/f_ncm.c
security/selinux/hooks.c
drivers/usb/gadget/function/f_mass_storage.c
drivers/usb/gadget/function/f_fs.c
drivers/hwtracing/stm/core.c
drivers/hwtracing/stm/ftrace.c
"
for f in $ACK_OWNED; do
    if [ -f "$ACK/$f" ]; then
        cp -f "$ACK/$f" "$f" || echo "FAILED to copy $f from ACK"
        echo "ACK-owned: $f ($(wc -l < "$f") lines)"
    else
        echo "MISSING in ACK: $f"
    fi
done

# kernel/sched/walt/Kconfig is only reachable through Kconfig.msm, and
# Kconfig.msm is a standalone CLO entry point that nothing in the ACK tree
# sources -- so CONFIG_SCHED_WALT never existed as a symbol, while
# parrot_perf.config asks for it and drivers/soc/qcom/hung_task_enh.c uses
# struct walt_task_struct (which include/linux/sched/walt.h only defines
# under IS_ENABLED(CONFIG_SCHED_WALT)).  Anchor it to init/Kconfig, which the
# root Kconfig sources unconditionally; kernel/sched/Kconfig is a CLO-only
# file with no ACK twin, so nothing else pulls it in.
python3 - <<'EOF'
p = "init/Kconfig"
t = open(p).read()
if "sched/walt/Kconfig" not in t:
    t = t.rstrip("\n") + (
        "\n\n# CLO's WALT scheduler lives in kernel/sched/walt/ and is normally\n"
        "# pulled in via Kconfig.msm, which this ACK base never sources.\n"
        'source "$(KCONFIG_EXT_PREFIX)kernel/sched/walt/Kconfig"\n')
    open(p, "w").write(t)
    print("init/Kconfig: sourced walt/Kconfig")
else:
    print("init/Kconfig: walt already sourced")
EOF

# CLO's drivers/iommu/arm/arm-smmu/Makefile adds
#   arm_smmu-$(CONFIG_ARM_SMMU_NVIDIA) += arm-smmu-nvidia.o
# while line 4 already puts arm-smmu-nvidia.o in arm_smmu-objs unconditionally,
# so with the config on the object links twice ("redefinition of
# nvidia_smmu_impl_init").  Drop the conditional line; the unconditional one
# is ACK's.
python3 - <<'EOF'
p = "drivers/iommu/arm/arm-smmu/Makefile"
t = open(p).read()
bad = "arm_smmu-$(CONFIG_ARM_SMMU_NVIDIA) += arm-smmu-nvidia.o\n"
if bad in t:
    open(p, "w").write(t.replace(bad, "", 1))
    print("arm-smmu/Makefile: dropped the duplicate nvidia object line")
else:
    print("arm-smmu/Makefile: no duplicate nvidia line")
EOF

# WALT must be built in, not modular: struct walt_task_struct is defined in
# include/linux/sched/walt.h under IS_ENABLED(CONFIG_SCHED_WALT), and the
# in-tree users (drivers/soc/qcom/hung_task_enh.c) need the full definition
# at compile time.  parrot_perf.config ships it as =m.
python3 - <<'EOF'
p = "arch/arm64/configs/vendor/parrot_perf.config"
t = open(p).read()
t2 = t.replace("\nCONFIG_SCHED_WALT=m\n", "\nCONFIG_SCHED_WALT=y\n")
t2 = t2.replace("\nCONFIG_SCHED_WALT_DEBUG=m\n",
                "\n# CONFIG_SCHED_WALT_DEBUG is not set\n")
if t2 != t:
    open(p, "w").write(t2)
    print("parrot_perf.config: SCHED_WALT built in")
else:
    print("parrot_perf.config: SCHED_WALT already built in")
EOF

# CLO's socinfo.c drives the LeapPart feature codes (SOCINFO_FC_LA..LL), which
# only exist in CLO's include/soc/qcom/socinfo.h.  ACK's
# include/linux/soc/qcom/socinfo.h defines a shorter enum feature_code that
# stops at SOCINFO_FC_AH, so the include has to point at CLO's header.  Both
# guard macros differ (__SOC_QCOM_SOCINFO_H__ vs __QCOM_SOCINFO_H__), so the
# SMEM constants ACK's header carries stay available.
python3 - <<'EOF'
p = "drivers/soc/qcom/socinfo.c"
t = open(p).read()
old = "#include <linux/soc/qcom/socinfo.h>"
new = "#include <soc/qcom/socinfo.h>"
if new not in t:
    n = t.count(old)
    t = t.replace(old, new)
    open(p, "w").write(t)
    print("socinfo.c: %d include(s) repointed to <soc/qcom/socinfo.h>" % n)
else:
    print("socinfo.c: already repointed")
EOF

# CLO's arm-smmu.h gates nvidia_smmu_impl_init behind
# IS_ENABLED(CONFIG_ARM_SMMU_NVIDIA) and supplies a static inline stub when
# the option is off, but ACK's Makefile lists arm-smmu-nvidia.o in
# arm_smmu-objs unconditionally -- so the real definition collides with the
# stub.  CLO's Kconfig makes ARM_SMMU_NVIDIA depend on TEGRA_MC, which this
# SoC never enables.  Build the file only when the option is on.
python3 - <<'EOF'
p = "drivers/iommu/arm/arm-smmu/Makefile"
t = open(p).read()
old = "arm_smmu-objs += arm-smmu.o arm-smmu-impl.o arm-smmu-nvidia.o"
new = ("arm_smmu-objs += arm-smmu.o arm-smmu-impl.o\n"
       "arm_smmu-$(CONFIG_ARM_SMMU_NVIDIA) += arm-smmu-nvidia.o")
if old in t:
    open(p, "w").write(t.replace(old, new))
    print("arm-smmu/Makefile: arm-smmu-nvidia.o is conditional")
elif new in t:
    print("arm-smmu/Makefile: already conditional")
else:
    print("arm-smmu/Makefile: WARNING pattern not found")
EOF

# CLO's Makefile fragment builds qti-fixed-regulator.o from
# qti_fixed_regulator.c, but that source file is not part of the soc-repo
# overlay (it lives in a separate techpack repo upstream) and nothing in the
# device tree needs it -- parrot_perf.config merely asks for the module.
# Asking for a module whose source does not exist breaks `make modules` with
# "No rule to make target 'drivers/regulator/qti_fixed_regulator.o'".
python3 - <<'EOF'
p = "drivers/regulator/Makefile"
t = open(p).read()
drop = [
    "obj-$(CONFIG_REGULATOR_QTI_FIXED_VOLTAGE) += qti-fixed-regulator.o\n",
    "qti-fixed-regulator-objs += qti_fixed_regulator.o\n",
    "CFLAGS_qti_fixed_regulator.o += -DQTI_FIXED_REGULATOR\n",
]
removed = 0
for line in drop:
    if line in t:
        t = t.replace(line, "")
        removed += 1
if removed:
    open(p, "w").write(t)
    print("regulator/Makefile: dropped %d qti-fixed-regulator line(s) "
          "(source absent from overlay)" % removed)
else:
    print("regulator/Makefile: already clean")
EOF

# CLO's qcom_tzmem.h declares `enum bridge_owner` inside
# `#if IS_ENABLED(CONFIG_QCOM_TZMEM_MODE_SHMBRIDGE)` but also uses it in the
# `#else` branch's static inline stub, so with the mode off the enum is
# undefined and qcom_scm.c/qcom_tzmem.c/qtee_shmbridge.c all fail with
# "variable has incomplete type 'enum bridge_owner'" and "use of undeclared
# identifier 'OTHERS'".  Hoist the enum above the #if.
python3 - <<'EOF'
p = "drivers/firmware/qcom/qcom_tzmem.h"
t = open(p).read()
enum_block = ("enum bridge_owner {\n"
              "\t/**< Bridge is owned by tzmem/shmbridge. */\n"
              "\tSELF = 1,\n"
              "\t/**< Bridge is owned by other users. */\n"
              "\tOTHERS,\n"
              "};\n"
              "\n")
anchor = "#if IS_ENABLED(CONFIG_QCOM_TZMEM_MODE_SHMBRIDGE)\n"
if anchor in t and enum_block in t:
    t = t.replace(enum_block, "", 1)
    t = t.replace(anchor, enum_block + anchor, 1)
    open(p, "w").write(t)
    print("qcom_tzmem.h: enum bridge_owner hoisted above the #if")
elif t.find(enum_block) < t.find(anchor):
    print("qcom_tzmem.h: enum already hoisted")
else:
    print("qcom_tzmem.h: WARNING pattern not found")
EOF

# CLO systematically rewrites local `#include "security.h"` to
# `#include <linux/security.h>` inside security/selinux.  Those are two
# different headers; restoring the local form fixes the ss/ subtree.
python3 "$HOME/fix_local_includes.py" --apply

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
     HOSTLDFLAGS="$HOSTLIB" -j96 Image dtbs modules > "$HOME/kbuild.log" 2>&1 < /dev/null &
sleep 2
echo "build started -> ~/kbuild.log (Image + dtbs + modules)"
