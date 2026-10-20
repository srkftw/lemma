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
from package_closure_deployment import (CONFIGURATIONS as PACKAGE_CONFIGURATIONS,
 SOFTWARE_DEPLOYMENT as PACKAGE_SOFTWARE_DEPLOYMENT, BOOT_ROOTS as PACKAGE_BOOT_ROOTS)
from reader_deployment import (CONFIGURATIONS as READER_CONFIGURATIONS,
 SOFTWARE_DEPLOYMENT as READER_SOFTWARE_DEPLOYMENT, BOOT_ROOTS as READER_BOOT_ROOTS)
from product_reader_deployment import (ALL_CONFIGURATIONS as PRODUCT_READER_CONFIGURATIONS,
 SOFTWARE_DEPLOYMENT as PRODUCT_READER_SOFTWARE_DEPLOYMENT, BOOT_ROOTS as PRODUCT_READER_BOOT_ROOTS)
from chooser_reader_deployment import (CONFIGURATIONS as CHOOSER_CONFIGURATIONS,
 SOFTWARE_DEPLOYMENT as CHOOSER_SOFTWARE_DEPLOYMENT, BOOT_ROOTS as CHOOSER_BOOT_ROOTS)
KERNEL_CONFIGURATIONS=CONFIGURATIONS+ENTRY2_CONFIGURATIONS+PACKAGE_CONFIGURATIONS+READER_CONFIGURATIONS+PRODUCT_READER_CONFIGURATIONS+CHOOSER_CONFIGURATIONS
KERNEL_ENTRIES.update(dict(zip(ENTRY2_CONFIGURATIONS,("siliconClosureEntry2Boot","siliconClosureEntry2InitializeMedium"))))
KERNEL_ENTRIES.update(PACKAGE_BOOT_ROOTS)
KERNEL_ENTRIES.update(READER_BOOT_ROOTS)
KERNEL_ENTRIES.update(PRODUCT_READER_BOOT_ROOTS)
KERNEL_ENTRIES.update(CHOOSER_BOOT_ROOTS)
from package_companion_deployment import ALL_CONFIGURATIONS as PACKAGE_RECOVERY_CONFIGURATIONS, SOFTWARE_DEPLOYMENT as PACKAGE_RECOVERY_SOFTWARE_DEPLOYMENT
from multimodal_deployment import CONFIGURATIONS as MULTIMODAL_CONFIGURATIONS, SOFTWARE_DEPLOYMENT as MULTIMODAL_SOFTWARE_DEPLOYMENT
from integrated_deployment import CONFIGURATIONS as INTEGRATED_CONFIGURATIONS, SOFTWARE_DEPLOYMENT as INTEGRATED_SOFTWARE_DEPLOYMENT
ALL_CONFIGURATIONS=INTEGRATED_CONFIGURATIONS+KERNEL_CONFIGURATIONS+RECOVERY3_CONFIGURATIONS+PACKAGE_RECOVERY_CONFIGURATIONS+MULTIMODAL_CONFIGURATIONS
def software_deployment_for(configuration):
 from school_deployment import ALL_CONFIGURATIONS as school, software_deployment_for as school_software
 if configuration in school:return school_software(configuration)
 if configuration in INTEGRATED_CONFIGURATIONS:return INTEGRATED_SOFTWARE_DEPLOYMENT
 if configuration in MULTIMODAL_CONFIGURATIONS:return MULTIMODAL_SOFTWARE_DEPLOYMENT
 if configuration in CHOOSER_CONFIGURATIONS:return CHOOSER_SOFTWARE_DEPLOYMENT
 if configuration in PRODUCT_READER_CONFIGURATIONS:
  from product_reader_deployment import WATCHDOG_CONFIGURATION, WATCHDOG_SOFTWARE_DEPLOYMENT
  return WATCHDOG_SOFTWARE_DEPLOYMENT if configuration == WATCHDOG_CONFIGURATION else PRODUCT_READER_SOFTWARE_DEPLOYMENT
 if configuration in READER_CONFIGURATIONS:return READER_SOFTWARE_DEPLOYMENT
 if configuration in PACKAGE_RECOVERY_CONFIGURATIONS:
  from package_companion_deployment import software_deployment_for as package_software
  return package_software(configuration)
 if configuration in CONFIGURATIONS:return SOFTWARE_DEPLOYMENT
 if configuration in ENTRY2_CONFIGURATIONS:return ENTRY2_SOFTWARE_DEPLOYMENT
 if configuration in RECOVERY3_CONFIGURATIONS:return RECOVERY3_SOFTWARE_DEPLOYMENT
 if configuration in PACKAGE_CONFIGURATIONS:return PACKAGE_SOFTWARE_DEPLOYMENT
 raise ValueError("Unknown exact Closure software deployment")
