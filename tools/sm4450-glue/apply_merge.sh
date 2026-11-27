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

# CLO's Makefile fragments define composite objects (`<name>-objs += ...`)
# without ever adding the `obj-$(CONFIG_...) += <name>.o` line that would
# build them.  The modules then never get compiled, and every consumer fails
# at modpost with `"symbol" [foo.ko] undefined!`.  Restore the missing
# targets.  Each entry is: <Makefile>|<obj name>|<config>|<default member>
python3 - <<'EOF'
import os, re
MISSING = [
    ("kernel/trace/Makefile", "qcom_ipc_logging", "CONFIG_IPC_LOGGING"),
    ("drivers/dma-buf/heaps/Makefile", "qcom_dma_heaps",
     "CONFIG_QCOM_DMABUF_HEAPS"),
    ("drivers/pci/controller/Makefile", "pci-msm-drv", "CONFIG_PCI_MSM"),
    ("sound/usb/Makefile", "snd-usb-audio-qmi", "CONFIG_SND_USB_AUDIO_QMI"),
    ("net/qrtr/Makefile", "qrtr-gunyah", "CONFIG_QRTR_GUNYAH"),
    ("net/qrtr/Makefile", "qrtr-genpool", "CONFIG_QRTR_GENPOOL"),
    ("drivers/soc/qcom/Makefile", "minidump", "CONFIG_QCOM_MINIDUMP"),
    ("drivers/power/supply/Makefile", "qti-battery-charger",
     "CONFIG_QTI_BATTERY_CHARGER"),
    ("drivers/virt/gunyah/Makefile", "gh_rm_drv", "CONFIG_GUNYAH"),
    ("drivers/virt/gunyah/Makefile", "gunyah_loader", "CONFIG_GUNYAH"),
    ("drivers/remoteproc/Makefile", "rproc_qcom_common",
     "CONFIG_REMOTEPROC"),
    ("drivers/iommu/Makefile", "qcom_iommu_util", "CONFIG_QCOM_IOMMU_UTIL"),
    ("drivers/iommu/Makefile", "qcom_iommu_debug", "CONFIG_QCOM_IOMMU_DEBUG"),
]
for path, name, cfg in MISSING:
    if not os.path.exists(path):
        continue
    t = open(path, encoding="utf-8", errors="surrogateescape").read()
    if re.search(r'^obj-[^\s]*\s*\+?=.*\b%s\.o\b' % re.escape(name), t, re.M):
        print("%s: %s already has an obj- line" % (path, name))
        continue
    if not (("%s-objs" % name) in t or ("%s-y" % name) in t):
        print("%s: %s has no -objs definition, skipping" % (path, name))
        continue
    with open(path, "a", encoding="utf-8", errors="surrogateescape") as f:
        f.write('obj-$(%s) += %s.o\n' % (cfg, name))
    print("%s: added obj-$(%s) += %s.o" % (path, cfg, name))

# mhi_device_ioctl lives in drivers/bus/mhi/host/misc.c but misc.o was never
# added to mhi-objs, so mhi_dev_uci.ko and friends link against a symbol
# nothing provides.
p = "drivers/bus/mhi/host/Makefile"
if os.path.exists(p):
    t = open(p, encoding="utf-8", errors="surrogateescape").read()
    if "misc.o" not in t and os.path.exists("drivers/bus/mhi/host/misc.c"):
        t = re.sub(r'^(mhi-objs\s*[:+]?=\s*)(.*)$',
                   lambda m: m.group(1) + m.group(2).rstrip() + " misc.o",
                   t, count=1, flags=re.M)
        open(p, "w", encoding="utf-8", errors="surrogateescape").write(t)
        print("mhi: misc.o added to mhi-objs")
EOF

