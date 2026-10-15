"""Closed four-role package notebook on the existing Clocked13 recovery machine.
Host selection only; guest Lean owns installation, checking, journals and retry.
"""
CONFIGURATIONS = (
    'lemmasim-silicon-usb-clocked-package-retry-bulk-notebook',
    'lemmasim-silicon-usb-clocked-package-retry-bulk-initialize',
)
SOFTWARE_DEPLOYMENT = {
    'contract_version': 'lemma-package-clocked-recovery4-deployment-v1',
    'silicon_profile': 'lemma-silicon-dev/0.13.0',
    'user_profiles': {'store': 'core0-user-v0.2', 'notebook': 'core0-user-v0.2',
                      'arithmetic': 'core0-user-v0.7', 'course': 'core0-user-v0.1'},
}
BOOT_ROOTS = dict(zip(CONFIGURATIONS, (
    'siliconUSBPackageRecoveryBoot', 'siliconUSBPackageRecoveryInitializeMedium')))
DISPATCH_ROOT = 'dispatchUSBPackageRecoveryBulk'
USER_ROOTS = {
    'store': ('Lemma.Services.Store.ServerRecoveryAwait',
              'Lemma.Services.Store.ServerRecoveryAwait.mainRecoveryAwait'),
    'notebook': ('Lemma.Applications.Notebook',
                 'Lemma.Applications.Notebook.mainRecoverablePackageClosureBulk'),
    'arithmetic': ('Lemma.Services.Arithmetic.ServerV7',
                   'Lemma.Services.Arithmetic.ServerV7.main'),
    'course': ('Lemma.Courses.PackageInstaller', 'Lemma.Courses.PackageInstaller.mainAwait'),
}
