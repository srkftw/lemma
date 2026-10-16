"""Closed software successor on the unchanged four-role Clocked13 machine."""
CONFIGURATIONS = (
    'lemmasim-silicon-usb-clocked-package-entry2-bulk-notebook',
    'lemmasim-silicon-usb-clocked-package-entry2-bulk-initialize',
)
SOFTWARE_DEPLOYMENT = {
    'contract_version': 'lemma-package-clocked-recovery4-entry2-deployment-v1',
    'silicon_profile': 'lemma-silicon-dev/0.13.0',
    'entry_contract': 'lemma-scheduler-entry-borrow-v2',
    'user_profiles': {'store': 'core0-user-v0.2', 'notebook': 'core0-user-v0.2',
                      'arithmetic': 'core0-user-v0.7', 'course': 'core0-user-v0.1'},
}
BOOT_ROOTS = dict(zip(CONFIGURATIONS, (
    'siliconUSBPackageRecoveryEntry2Boot', 'siliconUSBPackageRecoveryEntry2InitializeMedium')))
BOOT_SOURCE = 'bootPackageRecoveryEntry2'
STEP_SOURCE = 'packageRecoveryEntry2Step'
