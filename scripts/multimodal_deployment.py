"""Exact four-role Multimodal14 successor; no host application policy."""
BASE_CONFIGURATIONS = ('lemmasim-silicon-multimodal-notebook', 'lemmasim-silicon-multimodal-initialize')
PARAMETERIZED_CONFIGURATIONS = ('lemmasim-silicon-multimodal-parameterized-notebook', 'lemmasim-silicon-multimodal-parameterized-initialize')
CONFIGURATIONS = BASE_CONFIGURATIONS + PARAMETERIZED_CONFIGURATIONS
SOFTWARE_DEPLOYMENT = {
    'contract_version': 'lemma-multimodal-notebook-deployment/1',
    'silicon_profile': 'lemma-silicon-dev/0.14.0',
    'machine_profile': 'lemma-one-multimodal/0.2.0',
    'reader_contract': 'lemma-course-reader-location/1',
    'chooser_contract': 'lemma-course-empty-selection-chooser/1',
    'stream_contract': 'lemma-multimodal-converter/1',
    'user_profiles': {'store': 'core0-user-v0.1', 'notebook': 'core0-user-v0.2',
                      'arithmetic': 'core0-user-v0.7', 'course': 'core0-user-v0.1'},
}
BOOT_ROOTS = dict(zip(CONFIGURATIONS, ('siliconMultimodalBoot', 'siliconMultimodalInitializeMedium', 'siliconMultimodalParameterizedBoot', 'siliconMultimodalParameterizedInitializeMedium')))
NOTEBOOK_ROOT = 'Lemma.Applications.Notebook.mainMultimodal'

LEGACY_CONFIGURATIONS=CONFIGURATIONS
from school_deployment import ALL_FAST_CONFIGURATIONS as FAST_CONFIGURATIONS, ALL_BOOT_ROOTS as SCHOOL_BOOT_ROOTS
CONFIGURATIONS += FAST_CONFIGURATIONS
BOOT_ROOTS.update(SCHOOL_BOOT_ROOTS)
