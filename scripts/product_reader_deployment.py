"""Closed four-role Reader18/Closure7 software selection on Product10.

Host build metadata only. The Lean constructor owns mapping, grants, startup
and confirmation. No initializer or alternate hardware profile is admitted.
"""
CONFIGURATIONS = ("lemmasim-silicon-product-course-reader-bulk-notebook",)
SOFTWARE_DEPLOYMENT = {
    "contract_version": "lemma-package-reader-product10-deployment-v1",
    "kernel_lowering": "lemma-product-course-checked-physical-inline/1",
    "silicon_profile": "lemma-silicon-dev/0.10.0",
    "reader_contract": "lemma-course-reader-location/1",
    "user_profiles": {
        "store": "core0-user-v0.1", "notebook": "core0-user-v0.2",
        "arithmetic": "core0-user-v0.7", "course": "core0-user-v0.1",
    },
}
BOOT_ROOT = "Lemma.Platform.LemmaSim.NotebookKernel.siliconProductCourseReaderBoot"
DISPATCH_ROOT = "Lemma.Platform.LemmaSim.NotebookKernel.dispatchProductExecutedBulk"
NOTEBOOK_ROOT = "Lemma.Applications.Notebook.mainPackageNumberPadBookmark"
BOOT_ROOTS = {CONFIGURATIONS[0]: "siliconProductCourseReaderBoot"}

# Additive supervised product selection. Historical CONFIGURATIONS remains exact.
WATCHDOG_CONFIGURATION = "lemmasim-silicon-product-course-watchdog-bulk-notebook"
ALL_CONFIGURATIONS = CONFIGURATIONS + (WATCHDOG_CONFIGURATION,)
WATCHDOG_SOFTWARE_DEPLOYMENT = {**SOFTWARE_DEPLOYMENT,
    "contract_version": "lemma-package-reader-product10-watchdog-deployment-v1"}
WATCHDOG_BOOT_ROOT = "Lemma.Platform.LemmaSim.TrialWatchdogKernel.boot"
WATCHDOG_DISPATCH_ROOT = "Lemma.Platform.LemmaSim.TrialWatchdogKernel.dispatch"

def roots_for(configuration):
    if configuration == WATCHDOG_CONFIGURATION:
        return WATCHDOG_BOOT_ROOT, WATCHDOG_DISPATCH_ROOT
    if configuration in CONFIGURATIONS:
        return BOOT_ROOT, DISPATCH_ROOT
    raise ValueError("unknown ProductReader deployment")

def software_deployment_for(configuration):
    if configuration == WATCHDOG_CONFIGURATION:
        return WATCHDOG_SOFTWARE_DEPLOYMENT
    if configuration in CONFIGURATIONS:
        return SOFTWARE_DEPLOYMENT
    raise ValueError("unknown ProductReader deployment")
