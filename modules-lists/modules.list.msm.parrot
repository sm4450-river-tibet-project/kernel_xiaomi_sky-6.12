# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) Qualcomm Technologies, Inc. and/or its subsidiaries.
# SM4450 / parrot / ravelin -- Redmi 12 5G (sky)
#
# First-stage modules, loaded from the initramfs before /vendor is mounted.
# Only the drivers needed to bring up storage, power and the interconnect
# fabric belong here; everything else is in the vendor_dlkm list.
arm_smmu.ko
gic_intr_routing.ko
llcc-qcom.ko
clk-dummy.ko
clk-qcom.ko
cmd-db.ko
iommu-logger.ko
icc-bcm-voter.ko
icc-common.ko
icc-rpmh.ko
qnoc-ravelin.ko
pinctrl-msm.ko
pinctrl-ravelin.ko
gcc-sm4450.ko
dispcc-sm4450.ko
gpucc-sm4450.ko
camcc-sm4450.ko
debugcc-sm4450.ko
phy-qcom-qmp-ufs.ko
phy-qcom-ufs-qmp-v4-waipio.ko
ufs-qcom.ko
ufshcd-core.ko
ufshcd-pltfrm.ko
rpmhpd.ko
qcom-rpmhpd.ko
qcom-spmi-pmic.ko
regmap-spmi.ko
qcom_geni_serial.ko
