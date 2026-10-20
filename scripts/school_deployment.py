"""Explicit Notebook23 written-page school composition on fast14/integrated15.

The preceding v1/Notebook22 tuple remains in its complete consumed archives;
its attempts and eight-stroke envelope retain their original version identity.
"""
FAST='lemmasim-silicon-school-notebook'
INTEGRATED='lemmasim-silicon-integrated-school-notebook'
INTEGRATED_PCM='lemmasim-silicon-integrated-pcm-school-notebook'
INITIALIZE='lemmasim-silicon-school-initialize'
CONFIGURATIONS=(FAST,INITIALIZE,INTEGRATED,INTEGRATED_PCM)
NOTEBOOK_ROOT='Lemma.Applications.Notebook.mainMultimodalSchool'
STORE_ROOT='Lemma.Services.Store.ServerSchool.main'
COURSE_ROOT='Lemma.Courses.PackageInstaller.mainAwaitSelected'
USER_ROOTS={'store':(STORE_ROOT,1,'core0-user-v0.2'),'notebook':(NOTEBOOK_ROOT,2,'core0-user-v0.2'),'arithmetic':('Lemma.Services.Arithmetic.ServerV8.main',3,'core0-user-v0.7'),'course':(COURSE_ROOT,4,'core0-user-v0.1')}

# Historical exports above retain the exact School23 tuple. New callers must
# explicitly select a reviewed version; arbitrary names/modules are rejected.
_ROLES=('notebook','initialize','integrated','integrated-pcm')
_CONFIGURATIONS={23:dict(zip(_ROLES,CONFIGURATIONS)),24:{
 'notebook':'lemmasim-silicon-school24-notebook',
 'initialize':'lemmasim-silicon-school24-initialize',
 'integrated':'lemmasim-silicon-integrated-school24-notebook',
 'integrated-pcm':'lemmasim-silicon-integrated-pcm-school24-notebook'},25:{
 'notebook':'lemmasim-silicon-school25-notebook',
 'initialize':'lemmasim-silicon-school25-initialize',
 'integrated':'lemmasim-silicon-integrated-school25-notebook',
 'integrated-pcm':'lemmasim-silicon-integrated-pcm-school25-notebook'}}
VERSIONS=tuple(_CONFIGURATIONS)

def configuration_for(version,role):
 if type(version) is not int or version not in _CONFIGURATIONS or role not in _ROLES:
  raise ValueError('Unknown school deployment version/role')
 return _CONFIGURATIONS[version][role]

def configurations_for(version):
 return tuple(configuration_for(version,role) for role in _ROLES)

def version_for_configuration(configuration):
 for version,roles in _CONFIGURATIONS.items():
  if configuration in roles.values():return version
 raise ValueError('Unknown school deployment')

def user_roots_for(configuration):
 version=version_for_configuration(configuration)
 roots=dict(USER_ROOTS)
 if version in (24,25):
  roots['notebook']=('Lemma.Applications.Notebook.'+('mainMultimodalSchoolV3' if version==25 else 'mainMultimodalSchool24'),2,'core0-user-v0.2')
  roots['arithmetic']=('Lemma.Services.Arithmetic.ServerV9.main',3,'core0-user-v0.7')
 return roots

ALL_CONFIGURATIONS=tuple(configuration for version in VERSIONS for configuration in configurations_for(version))
ALL_FAST_CONFIGURATIONS=tuple(configuration_for(version,role) for version in VERSIONS for role in ('notebook','initialize'))
ALL_INTEGRATED_CONFIGURATIONS=tuple(configuration_for(version,role) for version in VERSIONS for role in ('integrated','integrated-pcm'))
ALL_PCM_CONFIGURATIONS=tuple(configuration_for(version,'integrated-pcm') for version in VERSIONS)
ALL_BOOT_ROOTS={configuration_for(version,role):root for version in VERSIONS for role,root in
 [('notebook','siliconMultimodalBoot'),('initialize','siliconMultimodalInitializeMedium')]}

def software_deployment_for(configuration):
 version=version_for_configuration(configuration)
 value={'contract_version':'lemma-school-notebook-deployment/2','notebook_version':version,
 'silicon_profile':'lemma-silicon-dev/0.16.0' if configuration in ALL_PCM_CONFIGURATIONS else 'lemma-silicon-dev/0.15.0' if configuration in ALL_INTEGRATED_CONFIGURATIONS else 'lemma-silicon-dev/0.14.0',
 'machine_profile':'lemma-one-multimodal/0.2.0','reader_contract':'lemma-course-reader-location/1',
 'chooser_contract':'lemma-course-empty-selection-chooser/1','stream_contract':'lemma-multimodal-converter/1',
 'selection_contract':'lemma-school-course-selection/1','submission_contract':'lemma-school-guest-submission/2',
 'user_profiles':{'store':'core0-user-v0.2','notebook':'core0-user-v0.2','arithmetic':'core0-user-v0.7','course':'core0-user-v0.1'}}
 if configuration in ALL_INTEGRATED_CONFIGURATIONS:value['boot_image_contract']='lemma-product10-image-compatibility/1'
 if configuration in ALL_PCM_CONFIGURATIONS:value.update(contract_version='lemma-school-notebook-deployment/3',stream_contract='lemma-multimodal-converter/2',multimodal_service_version=3)
 if version in (24,25):value.update(contract_version='lemma-school-notebook-deployment/4',
  extension_contract='lemma-school-exact-reduction-advisory/1',assistance_event_format=3)
 if version==25:value.update(contract_version='lemma-school-notebook-deployment/5',
  submission_stream_contract='lemma-school-console-stream/1')
 return value

FAST_CONFIGURATIONS=(FAST,INITIALIZE)
INTEGRATED_CONFIGURATIONS=(INTEGRATED,INTEGRATED_PCM)
BOOT_ROOTS={FAST:'siliconMultimodalBoot',INITIALIZE:'siliconMultimodalInitializeMedium'}