# qtee_shmbridge.c (built into qcom-scm.ko via CONFIG_QTEE_SHM_BRIDGE=y)
# calls qcom_tzmem_get_status(), but qcom_tzmem.c is built as its own module
# (CONFIG_QCOM_TZMEM=m) and the function is not exported -- modpost reports
# it undefined.  Export it so the cross-module reference resolves.
python3 - <<'EOF'
import os
p = "drivers/firmware/qcom/qcom_tzmem.c"
if os.path.exists(p):
    t = open(p, encoding="utf-8", errors="surrogateescape").read()
    fn = "bool qcom_tzmem_get_status(void)"
    if fn in t and "EXPORT_SYMBOL_GPL(qcom_tzmem_get_status)" not in t:
        # insert the export right after the function's closing brace
        i = t.index(fn)
        j = t.index("\n}\n", i) + 3
        t = t[:j] + "EXPORT_SYMBOL_GPL(qcom_tzmem_get_status);\n" + t[j:]
        open(p, "w", encoding="utf-8", errors="surrogateescape").write(t)
        print("qcom_tzmem.c: exported qcom_tzmem_get_status")
EOF

# GUNYAH is builtin while every GH_* member is =m.  A composite object built
# into vmlinux (obj-$(CONFIG_GUNYAH) += gunyah_loader.o with GUNYAH=y) drops
# members listed under `gunyah_loader-$(CONFIG_GH_...)` when that config is
# =m, because the conditional variable becomes `gunyah_loader-m`, which only
# applies to module builds.  Result: vmlinux links with gh_secure_vm_loader,
# gh_proxy_sched, gh_dbl, gh_msgq and gh_vcpu_mgr symbols missing.  Making
# GUNYAH a module puts every member on the same side of the boundary.
python3 - <<'EOF'
import os, re
p = "arch/arm64/configs/vendor/parrot_perf.config"
if os.path.exists(p):
    t = open(p, encoding="utf-8", errors="surrogateescape").read()
    if re.search(r'^CONFIG_GUNYAH=', t, re.M):
        new = re.sub(r'^CONFIG_GUNYAH=.*$', 'CONFIG_GUNYAH=m', t, flags=re.M)
    else:
        new = t + ("\n" if not t.endswith("\n") else "") + "CONFIG_GUNYAH=m\n"
    if new != t:
        open(p, "w", encoding="utf-8", errors="surrogateescape").write(new)
        print("parrot_perf.config: CONFIG_GUNYAH=m (overrides gki_defconfig =y)")
EOF

# USB_XHCI_SIDEBAND is a bool, but the config fragment carries `=m`, which
# merge_config.sh discards as an invalid value -- the option ends up unset and
# xhci-sideband.o is never compiled.  snd-usb-audio-qmi.ko needs its exports.
python3 - <<'EOF'
import os, re
p = "arch/arm64/configs/vendor/parrot_perf.config"
if os.path.exists(p):
    t = open(p, encoding="utf-8", errors="surrogateescape").read()
    new = re.sub(r'^CONFIG_USB_XHCI_SIDEBAND=.*$', 'CONFIG_USB_XHCI_SIDEBAND=y',
                 t, flags=re.M)
    if new != t:
        open(p, "w", encoding="utf-8", errors="surrogateescape").write(new)
        print("parrot_perf.config: CONFIG_USB_XHCI_SIDEBAND=m -> =y (bool)")
EOF

# CONFIG_USB_DWC3_MSM=m builds dwc3-msm.ko, which exports msm_ep_* and
# dwc3_msm_get_qsram, but the composite object has -objs lines and no obj-.
python3 - <<'EOF'
import os, re
path, name, cfg = "drivers/usb/dwc3/Makefile", "dwc3-msm", "CONFIG_USB_DWC3_MSM"
if os.path.exists(path):
    t = open(path, encoding="utf-8", errors="surrogateescape").read()
    if not re.search(r'^obj-[^\s]*\s*\+?=.*\b%s\.o\b' % re.escape(name), t, re.M):
        if ("%s-objs" % name) in t or ("%s-y" % name) in t:
            if not t.endswith("\n"):
                t += "\n"
            t += "obj-$(%s) += %s.o\n" % (cfg, name)
            open(path, "w", encoding="utf-8", errors="surrogateescape").write(t)
            print("%s: added obj-$(%s) += %s.o" % (path, cfg, name))
        else:
            print("%s: %s has no -objs definition" % (path, name))
    else:
        print("%s: %s already has an obj- line" % (path, name))
