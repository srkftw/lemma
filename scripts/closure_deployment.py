"""Exact software registry for the isolated closure mathematics successor."""
CONFIGURATIONS=('lemmasim-silicon-closure-bulk-notebook',
 'lemmasim-silicon-closure-bulk-initialize',
 'lemmasim-silicon-closure-arithmetic-oom-development',
 'lemmasim-silicon-closure-arithmetic-fault-development')
SOFTWARE_DEPLOYMENT={'contract_version':'lemma-managed-closure-bulk-deployment-v1',
 'silicon_profile':'lemma-silicon-dev/0.3.0',
 'user_profiles':{'store':'core0-user-v0.1','notebook':'core0-user-v0.2','arithmetic':'core0-user-v0.7'}}
KERNEL_ENTRIES=dict(zip(CONFIGURATIONS,('siliconClosureBoot','siliconClosureInitializeMedium',
 'siliconClosureOOMBoot','siliconClosureFaultBoot')))
