"""Closed Reader19/Recovery5 selection on the unchanged Clocked13 machine.

Host artifact selection only; all reading, mathematics, recovery and Save are
ordinary compiled Lean in the existing four separately linked services.
"""
CONFIGURATIONS = (
    'lemmasim-silicon-usb-clocked-reader-entry2-bulk-notebook',
    'lemmasim-silicon-usb-clocked-reader-entry2-bulk-initialize',
)
SOFTWARE_DEPLOYMENT = {
    'contract_version': 'lemma-package-reader-clocked-recovery5-entry2-deployment-v1',
    'silicon_profile': 'lemma-silicon-dev/0.13.0',
    'entry_contract': 'lemma-scheduler-entry-borrow-v2',
    'reader_contract': 'lemma-course-reader-location/1',
    'recovery_contract': 'lemma-notebook-reader-recovery/5',
    'user_profiles': {'store': 'core0-user-v0.2', 'notebook': 'core0-user-v0.2',
                      'arithmetic': 'core0-user-v0.7', 'course': 'core0-user-v0.1'},
}
BOOT_ROOTS = dict(zip(CONFIGURATIONS, (
    'siliconUSBPackageRecoveryEntry2Boot', 'siliconUSBPackageRecoveryEntry2InitializeMedium')))
NOTEBOOK_ROOT = 'Lemma.Applications.Notebook.mainRecoverablePackageReader'