EOF

# usb_f_qdss and dwc3-msm are composite objects with -objs lines but no obj-
# line, exactly the CLO fragment defect this project keeps hitting.
python3 - <<'EOF'
import os, re
adds = [
    ("drivers/usb/gadget/function/Makefile", "usb_f_qdss", "CONFIG_USB_F_QDSS"),
]
for path, name, cfg in adds:
    if not os.path.exists(path):
        continue
    t = open(path, encoding="utf-8", errors="surrogateescape").read()
    if re.search(r'^obj-[^\s]*\s*\+?=.*\b%s\.o\b' % re.escape(name), t, re.M):
        print("%s: %s already has an obj- line" % (path, name))
        continue
    if ("%s-objs" % name) not in t:
        print("%s: %s has no -objs definition, skipping" % (path, name))
        continue
    if not t.endswith("\n"):
        t += "\n"
    t += "obj-$(%s) += %s.o\n" % (cfg, name)
    open(path, "w", encoding="utf-8", errors="surrogateescape").write(t)
    print("%s: added obj-$(%s) += %s.o" % (path, cfg, name))
EOF

# gh_proxy_sched.c and gh_vcpu_mgr.c both EXPORT_SYMBOL_GPL(gh_poll_vcpu_run).
# gh_vcpu_mgr.o is a standalone module that nothing references and duplicates
# gh_proxy_sched's implementation, so it is disabled in the config fragment
# below.  gh_proxy_sched.o belongs with gh_main.o in gunyah_loader: gh_main.c
# calls gh_proxy_sched_init/exit, gh_get_nr_vcpus and gh_wakeup_all_vcpus,
# which only exist in gh_proxy_sched.c, so they must link into one module.
python3 - <<'EOF'
import os, re
p = "drivers/virt/gunyah/Makefile"
if os.path.exists(p):
    t = open(p, encoding="utf-8", errors="surrogateescape").read()
    if "gunyah_loader-$(CONFIG_GH_PROXY_SCHED) += gh_proxy_sched.o" not in t:
        t = re.sub(r'^obj-\$\(CONFIG_GH_PROXY_SCHED\) \+= gh_proxy_sched\.o\n',
                   '', t, flags=re.M)
        if not t.endswith("\n"):
            t += "\n"
        t += "gunyah_loader-$(CONFIG_GH_PROXY_SCHED) += gh_proxy_sched.o\n"
        open(p, "w", encoding="utf-8", errors="surrogateescape").write(t)
        print("gunyah Makefile: gh_proxy_sched.o back inside gunyah_loader")
    else:
        print("gunyah Makefile: gh_proxy_sched already in gunyah_loader")
EOF

# CLO's Makefile.modfinal drops the `targets +=` / `$(modules): %.ko: ...`
# rule that precedes the recipe, so make dies with "recipe commences before
# first target" at line 103.  ACK's copy is the working one.
python3 - <<'EOF'
import os, shutil
p = "scripts/Makefile.modfinal"
ack = os.path.expanduser("~/ack612/scripts/Makefile.modfinal")
if os.path.exists(p) and os.path.exists(ack):
    if open(p, "rb").read() != open(ack, "rb").read():
        shutil.copyfile(ack, p)
        print("scripts/Makefile.modfinal: restored ACK's copy")
    else:
        print("scripts/Makefile.modfinal: already ACK's")
EOF

