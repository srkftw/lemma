"""Exact additive course mount-await deployment; no guest policy implementation."""
CONFIGURATIONS=('lemmasim-silicon-course-await-bulk-notebook',
                'lemmasim-silicon-course-await-bulk-initialize')
SOFTWARE_DEPLOYMENT={'contract_version':'lemma-course-mounted-await-bulk-deployment-v1',
 'silicon_profile':'lemma-silicon-dev/0.3.0',
 'user_profiles':{'store':'core0-user-v0.1','notebook':'core0-user-v0.2',
                  'arithmetic':'core0-user-v0.5','course':'core0-user-v0.1'}}
BOOT_ROOTS=dict(zip(CONFIGURATIONS,('siliconCourseAwaitBoot','siliconCourseAwaitInitializeMedium')))
STORE_ROOT='Lemma.Services.Store.ServerAwait.main'
INSTALLER_ROOT='Lemma.Courses.PackageInstaller.mainAwait'

def library_source_allowed(role,source,image):
 """Only this exact Store root borrows the old engine/dispatcher library.

 Old main/step/courseMain/courseStep remain executable roots and are excluded.
 Caller and primitive authority still undergo the full ordinary artifact audit.
 """
 return (role=='user' and isinstance(image,dict) and image.get('key')=='store' and
         image.get('module')=='Lemma.Services.Store.ServerAwait' and
         image.get('source')==STORE_ROOT and
         (source=='Lemma.Services.Store.Server' or source.startswith('Lemma.Services.Store.Server.')) and source not in
         ('Lemma.Services.Store.Server.main','Lemma.Services.Store.Server.step',
          'Lemma.Services.Store.Server.courseMain','Lemma.Services.Store.Server.courseStep'))
