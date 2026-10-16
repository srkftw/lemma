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
