"""Exact installed-package/Closure7 software tuple on canonical silicon0.3.

Host selection only. Package parsing, interpretation, checking and persistence
remain separately elaborated guest Actions in owned address spaces.
"""
CONFIGURATIONS=('lemmasim-silicon-package-closure-entry2-bulk-notebook',
                'lemmasim-silicon-package-closure-entry2-bulk-initialize')
SOFTWARE_DEPLOYMENT={'contract_version':'lemma-package-closure-entry2-bulk-deployment-v1',
 'silicon_profile':'lemma-silicon-dev/0.3.0',
 'user_profiles':{'store':'core0-user-v0.1','notebook':'core0-user-v0.2',
                  'arithmetic':'core0-user-v0.7','course':'core0-user-v0.1'}}
BOOT_ROOTS=dict(zip(CONFIGURATIONS,('siliconPackageClosureEntry2Boot',
                                 'siliconPackageClosureEntry2InitializeMedium')))
NOTEBOOK_ROOT='Lemma.Applications.Notebook.mainPackageClosureBulk'
