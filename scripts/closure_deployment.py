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

# Exact extensions; historical declarations above retain their meanings.
ENTRY2_CONFIGURATIONS=("lemmasim-silicon-closure-entry2-bulk-notebook", "lemmasim-silicon-closure-entry2-bulk-initialize")
ENTRY2_SOFTWARE_DEPLOYMENT={"contract_version":"lemma-managed-closure-entry2-bulk-deployment-v1", "silicon_profile":"lemma-silicon-dev/0.3.0", "user_profiles":{"store":"core0-user-v0.1","notebook":"core0-user-v0.2","arithmetic":"core0-user-v0.7"}}
from usb_closure_recovery_deployment import (CONFIGURATIONS as RECOVERY3_CONFIGURATIONS,
                                             SOFTWARE_DEPLOYMENT as RECOVERY3_SOFTWARE_DEPLOYMENT)
KERNEL_CONFIGURATIONS=CONFIGURATIONS+ENTRY2_CONFIGURATIONS
KERNEL_ENTRIES.update(dict(zip(ENTRY2_CONFIGURATIONS,("siliconClosureEntry2Boot","siliconClosureEntry2InitializeMedium"))))
ALL_CONFIGURATIONS=CONFIGURATIONS+ENTRY2_CONFIGURATIONS+RECOVERY3_CONFIGURATIONS
def software_deployment_for(configuration):
 if configuration in CONFIGURATIONS:return SOFTWARE_DEPLOYMENT
 if configuration in ENTRY2_CONFIGURATIONS:return ENTRY2_SOFTWARE_DEPLOYMENT
 if configuration in RECOVERY3_CONFIGURATIONS:return RECOVERY3_SOFTWARE_DEPLOYMENT
 raise ValueError("Unknown exact Closure software deployment")
