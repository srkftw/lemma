"""Exact software identity for Closure7 joined to Clocked13 recovery.
Host comparison only; all journal, retry and mathematical policy remain Lean.
"""
CONFIGURATIONS=('lemmasim-silicon-usb-clocked-closure-retry-bulk-notebook','lemmasim-silicon-usb-clocked-closure-retry-bulk-initialize')
SOFTWARE_DEPLOYMENT={'contract_version':'lemma-usb-clocked-closure-recovery-deployment-v1',
 'silicon_profile':'lemma-silicon-dev/0.13.0',
 'user_profiles':{'store':'core0-user-v0.2','notebook':'core0-user-v0.2','arithmetic':'core0-user-v0.7'}}
KERNEL_ENTRIES=dict(zip(CONFIGURATIONS,('siliconUSBClosureRecoveryBoot','siliconUSBClosureRecoveryInitializeMedium')))
STORE_ROOT='Lemma.Services.Store.ServerRecovery.mainRecoveryCourse'
NOTEBOOK_ROOT='Lemma.Applications.Notebook.mainRecoverableClosureBulk'
ARITHMETIC_ROOT='Lemma.Services.Arithmetic.ServerV7.main'