# rust/bindings/lib.rs is a pure type crate: every item is a repr or a type
# alias, so rustc emits an object with no .text and no .debug_info.
# gendwarfksyms (CONFIG_MODVERSIONS + CONFIG_GENDWARFKSYMS) walks every CU
# with dwarf_get_units() and hard-errors on a module without debug info:
#   gendwarfksyms: process_module: dwarf_get_units failed: no debugging information?
# bindings.o carries zero global symbols, so there is nothing to version.
# Every other Rust object in rust/Makefile already sets skip_gendwarfksyms = 1
# for the same class of reason; bindings.o was simply missed.
python3 - <<'EOF'
import os
p = "rust/Makefile"
if os.path.exists(p):
    t = open(p, encoding="utf-8", errors="surrogateescape").read()
    if "bindings.o: private skip_gendwarfksyms" not in t:
        old = "$(obj)/bindings.o: private rustc_target_flags = --extern ffi"
        if old in t:
            t = t.replace(old,
                          "$(obj)/bindings.o: private skip_gendwarfksyms = 1\n" + old,
                          1)
            open(p, "w", encoding="utf-8",
                 errors="surrogateescape").write(t)
            print("rust/Makefile: bindings.o skip_gendwarfksyms=1")
        else:
            print("rust/Makefile: bindings.o anchor not found")
    else:
        print("rust/Makefile: bindings.o already skipped")
EOF

# kernel/sched/walt is builtin (CONFIG_SCHED_WALT=y) and walt_config.c calls
# socinfo_get_id_string(), which lives in the QCOM_SOCINFO module.  Builtin
# code cannot reference a module's exports, so vmlinux links with the symbol
# undefined.  socinfo is a tiny early-init driver; build it in.
python3 - <<'EOF'
import os, re
p = "arch/arm64/configs/vendor/parrot_perf.config"
if os.path.exists(p):
    t = open(p, encoding="utf-8", errors="surrogateescape").read()
    if re.search(r'^CONFIG_QCOM_SOCINFO=', t, re.M):
        t = re.sub(r'^CONFIG_QCOM_SOCINFO=.*$', 'CONFIG_QCOM_SOCINFO=y',
                   t, flags=re.M)
    else:
        t += ("\n" if not t.endswith("\n") else "") + "CONFIG_QCOM_SOCINFO=y\n"
    if re.search(r'^CONFIG_QCOM_SMEM=', t, re.M):
        t = re.sub(r'^CONFIG_QCOM_SMEM=.*$', 'CONFIG_QCOM_SMEM=y', t, flags=re.M)
    else:
        t += "CONFIG_QCOM_SMEM=y\n"
    open(p, "w", encoding="utf-8", errors="surrogateescape").write(t)
    print("parrot_perf.config: CONFIG_QCOM_SMEM=y CONFIG_QCOM_SOCINFO=y "
          "(builtin for walt)")
EOF

python3 - <<'EOF'
import os, re
p = "arch/arm64/configs/vendor/parrot_perf.config"
if os.path.exists(p):
    t = open(p, encoding="utf-8", errors="surrogateescape").read()
    if re.search(r'^CONFIG_GH_VCPU_MGR=', t, re.M):
        t = re.sub(r'^CONFIG_GH_VCPU_MGR=.*$', '# CONFIG_GH_VCPU_MGR is not set',
                   t, flags=re.M)
    else:
        t += ("\n" if not t.endswith("\n") else "") + \
             "# CONFIG_GH_VCPU_MGR is not set\n"
    open(p, "w", encoding="utf-8", errors="surrogateescape").write(t)
    print("parrot_perf.config: CONFIG_GH_VCPU_MGR disabled "
          "(duplicate of gh_proxy_sched)")
EOF

# The CLO fragment defect recurs: composite objects keep their -objs lines but
# lose the obj- line that builds them.  Run the symbol-driven repair against
# the previous build log so the next build picks up everything modpost found.
if [ -f "$HOME/kbuild.log" ]; then
    python3 "$HOME/fix_missing_obj.py" "$HOME/kbuild.log" --apply || true
fi

