"""Closed canonical Reader20 selection; no target policy on the host."""
CONFIGURATIONS = (
    'lemmasim-silicon-package-chooser-bulk-notebook',
    'lemmasim-silicon-package-chooser-bulk-initialize',
)
SOFTWARE_DEPLOYMENT = {
    'contract_version': 'lemma-package-reader-chooser-bulk-deployment-v1',
    'silicon_profile': 'lemma-silicon-dev/0.3.0',
    'reader_contract': 'lemma-course-reader-location/1',
    'chooser_contract': 'lemma-course-empty-selection-chooser/1',
    'user_profiles': {'store': 'core0-user-v0.1', 'notebook': 'core0-user-v0.2',
                      'arithmetic': 'core0-user-v0.7', 'course': 'core0-user-v0.1'},
}
BOOT_ROOTS = dict(zip(CONFIGURATIONS, (
    'siliconPackageClosureEntry2Boot', 'siliconPackageClosureEntry2InitializeMedium')))
NOTEBOOK_ROOT = 'Lemma.Applications.Notebook.mainPackageReaderChooser'
