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

# Historical selectors/catalogs above are immutable. These additive unions are
# used only by the shared build/device registry; exact artifact gates select
# their own complete versioned authority.
from package_entry2_deployment import (CONFIGURATIONS as ENTRY2_CONFIGURATIONS,
    SOFTWARE_DEPLOYMENT as ENTRY2_SOFTWARE_DEPLOYMENT, BOOT_ROOTS as ENTRY2_BOOT_ROOTS)
from companion_reader_deployment import (CONFIGURATIONS as READER_CONFIGURATIONS,
    SOFTWARE_DEPLOYMENT as READER_SOFTWARE_DEPLOYMENT, BOOT_ROOTS as READER_BOOT_ROOTS)
ALL_CONFIGURATIONS = CONFIGURATIONS + ENTRY2_CONFIGURATIONS + READER_CONFIGURATIONS
ALL_BOOT_ROOTS = {**BOOT_ROOTS, **ENTRY2_BOOT_ROOTS, **READER_BOOT_ROOTS}
def software_deployment_for(configuration):
    if configuration in READER_CONFIGURATIONS: return READER_SOFTWARE_DEPLOYMENT
    if configuration in ENTRY2_CONFIGURATIONS: return ENTRY2_SOFTWARE_DEPLOYMENT
    if configuration in CONFIGURATIONS: return SOFTWARE_DEPLOYMENT
    raise ValueError('Unknown exact package companion software deployment')
def boot_source_for(configuration):
    if configuration in READER_CONFIGURATIONS: return 'bootPackageRecoveryEntry2'
    if configuration in ENTRY2_CONFIGURATIONS: return 'bootPackageRecoveryEntry2'
    if configuration in CONFIGURATIONS: return 'bootPackageRecovery'
    raise ValueError('Unknown exact package companion boot source')