# CLO keeps its WALT scheduler in kernel/sched/walt/ and expects the parent
# Makefile to descend into it.  ACK has no such directory, so the merge never
# carried the line over and none of walt.o/boost.o/core_ctl.o were ever
# compiled -- every consumer then fails at modpost on should_boost_bus_dcvs,
# walt_* and friends.
python3 - <<'EOF'
import os
p = "kernel/sched/Makefile"
if os.path.exists(p) and os.path.isdir("kernel/sched/walt"):
    t = open(p, encoding="utf-8", errors="surrogateescape").read()
    if "walt/" not in t:
        if not t.endswith("\n"):
            t += "\n"
        t += "obj-$(CONFIG_SCHED_WALT) += walt/\n"
        open(p, "w", encoding="utf-8", errors="surrogateescape").write(t)
        print("kernel/sched/Makefile: obj-$(CONFIG_SCHED_WALT) += walt/")
    else:
        print("kernel/sched/Makefile: walt/ already present")
EOF

# CONFIG_MHI_DTR=m means misc.c compiles its mhi_device_ioctl stub out and the
# real implementation in mhi_dtr.c is expected to provide it.  mhi_dtr.o was
# never added to the MHI build.
python3 - <<'EOF'
import os, re
p = "drivers/bus/mhi/devices/Makefile"
if os.path.exists(p):
    t = open(p, encoding="utf-8", errors="surrogateescape").read()
    if "mhi_dtr" not in t and os.path.exists("drivers/bus/mhi/devices/mhi_dtr.c"):
        if not t.endswith("\n"):
            t += "\n"
        t += "obj-$(CONFIG_MHI_DTR) += mhi_dtr.o\n"
        open(p, "w", encoding="utf-8", errors="surrogateescape").write(t)
        print("mhi devices: obj-$(CONFIG_MHI_DTR) += mhi_dtr.o")
EOF

# walt.c registers `register_trace_android_rvh___set_task_cpu` (three
# underscores) but the hook declared in include/trace/hooks/sched.h is
# android_rvh_set_task_cpu (two).  CLO renamed the tracepoint and forgot the
# caller; the generated register_trace_* symbol therefore does not exist.
python3 - <<'EOF'
import os
p = "kernel/sched/walt/walt.c"
if os.path.exists(p):
    t = open(p, encoding="utf-8", errors="surrogateescape").read()
    bad = "register_trace_android_rvh___set_task_cpu"
    good = "register_trace_android_rvh_set_task_cpu"
    if bad in t:
        t = t.replace(bad, good)
        open(p, "w", encoding="utf-8", errors="surrogateescape").write(t)
        print("walt.c: %s -> %s" % (bad, good))
    else:
        print("walt.c: tracepoint name already correct")
EOF

# sysctl.c uses GENMASK_TYPE(u32, ...), a macro that landed in 6.9.  This
# tree predates it; GENMASK() has identical semantics for a u32 target here.
python3 - <<'EOF'
import os, re
p = "kernel/sched/walt/sysctl.c"
if os.path.exists(p):
    t = open(p, encoding="utf-8", errors="surrogateescape").read()
    if "GENMASK_TYPE" in t:
        t = re.sub(r'GENMASK_TYPE\(\s*u32\s*,', 'GENMASK(', t)
        open(p, "w", encoding="utf-8", errors="surrogateescape").write(t)
        print("sysctl.c: GENMASK_TYPE(u32, ...) -> GENMASK(...)")
EOF

# mhi_dtr.c is CLO-only and needs a `struct mhi_device_id` definition this
# tree does not have.  CONFIG_MHI_DTR has no Kconfig entry either, so the
# symbol is a leftover from the fragment merge; turning it off makes misc.c
# compile its stub, which is exactly what the module consumers expect.
python3 - <<'EOF'
import os, re
p = "arch/arm64/configs/vendor/parrot_perf.config"
if os.path.exists(p):
    t = open(p, encoding="utf-8", errors="surrogateescape").read()
    if re.search(r'^CONFIG_MHI_DTR=', t, re.M):
        t = re.sub(r'^CONFIG_MHI_DTR=.*$', '# CONFIG_MHI_DTR is not set',
                   t, flags=re.M)
        open(p, "w", encoding="utf-8", errors="surrogateescape").write(t)
        print("parrot_perf.config: CONFIG_MHI_DTR disabled")
EOF

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
