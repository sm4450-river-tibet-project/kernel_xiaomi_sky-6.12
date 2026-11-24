# SPDX-License-Identifier: GPL-2.0-only
# SM4450 / parrot / ravelin -- modules that must NOT go into vendor_dlkm.
# The ravelin NoC and pin controller are first-stage so that storage works
# before /vendor is mounted.
qnoc-ravelin.ko
pinctrl-ravelin.ko
gcc-sm4450.ko
dispcc-sm4450.ko
gpucc-sm4450.ko
camcc-sm4450.ko
debugcc-sm4450.ko
phy-qcom-ufs-qmp-v4-waipio.ko
ufs-qcom.ko
