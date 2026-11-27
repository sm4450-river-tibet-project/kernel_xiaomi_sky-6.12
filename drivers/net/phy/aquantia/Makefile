# SPDX-License-Identifier: GPL-2.0
aquantia-objs			+= aquantia_main.o aquantia_firmware.o aquantia_leds.o
ifdef CONFIG_HWMON
aquantia-objs			+= aquantia_hwmon.o
endif
obj-$(CONFIG_AQUANTIA_PHY)	+= aquantia.o

# --- CLO soc-repo overlay additions (restored by fix_kbuild.py) ---
ccflags-y += -I$(src)

obj-$(CONFIG_AQUANTIA_PHY) += aquantia.o
aquantia-objs += ../../../../lib/crc-itu-t.o aquantia_main.o aquantia_firmware.o aquantia_leds.o

