"""Explicit Notebook23 written-page school composition on fast14/integrated15.

The preceding v1/Notebook22 tuple remains in its complete consumed archives;
its attempts and eight-stroke envelope retain their original version identity.
"""
FAST='lemmasim-silicon-school-notebook'
INTEGRATED='lemmasim-silicon-integrated-school-notebook'
INITIALIZE='lemmasim-silicon-school-initialize'
CONFIGURATIONS=(FAST,INITIALIZE,INTEGRATED)
NOTEBOOK_ROOT='Lemma.Applications.Notebook.mainMultimodalSchool'
STORE_ROOT='Lemma.Services.Store.ServerSchool.main'
COURSE_ROOT='Lemma.Courses.PackageInstaller.mainAwaitSelected'
USER_ROOTS={'store':(STORE_ROOT,1,'core0-user-v0.2'),'notebook':(NOTEBOOK_ROOT,2,'core0-user-v0.2'),'arithmetic':('Lemma.Services.Arithmetic.ServerV8.main',3,'core0-user-v0.7'),'course':(COURSE_ROOT,4,'core0-user-v0.1')}
def software_deployment_for(configuration):
 if configuration not in CONFIGURATIONS:raise ValueError('Unknown school deployment')
 value={'contract_version':'lemma-school-notebook-deployment/2','notebook_version':23,
 'silicon_profile':'lemma-silicon-dev/0.15.0' if configuration==INTEGRATED else 'lemma-silicon-dev/0.14.0',
 'machine_profile':'lemma-one-multimodal/0.2.0','reader_contract':'lemma-course-reader-location/1',
 'chooser_contract':'lemma-course-empty-selection-chooser/1','stream_contract':'lemma-multimodal-converter/1',
 'selection_contract':'lemma-school-course-selection/1','submission_contract':'lemma-school-guest-submission/2',
 'user_profiles':{'store':'core0-user-v0.2','notebook':'core0-user-v0.2','arithmetic':'core0-user-v0.7','course':'core0-user-v0.1'}}
 if configuration==INTEGRATED:value['boot_image_contract']='lemma-product10-image-compatibility/1'
 return value

FAST_CONFIGURATIONS=(FAST,INITIALIZE)
INTEGRATED_CONFIGURATIONS=(INTEGRATED,)
BOOT_ROOTS={FAST:'siliconMultimodalBoot',INITIALIZE:'siliconMultimodalInitializeMedium'}
