"""One explicit Product10+Multimodal14 guest composition on Integrated15.

This registry selects genuine maintained roots. It implements no target policy.
"""
CONFIGURATIONS=('lemmasim-silicon-integrated-notebook',)
SOFTWARE_DEPLOYMENT={
 'contract_version':'lemma-integrated-notebook-deployment/1',
 'silicon_profile':'lemma-silicon-dev/0.15.0',
 'machine_profile':'lemma-one-multimodal/0.2.0',
 'reader_contract':'lemma-course-reader-location/1',
 'chooser_contract':'lemma-course-empty-selection-chooser/1',
 'stream_contract':'lemma-multimodal-converter/1',
 'boot_image_contract':'lemma-product10-image-compatibility/1',
 'user_profiles':{'store':'core0-user-v0.1','notebook':'core0-user-v0.2','arithmetic':'core0-user-v0.7','course':'core0-user-v0.1'},
}
BOOT_ROOT='Lemma.Platform.LemmaSim.IntegratedKernel.boot'
DISPATCH_ROOT='Lemma.Platform.LemmaSim.IntegratedKernel.dispatch'
NOTEBOOK_ROOT='Lemma.Applications.Notebook.mainMultimodal'

LEGACY_CONFIGURATIONS=CONFIGURATIONS
from school_deployment import INTEGRATED_CONFIGURATIONS as SCHOOL_CONFIGURATIONS
CONFIGURATIONS += SCHOOL_CONFIGURATIONS
