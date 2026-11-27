# SPDX-License-Identifier: GPL-2.0

obj-$(CONFIG_GUNYAH_HYPERCALLS) += gunyah_hypercall.o

# --- CLO soc-repo overlay additions (restored by fix_kbuild.py) ---
ccflags-y += -I$(src)

obj-$(CONFIG_GH_ARM64_DRV) += gh_arm_drv.o
gh_arm_drv-objs += gh_arm.o irq.o reset.o

