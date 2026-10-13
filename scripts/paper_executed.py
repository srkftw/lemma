"""Independent emitted authority for the opt-in Paper3/Product10 deployment.

The fixed identities below were established from the maintained genuine Lean
component at build/managed/paper-executed-probe-a1, after independent real
controller reset/abort/executed-geometry and health Action checks. Audits never
construct target AST or infer success from these tests. Legacy paths retain
Paper1/2 authority; this profile requires its exact new policy corpus.
"""
import hashlib,json,re
from core0_common import Core0Error
from paper_next import canonical,normalized
CONFIGURATION='lemmasim-silicon-product-executed-bulk-notebook'
EXPECTED = {
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalLengthNext': (['u64'], [], '2cb065efbb0087aadcee02aba000d1d6b75d2cbff429d610ab68af76a4fcafe2'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalWordNext': (['u64', 'u64'], [], 'ada856e4b2c73bc306023c4690ba4617d77f04f15c1f8dd388cbedbfac99807f'),
 'Lemma.Drivers.Paper.uploadWordNext': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'mmio-write', 'io-order', 'physical-read'], '88d1e36f8a5aaf6ebdb04df92f9c124f0e35b781bda90b5a92d33dddaa30f2cc'),
 'Lemma.Drivers.Paper.uploadOffsetNext': (['u64', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-read'], '871073f696f1c93737b85460fd40d108f0ec61fff41cc25c431260ce2cbda22d'),
 'Lemma.Platform.LemmaSim.DeviceService.bulkUploadStepNext': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-read'], '1944203fd010cdb478006cc5befed984ed36bfc18c603ab56ab87016b1ccfeb5'),
 'Lemma.Platform.LemmaSim.DeviceService.bulkValidateStep': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'physical-read'], '75d9fb2fdc1b137eeb0f5ad628327357edd070089eab48cc96e7a45b8764b520'),
 'Lemma.Platform.LemmaSim.DeviceService.uploadBulkNext': (['u64', 'u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-read', 'physical-write'], '8d7e795b8591ccd9fd6c67b02428eb303e9ece5651431c1b3278268be5899bde'),
 'Lemma.Drivers.Paper.uploadNext': (['u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-read'], '397b3df89466969175a03673d72f18784a8cb32f1e25d4e82315a87b80f9dfd0'),
 'Lemma.Platform.LemmaSim.DeviceService.uploadOrdinaryNext': (['u64', 'u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-read', 'physical-write'], '65dd460340c6ffdac1114f80fb889f3c43048665c85460ac39ed85f6aa49811a'),
 'Lemma.Platform.LemmaSim.DeviceService.surfaceV2Next': (['u64', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-read', 'physical-write'], '945925d35cd830f20b719533b10b9cd08d47c0b80282796c12f2136c38a85fdf'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalLengthExecuted': (['u64'], [], 'c441f3bfa30e93a0ef2d1233a6c23d1a6da68a7a01c45f0ef61f8e85be291480'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalWordExecuted': (['u64', 'u64'], [], '08876c2db152ac8c6eda246718539f42b54699aad09cac165a193c728617711e'),
 'Lemma.Platform.Silicon.BindingProductExecuted.frame_pool_bytes': ([], [], '4fa0acfd3ce320ff2bf0018f7650ae87545467117c0507cfd364346ccf03e8df'),
 'Lemma.Platform.Silicon.BindingProductExecuted.power_base': ([], [], 'f9ec268ee18f606b275f97360decd953bffbfb7cab1d3fc2c49187a6b436e9a8'),
 'Lemma.Platform.LemmaSim.Descriptor.expectedBindingExecuted': (['u64', 'u64'], [], 'b62d613eee29716002b7416220fd2c7f80a2f94f8f3f7a2fef4757c6af9d6752'),
 'Lemma.Boot.ProductExecuted.scratch': ([], [], 'cf976b0fad20e73c0b89f3a63a87b31fafa2d6a906f3711ba8b9d5ff01092091'),
 'Lemma.Boot.ProductExecuted.contextMagic': ([], [], '9a47c6a5e2f01930f84215eb3d6c0aab581033910b63233c3a7aa8e176895a66'),
 'Lemma.Platform.LemmaSim.BootHealthExecuted.state': ([], [], '2ddbc8b1bb1f1e8dc6aa3f5a064b06d297102e9e7b4daef6e310e700bf8fb2a0'),
 'Lemma.Boot.ProductExecuted.metadata0Buffer': ([], [], '3030399c8c815c1d5d37fcda04f05990a8a454f5325773280b8b9b2d266bd451'),
 'Lemma.Boot.ProductExecuted.metadata1Buffer': ([], [], 'b5be7012d5f711c8c9393b3f82a2e08799da2732c9dff31d5bce8010c7ca5ffd'),
 'Lemma.Boot.ProductExecuted.wrongReceipt': ([], [], 'e6cd911be7e49560efb6d6c0f490f85e350e7aafdace0fd2e456f39ed8eefa90'),
 'Lemma.Boot.ProductExecuted.chooseMetadata': (['u64', 'u64', 'u64', 'u64', 'u64'], [], '2b831f39f3fd133fc28c741a8112f7b79dd9cda8d93253ade88aa723f6ce412b'),
 'Lemma.Boot.ProductExecuted.malformed': ([], [], '33b18bf929f94890df77997cad4d860bce1696c3aa55f05bd1ca6c7dfcbeff5b'),
 'Lemma.Boot.ProductExecuted.ioFailure': ([], [], 'f1fb530f9ad209160a4a73942381ec20a491b4f4325560a2c67d5673d2fa3c84'),
 'Lemma.Boot.ProductExecuted.validSpan': (['u64', 'u64', 'u64', 'u64'], [], 'c77a2e91aac110fd1104e241abfce6f6074ead3f672b30f7fc45b6bbf18525e5'),
 'Lemma.Boot.ProductExecuted.scratchSpan': (['u64'], [], '2840774c884e75a698fb15793de9b2f56cce2b3ab3f1db2791e1d7b2301bdf9c'),
 'Lemma.Boot.ProductExecuted.pending': ([], [], 'd445b1f4104e328cfcef101fc4f0ca2635ed30c5c2fd29b2850cecc2ab18a47c'),
 'Lemma.Boot.ProductExecuted.submittedRequest': (['u8', 'u64'], [], '71398a6c1d405569be612c5fe824be13108e586047d3deeff6225516e7fe1c28'),
 'Lemma.Boot.ProductExecuted.cancellationStatus': (['u8'], [], 'd1229c4f89a088701aeb35e2145233912110ba777e893e23797a0f76d3edde15'),
 'Lemma.Boot.ProductExecuted.timeout': ([], [], '2d05be857c34a59feff68136fb1866c7ddbed5471e6f720d87702373eafcbed4'),
 'Lemma.Boot.ProductExecuted.validKind': (['u64'], [], '60ad72361b3b0b345769a632d1cfabb98cbf6a3ae27964c2a7f377972d2183e8'),
 'Lemma.Boot.ProductExecuted.mediumSectors': ([], [], '75e58fe021311f9df78a353abe7575272daac947c007bd5a927c30d34989ec4b'),
 'Lemma.Boot.ProductExecuted.validSector': (['u64', 'u64'], [], 'b4cab93de7a546fcaeeb892a79681175a4918d4797fa8c261544d999666d98b0'),
 'Lemma.Boot.ProductExecuted.nvBase': ([], [], 'bca4d83e79b0e61cc5f41ae50f8d5594e1442f84fa592a4dbb76782310f39488'),
 'Lemma.Boot.ProductExecuted.completeState': (['u64'], [], '068f1c677394b1fb6caaf73ba8a843735a6960a6815f90568195397b6f912714'),
 'Lemma.Boot.ProductExecuted.matchingRequest': (['u64', 'u64'], [], 'a7a053d4e192f71a664224d3c025f3029419896b6833ec37ac06a152ad8803b6'),
 'Lemma.Boot.ProductExecuted.metadataMagic': ([], [], 'b4484749710581f11c2cdb059e214e3049d768bb1d7cb2bdc0c4ea27d3abba43'),
 'Lemma.Boot.ProductExecuted.formatVersion': ([], [], 'b9963e51661245c86a7c5e0253149c979ec3a62256c38ccd8f75340e59643817'),
 'Lemma.Boot.ProductExecuted.maximumAttempts': ([], [], '17c4388f936a6222413e847ce8c27b60b92b6f6d9a5544d4fc77775db73fbd4a'),
 'Lemma.Boot.ProductExecuted.noTrial': ([], [], '190b92608d387b74ef344553ce04f931e877ab14721a8cebc906354671cef0a6'),
 'Lemma.Boot.ProductExecuted.metadataFieldsValid': (['u64', 'u64', 'u64', 'u64', 'u64', 'u64', 'u64', 'u64', 'u64'], [], '53fcbc8927ad46d0427ee2c13a6aa79b2f1ff37654ead6221697f0e005a3c3fc'),
 'Lemma.Boot.ProductExecuted.crcInitial': ([], [], 'e770fb816ccbcf70db661b0734a7e2a139cbb52a7135452ea83aad54b7c6dbd4'),
 'Lemma.Boot.ProductExecuted.crcFinish': (['u64'], [], '855e24d1e0f2fba90f990a03c5a49904a411cf78a7882c75a49b0daf3cfa25c2'),
 'Lemma.Boot.ProductExecuted.crcBit': (['u64'], [], '6beb8ad29b843694d4ec3eb69b9f4a98881bb2156ab800f8c330cfcc72919bf1'),
 'Lemma.Boot.ProductExecuted.crcByte': (['u64', 'u64'], [], 'e72905a15bb09b6f3952645f0969b9daddae6c22fe7d345367ed32a951ed6541'),
 'Lemma.Boot.ProductExecuted.crcWord': (['u64', 'u64'], [], 'f31ad5a74308e86eb4dcd26c6ec26fc922bcafdd8e6dab161f01e3b96778d5ef'),
 'Lemma.Boot.ProductExecuted.canConfirm': (['u64', 'u64', 'u64', 'u64'], [], 'f3cf968f427734438603bd8d13ab2c47b89316088a51e4a4471ae86db967d43d'),
 'Lemma.Boot.ProductExecuted.invalidGeneration': (['u64'], [], '7064e4ff7e000c2151d691662654c267a724e85409a973150defab39076658fb'),
 'Lemma.Boot.ProductExecuted.nextMetadataSector': (['u64'], [], '4e61347ef9f2f8b1be5718db7f1feea32cf4f1dd7bd845bb2c75d8679c73ad9e'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.actualDevicesExecuted': ([], ['checked-access', 'mmio-read', 'io-order'], '80f67127d43b3fb76e5c4437d92c4e280a49404139e3040f9fc033f5b5505b9f'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.endNodeExecuted': (['u64', 'u64'], ['checked-access', 'physical-read', 'physical-write'], '3cf4d187e4a03f2d1d11636862589b9a48da0cb971c156bf4978a010268f358f'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.matchStepExecuted': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'physical-read'], '21a08bcb119018e8bd1132a60b43ce74ac539d5538ed8fe37595c940633329b9'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.equalLiteralExecuted': (['u64', 'u64', 'u64'], ['checked-access', 'physical-read'], '1d230e487fc11c829f03ad46f46ff2aad5ae81984e62133f7257d654f8dfb022'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.findStepExecuted': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'physical-read'], 'dad5d438805377d54cfdf8c02d0738e70e779f9bb2dcb8ee0b71416ca7eedce2'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.findCodeExecuted': (['u64', 'u64', 'u64', 'u64'], ['checked-access', 'physical-read'], 'c01bfbcbe771caebc89b07743d7d8c1fff00e6d6a8e6c5c9c8f694ebf4b0761d'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.executedRegisterStep': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'physical-read'], '0c6cdfc24e53fc4bae22930ff9ffcb7aec369106b00c74153134dfc11823c0f4'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.executedProperty': (['u64', 'u64'], ['checked-access', 'physical-read', 'physical-write'], '88657bf15fdd712589ca239e3cf0514afc49371f1b9ff100b27a175f995e3adb'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.leafPropertyExecuted': (['u64', 'u64', 'u64', 'u64'], ['checked-access', 'physical-read', 'physical-write'], '0892f4074e915b8030ee99ea6bbd2ce2f450b1f3a57503666f6a4aeb92417ce0'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.propertyExecuted': (['u64', 'u64', 'u64'], ['checked-access', 'physical-read', 'physical-write'], '41f1597e49b7e4066ba42504a892e14ecb3e3fee6a2045bf09876b8b29c3989d'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.tokenStepExecuted': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'physical-read', 'physical-write'], 'cb22829dd3d7e3cce70418c39a1b0a81842cfaf600577cd71ee4fde6379d7b14'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.validateBindingExecutedCore': (['u64', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'mmio-read', 'io-order', 'physical-read', 'physical-write'], '8780b09a5b6d1a7829b361c51465767f6d079c4340250636a17b7eb7a772fe80'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.validateSiliconProductExecuted': (['u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'mmio-read', 'io-order', 'physical-read', 'physical-write'], '4ed623551c0f9c03ee9793cd4ece2a598e3d7b63b98052f459433b9a65cfa0e5'),
 'Lemma.Platform.LemmaSim.Descriptor.geometryExecuted': (['u64'], ['checked-access', 'mmio-read', 'io-order', 'physical-read', 'physical-write'], '761e27e63573f23884bb0ca5c3ba40a4361a1009287343a73694b80004c20042'),
 'Lemma.Platform.LemmaSim.Descriptor.fieldsStepExecuted.compare': (['u64', 'u32', 'u64'], ['checked-access', 'mmio-read', 'io-order'], 'de2f3f6289b651e81d0e89fca6167153d10c632ab02c4ee032c19cefe606cd3e'),
 'Lemma.Platform.LemmaSim.Descriptor.fieldsStepExecuted': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'mmio-read', 'io-order'], 'e8d4df97fa62d20f34448b892ea459e9b46aedc7cf511a959cd76000eb83b474'),
 'Lemma.Platform.LemmaSim.Descriptor.validateBindingExecuted.admitted': (['u64'], ['checked-access', 'mmio-read', 'io-order', 'physical-read', 'physical-write'], '96c0dae474b4f4e363b48846451500a98d2dcadbbb9f134b1fca265193c545a7'),
 'Lemma.Platform.LemmaSim.Descriptor.validateBindingExecuted': (['u64'], ['checked-access', 'mmio-read', 'io-order', 'physical-read', 'physical-write'], 'ff75bd1b75d05704b0ec2ee08790613c60df88d73cac0d2dcee629eccd4a58f0'),
 'Lemma.Drivers.Paper.initializeExecuted': ([], ['checked-access', 'mmio-read', 'io-order'], '69ecbbc0a5994932f19cb630ee4f7833f9b179e90bb26ba9a2326bf5e377783d'),
 'Lemma.Platform.LemmaSim.Descriptor.validateSiliconProductExecuted': ([], ['checked-access', 'mmio-read', 'io-order', 'physical-read', 'physical-write'], '1c8bbeb1f600c522c87774f930ced9c55a6a46c748cdff3bf72d321356aba8cf'),
 'Lemma.Kernel.Memory.AddressSpace.configureProductExecuted': (['u64'], ['checked-access', 'mmio-read', 'io-order', 'physical-read', 'physical-write'], '5a703b63993b02ed7512760563381b54f9641a2a20e54c43db4d3647996058d1'),
 'Lemma.Platform.LemmaSim.BootHealthExecuted.fatal': ([], [], '154c60282cca0ee9a4161f6459a6a0c108ea537440ffb208e3e87980647cbd89'),
 'Lemma.Platform.LemmaSim.BootHealthExecuted.liveImage': (['u64', 'u64'], ['checked-access', 'physical-read'], '1dea9cf2be8303fc515f03f567514d37a0e9b8167956473ee11a666f6d540d15'),
 'Lemma.Platform.LemmaSim.BootHealthExecuted.put': (['u64', 'u64'], ['checked-access', 'physical-write'], '0aaf44feb6df66c663d1652696f904eedeae8ad92c0bfe679d2986c04612dd5c'),
 'Lemma.Platform.LemmaSim.BootHealthExecuted.configure': (['u64', 'u64'], ['checked-access', 'physical-read', 'physical-write'], '3744a03936ca1f93e98d6f80ccc885e913121f2e804574a6ec80bae9ad089090'),
 'Lemma.Platform.LemmaSim.NotebookKernel.constructModernExecuted': (['u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'machine-state', 'physical-read', 'physical-write', 'firmware-call', 'address-space', 'instruction-sync'], '089dd3d792373d64b142b3aa601576453be3350f15584bac62695b586cac20cb'),
 'Lemma.Platform.LemmaSim.NotebookKernel.acceptPendingModernExecuted': (['u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-read', 'physical-write'], '588f6f1406cb413e386956aac6fc2cb557abbdb099360e0ecc999168e1b2274d'),
 'Lemma.Platform.LemmaSim.BootHealthExecuted.get': (['u64'], ['checked-access', 'physical-read'], '6ab65b41c87e4700f02bc2c46e377c2532f86449540a9d1fc215c6dc06db96fa'),
 'Lemma.Platform.LemmaSim.BootHealthExecuted.paper': (['u64'], ['checked-access', 'mmio-read', 'io-order'], '074036aa8a2acad1098dcea1d205dcd4997ac7b29e07d20291ca2cccec629c4e'),
 'Lemma.Boot.ProductExecuted.readReg': (['u64'], ['checked-access', 'mmio-read', 'io-order'], '1321f316f5845153cc91e683b32148d17aa8fbdebef8c0e11d7c1965f6457266'),
 'Lemma.Boot.ProductExecuted.writeReg': (['u64', 'u64'], ['checked-access', 'mmio-write', 'io-order'], '53cd3e362a77984ca34389738f3ee7fee1806cc9e643c7243c7854fedbba6a30'),
 'Lemma.Boot.ProductExecuted.submit': (['u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order'], '1c2ce094832ea8d97645daa9b287b962011fbf86b99be093af877dd420e59040'),
 'Lemma.Boot.ProductExecuted.acknowledge': (['u64'], ['checked-access', 'mmio-write', 'io-order'], 'ef1cbe8e2a1f753dc5b828b1e42bf00bbbd7b924d5400f8eaeaca61651010e64'),
 'Lemma.Boot.ProductExecuted.cancel': (['u64'], ['checked-access', 'mmio-write', 'io-order'], '88478e83cb9f8b413a7b5a208e48c1150fa054970633d7b10817516ffa996707'),
 'Lemma.Boot.ProductExecuted.finish': (['u64'], ['checked-access', 'mmio-read', 'io-order'], '980cd51d94c00a395663fee6efcaa90d3655357fe6420a64b2521af747816205'),
 'Lemma.Boot.ProductExecuted.waitStep': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'mmio-read', 'io-order'], '66d5bc8ee9e055c8e4aaf2778042c44d90fdb1aeeebdbce38903bcd1c03c74e9'),
 'Lemma.Boot.ProductExecuted.transaction': (['u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order'], 'd712c3093cad9b867f25f25e14147ac01b66ef023735a55c4dfaff8d7278fc6f'),
 'Lemma.Boot.ProductExecuted.bufferRead': (['u64'], ['checked-access', 'mmio-read', 'io-order'], '910b761f69d2de9afde9b19a363b7699801f6d6a4686d1a81081803cc572ebdd'),
 'Lemma.Boot.ProductExecuted.readBufferStep': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'mmio-read', 'io-order', 'physical-write'], '33b4b7c91f0daa9b98ac7ca175047f8222eddae9cf6062f911e61cac89e3bfcf'),
 'Lemma.Boot.ProductExecuted.readSector': (['u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-write'], 'f02dcec638a4e341247638c0c167fe9439f5fbea38e4573494663e8b5994b779'),
 'Lemma.Boot.ProductExecuted.crcStep': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'physical-read'], 'a5769999e1a452655f5a496445d1afcd00ab92b63c5bcb458d8ce47f7e52fc7f'),
 'Lemma.Boot.ProductExecuted.sectorChecksum': (['u64'], ['checked-access', 'physical-read'], 'f670faf32fd9912984f4b585f183b51bc2752a2e5d381836d34fae71b581658c'),
 'Lemma.Boot.ProductExecuted.readWord': (['u64', 'u64'], ['checked-access', 'physical-read'], '703cb786d428b9b309a93ff6212164ce40c6bbb8295d3a633765204d68b29bb0'),
 'Lemma.Boot.ProductExecuted.verifySector': (['u64'], ['checked-access', 'physical-read'], '8227297fce2fa37347c24b8e1ce5266f591d9734e194ac40737761e23e5ea20f'),
 'Lemma.Boot.ProductExecuted.reservedStep': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'physical-read'], '252329d67dfd01765f64a0cd532896ce91bbe31d8a3680312bb6a18b3a1d8f99'),
 'Lemma.Boot.ProductExecuted.validateMetadata': (['u64'], ['checked-access', 'physical-read'], '0a1fb159c8448799b3f09b3d425774568e2ffe9aab282cd1f0c680b3f2e6eac7'),
 'Lemma.Boot.ProductExecuted.readMetadata': (['u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-read', 'physical-write'], '16fd5d7ba620bd4c0a2fac86dbe30d0b372e11d72365313ccc9993a0ef7c540b'),
 'Lemma.Boot.ProductExecuted.compareMetadataStep': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'physical-read'], '87a0c6485cfe837930aeac61a87f92af325abca12576a20c844fbe301b76f39e'),
 'Lemma.Boot.ProductExecuted.selectedMetadata': ([], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-read', 'physical-write'], '9bc280e05b02e93c5d4dc70cf9bbbf1c99e84a700841f162c1e4254d423425a8'),
 'Lemma.Boot.ProductExecuted.writeWord': (['u64', 'u64', 'u64'], ['checked-access', 'physical-write'], 'fa0ddf4d30e7842dd47af8a0a947c60cd35dc485724582d4ce57f36bed717841'),
 'Lemma.Boot.ProductExecuted.bufferWrite': (['u64', 'u64'], ['checked-access', 'mmio-write', 'io-order'], '03a35dad8e82abc42e83f64cc1c4fadf3e04750842fc5ccc5779f73fef47e5a7'),
 'Lemma.Boot.ProductExecuted.stageBufferStep': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'mmio-write', 'io-order', 'physical-read'], '412b4623d298f7008bab499e7cde54bdc1fcd1bcf43067ecbe95ce6a749abec5'),
 'Lemma.Boot.ProductExecuted.writeSector': (['u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-read'], '11c67a01777471b321e8612623b5ef8c8994c9d908cfef3fbc8c5226ada2d5c2'),
 'Lemma.Boot.ProductExecuted.publishMetadata': (['u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-read', 'physical-write'], '483d3128456ffb28632161d34b2d6ce81a43296df3e802a91c62956fe7c07801'),
 'Lemma.Boot.ProductExecuted.confirm': (['u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-read', 'physical-write'], '186f668644dbad1c713485f0e5169e70e1a768c0f95655793be96fb82b6f27d0'),
 'Lemma.Platform.LemmaSim.BootHealthExecuted.recordResult': (['u8', 'u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-write'], '9596e3d57c5484af760f7ad467ceb90dabb09fa637348b94cbad6f54504c39af'),
 'Lemma.Platform.LemmaSim.BootHealthExecuted.confirm': (['u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-read', 'physical-write'], '025cdbc0b3853002b9e4463c9084f4a07ead7803c828d30323435e042e791f1d'),
 'Lemma.Platform.LemmaSim.BootHealthExecuted.fullRefresh': (['u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-read', 'physical-write'], '7b2987a83324f77fe0b6ec13a44c08ec55c57088aa292216c558ae83527ff2e2'),
 'Lemma.Platform.LemmaSim.BootHealthExecuted.step': ([], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-read', 'physical-write'], '7a0a97381349fc9f326baa92a23b744813e441803295d6961f6421be7c465e4b'),
 'Lemma.Platform.LemmaSim.NotebookKernel.modernExecutedStep': (['u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'machine-state', 'interrupt-state', 'physical-read', 'physical-write', 'firmware-call', 'address-space', 'privilege-transition', 'wait-state'], '0d82ee353a165c706973dc0d1f2b83e782912e4b0400e4bed39742831c210de8'),
 'Lemma.Platform.LemmaSim.NotebookKernel.modernUSBExecutedStep': ([], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'machine-state', 'interrupt-state', 'physical-read', 'physical-write', 'firmware-call', 'address-space', 'privilege-transition', 'wait-state'], 'b1e9a851fc3fd77e8919ae843519760b5649dc59c3f98c9e607f32368d5a02f2'),
 'Lemma.Platform.LemmaSim.NotebookKernel.modernProductExecutedStep': ([], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'machine-state', 'interrupt-state', 'physical-read', 'physical-write', 'firmware-call', 'address-space', 'privilege-transition', 'wait-state'], '2c01dbb975f361f8960b320f5e122d4b4a9d694ee596b1018e29604361f5e409'),
 'Lemma.Platform.LemmaSim.NotebookKernel.bootModernExecuted': (['u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'machine-state', 'interrupt-state', 'physical-read', 'physical-write', 'firmware-call', 'address-space', 'instruction-sync', 'privilege-transition', 'wait-state', 'may-diverge'], '014782077bd25e9ba48bc74b279e67616fa40619d3377d1efcf1fcabb2600336'),
 'Lemma.Platform.LemmaSim.NotebookKernel.siliconProductExecutedBoot': ([], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'machine-state', 'interrupt-state', 'physical-read', 'physical-write', 'firmware-call', 'address-space', 'instruction-sync', 'privilege-transition', 'wait-state', 'may-diverge'], 'dd37ac912456ae7a3842609e5aca6cf6c894a8a7bad55080e6856423f698b197'),
 'Lemma.Platform.LemmaSim.NotebookKernel.deviceCallModernExecutedBulk': (['u64', 'u64', 'u64', 'u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'machine-state', 'physical-read', 'physical-write', 'firmware-call'], 'b080a1fea5cb6c0f9a40a7d67cdece25b73de6d3cbb6aa0c699fff6ef14da03f'),
 'Lemma.Platform.LemmaSim.NotebookKernel.dispatchModernExecutedBulk': (['u64', 'u64', 'u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'machine-state', 'interrupt-state', 'physical-read', 'physical-write', 'firmware-call', 'address-space', 'wait-state'], '82ba989292682755fc1cf992365cb8f9873d018dcd7b6654c44f8c6cc3f65574'),
 'Lemma.Platform.LemmaSim.NotebookKernel.dispatchProductExecutedBulk': (['u64', 'u64', 'u64'], ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'machine-state', 'interrupt-state', 'physical-read', 'physical-write', 'firmware-call', 'address-space', 'wait-state'], 'aa429196759dde1e396362c1062681d5c102eadeaef81cf5f38c1f45a96cc9fd'),
}
POST_BODIES = {'Lemma.Platform.LemmaSim.DescriptorDTB.literalWordNext': 'fe832b6a6b3465d0fb93a737954b4b86b9c9f07279160fea23eb2b820b0423ea', 'Lemma.Platform.LemmaSim.DescriptorDTB.literalWordExecuted': '31e5eb77930481963e1d49c49b12f331aea88df458e7eff6872bfbb6f11a148a', 'Lemma.Platform.LemmaSim.DescriptorDTB.tokenStepExecuted': '631654ec6b18f590141c85c6630a9c22aecf6efdd6913a745fd99ab89cf50402'}
CALLER_INVENTORIES = {False: 'c0268d31dfd45042719dd5a851edb721c0872c6b7e40f1e568a4a19b5d672d7d', True: '8b84e44860ff684afc848afa5b9729cb7e93624f6cfd127380e6ca1af0637302'}

def _successor(source):
 return 'executed' in source.lower() and source.startswith(('Lemma.Platform.LemmaSim.','Lemma.Platform.Silicon.Binding','Lemma.Drivers.Paper.','Lemma.Kernel.Memory.AddressSpace.','Lemma.Boot.Product'))

def validate(ir,unit,*,optimized):
 rows={canonical(row['source']):row for row in unit.get('functions',[])}
 reached={source for source in rows if _successor(source)}
 if unit.get('configuration')!=CONFIGURATION or unit.get('role')!='kernel':
  if reached:raise Core0Error('Paper3 declarations escaped exact Product10 kernel selection')
  return None
 if (unit.get('contract_version')!='core0-kernel-v0.7' or
     reached!={s for s in EXPECTED if _successor(s)} or
     len(rows)!=len(unit.get('functions',[]))):
  raise Core0Error('Paper3 complete declaration/Kernel7 inventory differs')
 names={row['symbol']:source for source,row in rows.items()};observed={}
 for source,(args,effects,digest) in EXPECTED.items():
  row=rows.get(source)
  if row is None or (row.get('args'),row.get('effects'))!=(args,effects):
   raise Core0Error('Paper3 source signature/effects differ: '+source)
  if optimized and source not in POST_BODIES:continue
  actual=hashlib.sha256(normalized(ir,row,names).encode()).hexdigest()
  if actual!=(POST_BODIES[source] if optimized else digest):
   raise Core0Error('Paper3 staging/discovery/accepted execution/reset/health/metadata authority differs: '+source)
  observed[source]=actual
 from audit_kernel import _ir_definition_body
 edges=[]
 for source,row in rows.items():
  body=_ir_definition_body(ir,row['symbol'])
  if body is None:continue
  for target in set(re.findall(r'\bcall\b[^\n]*?@([A-Za-z0-9_.$-]+)\(',body)):
   if names.get(target) in EXPECTED:edges.append((source,names[target]))
 callers=hashlib.sha256(json.dumps(sorted(edges),separators=(',',':')).encode()).hexdigest()
 if callers!=CALLER_INVENTORIES[bool(optimized)]:
  raise Core0Error('Paper3 authority caller inventory differs')
 return {'contract_version':'lemma-paper-executed-v3','configuration':CONFIGURATION,
  'stage_offset':3584,'bytes':512,'executed_offsets':[192,200,208,216,224,232],
  'pre_or_post':'post' if optimized else 'pre','complete_body_identities':observed,
  'caller_inventory_sha256':callers,'scope':'Checked compiled authority only; actual Product10 ROM Ready and trial confirmation require separate results'}
