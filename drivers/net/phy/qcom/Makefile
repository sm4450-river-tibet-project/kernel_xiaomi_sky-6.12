# SPDX-License-Identifier: GPL-2.0
obj-$(CONFIG_QCOM_NET_PHYLIB)	+= qcom-phy-lib.o
obj-$(CONFIG_AT803X_PHY)	+= at803x.o
obj-$(CONFIG_QCA83XX_PHY)	+= qca83xx.o
obj-$(CONFIG_QCA808X_PHY)	+= qca808x.o
obj-$(CONFIG_QCA807X_PHY)	+= qca807x.o

# --- CLO soc-repo overlay additions (restored by fix_kbuild.py) ---
ccflags-y += -I$(src)

obj-$(CONFIG_QCA808X_PHY) += qca808x.o
qca808x-objs += qca808x.o qcom-phy-lib.o

