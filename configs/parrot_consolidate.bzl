parrot_consolidate_config = {
    # keep sorted
    # ---- platform ----
    # ARCH_PARROT does not exist on CLO 6.12. The board gate there is
    # ARCH_RAVELIN (arch/arm64/Kconfig.platforms), and the SM4450 drivers
    # are gated on it. Enabling WAIPIO/DIWALI (as the waipio-derived copy
    # did) is wrong: those are different SoCs and pull in unrelated drivers.
    "CONFIG_ARCH_RAVELIN": "y",
    "CONFIG_ARCH_QCOM": "y",

    # ---- debug (consolidate only) ----
    "CONFIG_DEBUG_PAGEALLOC": "y",
    "CONFIG_DEBUG_PAGEALLOC_ENABLE_DEFAULT": "y",
    "CONFIG_DEBUG_SPINLOCK": "y",
    "CONFIG_UFS_DBG": "y",

    # ---- clocks: SM4450 clock controllers ----
    "CONFIG_SM_GCC_4450": "m",
    "CONFIG_SM_DISPCC_4450": "m",
    "CONFIG_SM_CAMCC_4450": "m",
    "CONFIG_SM_GPUCC_4450": "m",
    "CONFIG_SM_DEBUGCC_4450": "m",

    # ---- interconnect: ravelin NoC ----
    "CONFIG_INTERCONNECT_QCOM_RAVELIN": "m",

    # ---- pinctrl ----
    "CONFIG_PINCTRL_RAVELIN": "m",

    # ---- UFS: ravelin reuses the parrot/waipio PHY ----
    # qcom/ravelin-qrd.dtsi: compatible = "qcom,ufs-phy-qmp-v4-waipio"
    "CONFIG_PHY_QCOM_UFS_V4_WAIPIO": "m",
}
