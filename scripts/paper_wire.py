"""Fail-closed artifact authority for USBWire11 discovery and Paper3.

The selected genuine source/LLVM corpus supplies independently reviewed exact
body pins. No target code, device transaction, journal or policy runs here.
"""
from __future__ import annotations
import hashlib
import json
import re
from core0_common import Core0Error
from paper_next import canonical, normalized

CONFIGURATIONS = frozenset(('lemmasim-silicon-usb-wire-bulk-notebook',
                           'lemmasim-silicon-usb-wire-bulk-initialize'))
# Filled only from the genuine final kernel export after source, interface and
# error/caller semantics are independently inspected; absence never succeeds.
EXPECTED = {'Lemma.Drivers.Paper.initializeExecuted': ([],
                                            ['checked-access', 'mmio-read', 'io-order'],
                                            '69ecbbc0a5994932f19cb630ee4f7833f9b179e90bb26ba9a2326bf5e377783d'),
 'Lemma.Drivers.Paper.uploadNext': (['u64', 'u64', 'u64', 'u64', 'u64'],
                                    ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-read'],
                                    '397b3df89466969175a03673d72f18784a8cb32f1e25d4e82315a87b80f9dfd0'),
 'Lemma.Drivers.Paper.uploadOffsetNext': (['u64', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                          ['checked-access', 'mmio-read', 'mmio-write', 'io-order', 'physical-read'],
                                          '871073f696f1c93737b85460fd40d108f0ec61fff41cc25c431260ce2cbda22d'),
 'Lemma.Drivers.Paper.uploadWordNext': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                        ['checked-access', 'mmio-write', 'io-order', 'physical-read'],
                                        '88d1e36f8a5aaf6ebdb04df92f9c124f0e35b781bda90b5a92d33dddaa30f2cc'),
 'Lemma.Platform.LemmaSim.Descriptor.expectedBindingWire': (['u64', 'u64'],
                                                            [],
                                                            'c4e4e5f5c3acb1f560483e468f21094a0b6c3f6c3dc2c6bbadcd4b926d26b16e'),
 'Lemma.Platform.LemmaSim.Descriptor.fieldsStepWire': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                                       ['checked-access', 'mmio-read', 'io-order'],
                                                       '8fc57856e5d8f88d5545940922fbcd9986ded096ff2c99b2660422266f80f3bf'),
 'Lemma.Platform.LemmaSim.Descriptor.fieldsStepWire.compare': (['u64', 'u32', 'u64'],
                                                               ['checked-access', 'mmio-read', 'io-order'],
                                                               '463dd08f4bf6de2fa92ccbcf732bfd840f76c04581d5ba9b005f8786a09a3c4c'),
 'Lemma.Platform.LemmaSim.Descriptor.geometryWire': (['u64'],
                                                     ['checked-access',
                                                      'mmio-read',
                                                      'io-order',
                                                      'physical-read',
                                                      'physical-write'],
                                                     'b1bc71b18a489f69b48aad99dac92feb43c1d15c0ea63a62b19208283e3b5051'),
 'Lemma.Platform.LemmaSim.Descriptor.validateBindingWire': (['u64'],
                                                            ['checked-access',
                                                             'mmio-read',
                                                             'io-order',
                                                             'physical-read',
                                                             'physical-write'],
                                                            'b1935b9ad0f39d3e932a01ed21a06c631753642e7db8b791f10e2ba480dc30fc'),
 'Lemma.Platform.LemmaSim.Descriptor.validateBindingWire.admitted': (['u64'],
                                                                     ['checked-access',
                                                                      'mmio-read',
                                                                      'io-order',
                                                                      'physical-read',
                                                                      'physical-write'],
                                                                     'f5fc9917aacb45e13b59b9976093eb92c3efd8bc3c03697910e90c1577096fb7'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.actualDevicesExecuted': ([],
                                                                 ['checked-access', 'mmio-read', 'io-order'],
                                                                 '80f67127d43b3fb76e5c4437d92c4e280a49404139e3040f9fc033f5b5505b9f'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.endNodeWire': (['u64', 'u64'],
                                                       ['checked-access', 'physical-read', 'physical-write'],
                                                       '8cca440ba15bd8dca3ff446d4ffd299c37230d971f1106f6df36f61fcd9f00e1'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.equalLiteralExecuted': (['u64', 'u64', 'u64'],
                                                                ['checked-access', 'physical-read'],
                                                                '1d230e487fc11c829f03ad46f46ff2aad5ae81984e62133f7257d654f8dfb022'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.equalLiteralWire': (['u64', 'u64', 'u64'],
                                                            ['checked-access', 'physical-read'],
                                                            'a246e45d095b406f3f5c3c460bd4b447ec5e40cccc6cb070f59ed8d50f1663c5'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.executedProperty': (['u64', 'u64'],
                                                            ['checked-access', 'physical-read', 'physical-write'],
                                                            '88657bf15fdd712589ca239e3cf0514afc49371f1b9ff100b27a175f995e3adb'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.executedRegisterStep': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                                                ['checked-access', 'physical-read'],
                                                                '0c6cdfc24e53fc4bae22930ff9ffcb7aec369106b00c74153134dfc11823c0f4'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.findCodeWire': (['u64', 'u64', 'u64', 'u64'],
                                                        ['checked-access', 'physical-read'],
                                                        'ea99bd6892ff9818f6341f16e165928139f4c04db9cde16dbff63478564924c5'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.findStepWire': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                                        ['checked-access', 'physical-read'],
                                                        'f3ff7f2d37501d50e8f3b4ce61313eb358a6de285f05394c6779745e0e9f87fe'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.leafPropertyExecuted': (['u64', 'u64', 'u64', 'u64'],
                                                                ['checked-access', 'physical-read', 'physical-write'],
                                                                '0892f4074e915b8030ee99ea6bbd2ce2f450b1f3a57503666f6a4aeb92417ce0'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.leafPropertyWire': (['u64', 'u64', 'u64', 'u64'],
                                                            ['checked-access', 'physical-read', 'physical-write'],
                                                            '8f7e32b0fb6b2a0ee87f3aa54ebdf583061db9f3c2397a6716848a14934fd3ca'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalLengthExecuted': (['u64'],
                                                                 [],
                                                                 'c441f3bfa30e93a0ef2d1233a6c23d1a6da68a7a01c45f0ef61f8e85be291480'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalLengthNext': (['u64'],
                                                             [],
                                                             '2cb065efbb0087aadcee02aba000d1d6b75d2cbff429d610ab68af76a4fcafe2'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalLengthWire': (['u64'],
                                                             [],
                                                             'da92951a5f446d7162dd201f8d54f4d74ec9613f93877ee40c4979783e3eb263'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalWordExecuted': (['u64', 'u64'],
                                                               [],
                                                               '08876c2db152ac8c6eda246718539f42b54699aad09cac165a193c728617711e'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalWordNext': (['u64', 'u64'],
                                                           [],
                                                           'ada856e4b2c73bc306023c4690ba4617d77f04f15c1f8dd388cbedbfac99807f'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalWordWire': (['u64', 'u64'],
                                                           [],
                                                           '0653f4d181ee26c427eeb847dc86fd5d80023eae53e98c122f83db264d64a6d1'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.matchStepExecuted': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                                             ['checked-access', 'physical-read'],
                                                             '21a08bcb119018e8bd1132a60b43ce74ac539d5538ed8fe37595c940633329b9'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.matchStepWire': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                                         ['checked-access', 'physical-read'],
                                                         '01792a5ca21a91fa1e05824cb16d436393bf6ee5c25fbf9ac60dca8bbde43624'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.propertyWire': (['u64', 'u64', 'u64'],
                                                        ['checked-access', 'physical-read', 'physical-write'],
                                                        '3888d8d01b51a220565dfbe59e346b15d6de6dc47556fbf72931b654ac5121af'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.tokenStepWire': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                                         ['checked-access', 'physical-read', 'physical-write'],
                                                         '7be87f2702ba8d800a4942743fa23ba7788c4a0af02e69dcae64018684f31e87'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.validateBindingWireCore': (['u64', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                                                   ['checked-access',
                                                                    'mmio-read',
                                                                    'io-order',
                                                                    'physical-read',
                                                                    'physical-write'],
                                                                   'e95e5eaf69dd635960e113274908f6faee7e6bf0372df636a564d955449947b7'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.validateSiliconUSBWire': (['u64', 'u64', 'u64', 'u64', 'u64'],
                                                                  ['checked-access',
                                                                   'mmio-read',
                                                                   'io-order',
                                                                   'physical-read',
                                                                   'physical-write'],
                                                                  '70a776d02aa1e47130a0be0069db811427d270c6e1ce05ea72b4fd8ee6f1d56d'),
 'Lemma.Platform.LemmaSim.DeviceService.bulkUploadStepNext': (['u32', 'u32', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                                              ['checked-access',
                                                               'mmio-read',
                                                               'mmio-write',
                                                               'io-order',
                                                               'physical-read'],
                                                              '1944203fd010cdb478006cc5befed984ed36bfc18c603ab56ab87016b1ccfeb5'),
 'Lemma.Platform.LemmaSim.DeviceService.surfaceV2Next': (['u64', 'u64', 'u64', 'u64', 'u64', 'u64'],
                                                         ['checked-access',
                                                          'mmio-read',
                                                          'mmio-write',
                                                          'io-order',
                                                          'physical-read',
                                                          'physical-write'],
                                                         '945925d35cd830f20b719533b10b9cd08d47c0b80282796c12f2136c38a85fdf'),
 'Lemma.Platform.LemmaSim.DeviceService.uploadBulkNext': (['u64', 'u64', 'u64'],
                                                          ['checked-access',
                                                           'mmio-read',
                                                           'mmio-write',
                                                           'io-order',
                                                           'physical-read',
                                                           'physical-write'],
                                                          '8d7e795b8591ccd9fd6c67b02428eb303e9ece5651431c1b3278268be5899bde'),
 'Lemma.Platform.LemmaSim.DeviceService.uploadOrdinaryNext': (['u64', 'u64', 'u64'],
                                                              ['checked-access',
                                                               'mmio-read',
                                                               'mmio-write',
                                                               'io-order',
                                                               'physical-read',
                                                               'physical-write'],
                                                              '65dd460340c6ffdac1114f80fb889f3c43048665c85460ac39ed85f6aa49811a'),
 'Lemma.Platform.LemmaSim.NotebookKernel.acceptPendingWire': (['u64'],
                                                              ['checked-access',
                                                               'mmio-read',
                                                               'mmio-write',
                                                               'io-order',
                                                               'physical-read',
                                                               'physical-write'],
                                                              'c152a55287b13e974a966c3ea33d1d48ce13fa3ecd1ac5cc71f60b9e2ba64ea7'),
 'Lemma.Platform.LemmaSim.NotebookKernel.bootWire': (['u64', 'u64'],
                                                     ['checked-access',
                                                      'mmio-read',
                                                      'mmio-write',
                                                      'io-order',
                                                      'machine-state',
                                                      'interrupt-state',
                                                      'physical-read',
                                                      'physical-write',
                                                      'firmware-call',
                                                      'address-space',
                                                      'instruction-sync',
                                                      'privilege-transition',
                                                      'wait-state',
                                                      'may-diverge'],
                                                     'cbd84fe882c8f5a044f1a3b1a6acc35073318161a474f503108d7828a3b67350'),
 'Lemma.Platform.LemmaSim.NotebookKernel.constructWire': (['u64', 'u64'],
                                                          ['checked-access',
                                                           'mmio-read',
                                                           'mmio-write',
                                                           'io-order',
                                                           'machine-state',
                                                           'physical-read',
                                                           'physical-write',
                                                           'firmware-call',
                                                           'address-space',
                                                           'instruction-sync'],
                                                          'bd38d143f5a724e865658368b1b547cb43871d20fb75280500dd1eaeb422b0e4'),
 'Lemma.Platform.LemmaSim.NotebookKernel.deviceCallWireBulk': (['u64', 'u64', 'u64', 'u64', 'u64'],
                                                               ['checked-access',
                                                                'mmio-read',
                                                                'mmio-write',
                                                                'io-order',
                                                                'machine-state',
                                                                'physical-read',
                                                                'physical-write',
                                                                'firmware-call'],
                                                               'b31a7b8742ffad569b36b49fa2e5730d93ab072de986b9aae8b30702791375f4'),
 'Lemma.Platform.LemmaSim.NotebookKernel.dispatchUSBWireBulk': (['u64', 'u64', 'u64'],
                                                                ['checked-access',
                                                                 'mmio-read',
                                                                 'mmio-write',
                                                                 'io-order',
                                                                 'machine-state',
                                                                 'interrupt-state',
                                                                 'physical-read',
                                                                 'physical-write',
                                                                 'firmware-call',
                                                                 'address-space',
                                                                 'wait-state'],
                                                                '917c49cfb3c603f193ab6cfd72c55daa351615b40ffa070af597c21e7665de09'),
 'Lemma.Platform.LemmaSim.NotebookKernel.dispatchWireBulk': (['u64', 'u64', 'u64', 'u64'],
                                                             ['checked-access',
                                                              'mmio-read',
                                                              'mmio-write',
                                                              'io-order',
                                                              'machine-state',
                                                              'interrupt-state',
                                                              'physical-read',
                                                              'physical-write',
                                                              'firmware-call',
                                                              'address-space',
                                                              'wait-state'],
                                                             '5ce51eaefdd47f789db080584cb243a57d4696f517a75cfffe415c6bda7ce841'),
 'Lemma.Platform.LemmaSim.NotebookKernel.siliconUSBWireBoot': ([],
                                                               ['checked-access',
                                                                'mmio-read',
                                                                'mmio-write',
                                                                'io-order',
                                                                'machine-state',
                                                                'interrupt-state',
                                                                'physical-read',
                                                                'physical-write',
                                                                'firmware-call',
                                                                'address-space',
                                                                'instruction-sync',
                                                                'privilege-transition',
                                                                'wait-state',
                                                                'may-diverge'],
                                                               '0f8c3c35105c346710652dbd70ec12edb36c963740cd72841e3fd7fadd657f1f'),
 'Lemma.Platform.LemmaSim.NotebookKernel.wireStep': (['u64'],
                                                     ['checked-access',
                                                      'mmio-read',
                                                      'mmio-write',
                                                      'io-order',
                                                      'machine-state',
                                                      'interrupt-state',
                                                      'physical-read',
                                                      'physical-write',
                                                      'firmware-call',
                                                      'address-space',
                                                      'privilege-transition',
                                                      'wait-state'],
                                                     '819d8bb1656519e95e6c6db9aa3a0729f08aec542215c2483350a24acedd9705'),
 'Lemma.Platform.LemmaSim.NotebookKernel.wireUSBStep': ([],
                                                        ['checked-access',
                                                         'mmio-read',
                                                         'mmio-write',
                                                         'io-order',
                                                         'machine-state',
                                                         'interrupt-state',
                                                         'physical-read',
                                                         'physical-write',
                                                         'firmware-call',
                                                         'address-space',
                                                         'privilege-transition',
                                                         'wait-state'],
                                                        '938fcf6be3e06b22048ea5dd05ab52ef6e5a490b057e10fd5c7f776180137960'),
 'Lemma.Platform.Silicon.BindingUSBWire.frame_pool_bytes': ([],
                                                            [],
                                                            '4fa0acfd3ce320ff2bf0018f7650ae87545467117c0507cfd364346ccf03e8df'),
 'Lemma.Platform.Silicon.BindingUSBWire.power_base': ([],
                                                      [],
                                                      'f9ec268ee18f606b275f97360decd953bffbfb7cab1d3fc2c49187a6b436e9a8')}
POST_BODIES = {'Lemma.Drivers.Paper.initializeExecuted': '0ffad45205f89c9d9785bf6d00d01e9e7e138a408fa473d9dba1d8620ad43a7c',
 'Lemma.Drivers.Paper.uploadNext': 'ceacda363fbc56ad14619cdd98fd21d54c04866c682943a7ecf2b96d64edfdcb',
 'Lemma.Drivers.Paper.uploadOffsetNext': 'a9686bf4ae6936cdc75f6fa42d9c031ec454ca0b6a5c1183418e8293f717f309',
 'Lemma.Drivers.Paper.uploadWordNext': 'fe104011af00b39b56c4fc30dfafa4c9074121a7dae8b694ec96f775ff2bcb3f',
 'Lemma.Platform.LemmaSim.Descriptor.expectedBindingWire': 'e376ea4f343fe570d41ae57be6cf768e1e7175ecb8c6e729dabbb89e43297cc7',
 'Lemma.Platform.LemmaSim.Descriptor.fieldsStepWire': 'c7009ea79ecee91c9e71f6d821d5e12c7b0b7728650c3b17a6d4e886e5de0c5d',
 'Lemma.Platform.LemmaSim.Descriptor.fieldsStepWire.compare': 'ba2bd9fbf275ab7fcfd7502bd77f4a3c53d03ba91f8b7978c0f80ff0f2c8be15',
 'Lemma.Platform.LemmaSim.Descriptor.geometryWire': '39f634e10b5728c17366256667cd4230b25a6db4d186cc2439240a28710d504c',
 'Lemma.Platform.LemmaSim.Descriptor.validateBindingWire': '4aa626855b2522ab753bde754bbd6ff1b4605689896b753f28ffa24b9f74a463',
 'Lemma.Platform.LemmaSim.Descriptor.validateBindingWire.admitted': '048b320f808b8cd2fa89e344fa0eed365eb4dc5767d5a5e63bcc098b062a8079',
 'Lemma.Platform.LemmaSim.DescriptorDTB.actualDevicesExecuted': '92522a39058d1c4fdc69ee0bcc477dac32393a6d9ed22cc40a07842f3def2974',
 'Lemma.Platform.LemmaSim.DescriptorDTB.endNodeWire': '06f192a19d4939aebd61ca01e32530eb93e2fcedaf9f927689c10e5535365e9a',
 'Lemma.Platform.LemmaSim.DescriptorDTB.equalLiteralExecuted': '7913b75af7a61ce954d3148231dc70e7c4d6b2fb740354be35e6c0752053a248',
 'Lemma.Platform.LemmaSim.DescriptorDTB.equalLiteralWire': '9127d030a04c06dc289d619c77f0df69ddf4eb254677fab9b467d252df0559fb',
 'Lemma.Platform.LemmaSim.DescriptorDTB.executedProperty': '02d954fed44a774bc6e5a5840927b8dfe8c17c95673d446021d3591f3eb30144',
 'Lemma.Platform.LemmaSim.DescriptorDTB.executedRegisterStep': '88fefdfe7900a27a215a09cd08724ef8530f53f4972d4eed3ea63bf5a0630ad3',
 'Lemma.Platform.LemmaSim.DescriptorDTB.findCodeWire': '86eff48819db08cd606a34ebe208815726be754ae47285e4b640bb18cd727c0e',
 'Lemma.Platform.LemmaSim.DescriptorDTB.findStepWire': '48a91744dfa6aba16af7f5b808f6627bcff7ab17105a221a58439b1f3474eae6',
 'Lemma.Platform.LemmaSim.DescriptorDTB.leafPropertyExecuted': '1cf3441d346d4fe601a5d6e451989d9fa659cbedf81dd6789e8f1fe7c968678c',
 'Lemma.Platform.LemmaSim.DescriptorDTB.leafPropertyWire': '0ccc2a7082b7474b4721333a551951b225a6cc10e920bbfc8bc0c461f1acd11f',
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalLengthExecuted': 'd371316e921a182f068afb25eed8a21cc32e9a76c419f16fb1d5e6e963368760',
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalLengthNext': '0431978d2b4e2b35100e09db0d1985fc2685a858f28ba45dbd28c226dbedd80a',
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalLengthWire': 'd44fd538eeba50e3aaf76770cfeea8f42339d9eddcf7f520451e8d1743998b2d',
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalWordExecuted': '31e5eb77930481963e1d49c49b12f331aea88df458e7eff6872bfbb6f11a148a',
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalWordNext': 'fe832b6a6b3465d0fb93a737954b4b86b9c9f07279160fea23eb2b820b0423ea',
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalWordWire': 'bfb4367406e321ce0b8fcf4c21187722e7369016a112bb35133b2989e59c9671',
 'Lemma.Platform.LemmaSim.DescriptorDTB.matchStepExecuted': '0c525f9cf1078747353f550c569438b9528e03e7c45a666e1dc407166fc8a22d',
 'Lemma.Platform.LemmaSim.DescriptorDTB.matchStepWire': '3884de3002b54b0920b81bb57038aa243e272bba9d0f081378d4c052a445dd6e',
 'Lemma.Platform.LemmaSim.DescriptorDTB.propertyWire': '608dcf36fe17a11df9866c94712323f036db89967fe696a8b78496640bfefbba',
 'Lemma.Platform.LemmaSim.DescriptorDTB.tokenStepWire': '6116354d27171a12446ae11767ac21f43289a4610d9673f63d3aa809a87f1acd',
 'Lemma.Platform.LemmaSim.DescriptorDTB.validateBindingWireCore': 'f764b6751337d06fea56f302c3b278800d7e1a8d6fd0c7a059f03976ea1dc327',
 'Lemma.Platform.LemmaSim.DescriptorDTB.validateSiliconUSBWire': 'ef5e867a93c9bebb1dd37bded6b8426da794084795cf134f1d624d45cf3518b9',
 'Lemma.Platform.LemmaSim.DeviceService.bulkUploadStepNext': '4a356778644d1a813c29cd809b0a1d95f02ffefed99ec10e6ccdba210d4e3e1e',
 'Lemma.Platform.LemmaSim.DeviceService.surfaceV2Next': '9e09f3016afdcd9f5574f57b1335d7f57d7187f74ee66e7964402410364a1a4a',
 'Lemma.Platform.LemmaSim.DeviceService.uploadBulkNext': '0815f6f7d4aa51fb21f00919b93b999d6bd11ac68e1163000d013bc1a8938ecb',
 'Lemma.Platform.LemmaSim.DeviceService.uploadOrdinaryNext': '3f70688d60d50e8505558abb33f528a3e7a966983b100cb592890d07fe577b98',
 'Lemma.Platform.LemmaSim.NotebookKernel.acceptPendingWire': 'f58d419a8f5513abdd53de6ba595ee2ffa71e0a49010216d57421027f32e63b5',
 'Lemma.Platform.LemmaSim.NotebookKernel.bootWire': '3b1bed1becaf4cd465e6ffd3293b3dee51085933465f01ac9995128eefda73d2',
 'Lemma.Platform.LemmaSim.NotebookKernel.constructWire': '11527af55ad6e958e69585cacf60366e970640c52f47f8b07ac79535190ecbb2',
 'Lemma.Platform.LemmaSim.NotebookKernel.deviceCallWireBulk': '904275cc784ea67927bfb7586c20d7795288d43670f9740db0cece31d909ea8b',
 'Lemma.Platform.LemmaSim.NotebookKernel.dispatchUSBWireBulk': '34005c9134939c49b3806958f941326f605b02d901cbed2b764252a8cd35707f',
 'Lemma.Platform.LemmaSim.NotebookKernel.dispatchWireBulk': 'e83294f709aab3a180dbe7e991ef4b8777002baf93c15b02199644a290d65740',
 'Lemma.Platform.LemmaSim.NotebookKernel.siliconUSBWireBoot': '8394bac5693a7f0fb1d2bb5e1fedaafb5f65446ef9cc4c8c06142a3e45dcd2b5',
 'Lemma.Platform.LemmaSim.NotebookKernel.wireStep': 'e90f65030a0662e1f5fc0d1277094685e4ec227838795097f47ff59332600d20',
 'Lemma.Platform.LemmaSim.NotebookKernel.wireUSBStep': '9b12cb35de563f3b8c1c18c1ca5ff694d5b7e5c547f21dcfb00288277977dfce',
 'Lemma.Platform.Silicon.BindingUSBWire.frame_pool_bytes': '4fa0acfd3ce320ff2bf0018f7650ae87545467117c0507cfd364346ccf03e8df',
 'Lemma.Platform.Silicon.BindingUSBWire.power_base': 'f9ec268ee18f606b275f97360decd953bffbfb7cab1d3fc2c49187a6b436e9a8'}
CALLER_INVENTORIES = {False: 'd62f365a7ef815168be208436160263abb2b3c4f837deb532df2661fd35a0a87', True: '201f18921a5fd7ad256095968b8a9c21f358cfee2b3e03daccc4b36719b8eae5'}


LITERALS = {
 65: [0x68702c616d6d656c,0x6f69737265762d79,0x6e],
 66: [0x68702c616d6d656c,0x656c706d61732d79,0x7a682d],
 68: [0x65642c616d6d656c,0x6e656d706f6c6576,0x63616d2d74],
 81: [0x73752c616d6d656c,0x6563697665642d62,0x31762d657269772d],
}

def literal_aliases(ir, unit):
    from audit_kernel import _ir_definition_body, _line_functions
    rows=[r for r in unit.get('functions',[]) if canonical(r['source'])=='Lemma.Platform.LemmaSim.DescriptorDTB.literalWordWire']
    if not rows:return {}
    if len(rows)!=1 or unit.get('configuration') not in CONFIGURATIONS or unit.get('role')!='kernel' or unit.get('contract_version')!='core0-kernel-v0.6' or (rows[0]['args'],rows[0]['effects'])!=(['u64','u64'],[]):
        raise Core0Error('USBWire literal source/signature/role escaped exact Kernel6 selection')
    row=rows[0];symbol=row['symbol'];owners=_line_functions(ir.splitlines());result={};found=[]
    pattern=r'^@(switch\.table\.'+re.escape(symbol)+r'(?:\.\d+)?) = private unnamed_addr constant \[3 x i64\] \[(.*?)\], align 8$'
    body=_ir_definition_body(ir,symbol)
    for name,raw in re.findall(pattern,ir,re.M):
        values=[int(x) for x in re.findall(r'i64 (-?\d+)',raw)]
        codes=[code for code,wanted in LITERALS.items() if values==wanted]
        if len(codes)!=1 or len(re.findall(r'@'+re.escape(name)+r'(?![A-Za-z0-9_.$-])',ir))!=2:
            raise Core0Error('USBWire immutable UTF8 pool content/extent/use differs')
        uses=[owners[i] for i,line in enumerate(ir.splitlines()) if re.search(r'@'+re.escape(name)+r'(?![A-Za-z0-9_.$-])',line) and not line.startswith('@')]
        if uses!=[symbol] or len(re.findall(r'getelementptr inbounds nuw \[3 x i64\], ptr @'+re.escape(name)+r', i64 0, i64 %arg1',body))!=1:
            raise Core0Error('USBWire literal is not its one source-owned typed index')
        code=codes[0];found.append(code);result[name]='wire.literal.'+str(code)
    if sorted(found)!=sorted(LITERALS):raise Core0Error('USBWire complete UTF8 readonly pool inventory differs')
    return result

def body_normalized(ir,row,names,aliases):
    body=normalized(ir,row,names)
    for raw,stable in sorted(aliases.items(),key=lambda pair:-len(pair[0])):
        body=body.replace('@'+raw,'@'+stable)
        if raw=='switch.table.'+row['symbol']:
            body=body.replace('@switch.table.'+canonical(row['source']),'@'+stable)
    return body

INITIALIZER_WRAPPER = ([],
 ['checked-access',
  'mmio-read',
  'mmio-write',
  'io-order',
  'machine-state',
  'interrupt-state',
  'physical-read',
  'physical-write',
  'firmware-call',
  'address-space',
  'instruction-sync',
  'privilege-transition',
  'wait-state',
  'may-diverge'],
 'c3d8fa2eb75b48ab9ff2f9d94b6eddcf8653b3bbc23daedb788cbbf55249e014')
INITIALIZER_POST = '83ec7d5bc1395a6a1947da8649bb221905a43e55c91aad0d43ec274d4c890494'
INITIALIZER_CALLERS = {False: '2c2047ef8564af798b1bbb0e9d1a776433d10807e186ae0b1ee3b200847c6a5e', True: 'ae2e6948d4270a039261442d56b72d004a19fe9424400ffe90101395d1d1de52'}

def _successor(source):
    return 'wire' in source.lower() and source.startswith((
        'Lemma.Platform.LemmaSim.', 'Lemma.Platform.Silicon.BindingUSBWire'))


def validate(ir,unit,*,optimized):
    rows={canonical(row['source']):row for row in unit.get('functions',[])}
    reached={source for source in rows if any(x in source.lower() for x in ('wire','next','executed')) and source.startswith(('Lemma.Platform.LemmaSim.','Lemma.Platform.Silicon.Binding','Lemma.Drivers.Paper.','Lemma.Kernel.Memory.AddressSpace.'))}
    cfg=unit.get('configuration')
    if cfg not in CONFIGURATIONS or unit.get('role')!='kernel':
        if any(_successor(source) for source in rows):raise Core0Error('USBWire declarations escaped exact Kernel6 deployment')
        return None
    expected=dict(EXPECTED);post_bodies=dict(POST_BODIES);caller_inventory=CALLER_INVENTORIES
    if cfg.endswith('-initialize'):
        old='Lemma.Platform.LemmaSim.NotebookKernel.siliconUSBWireBoot';new='Lemma.Platform.LemmaSim.NotebookKernel.siliconUSBWireInitializeMedium'
        del expected[old];del post_bodies[old]
        expected[new]=INITIALIZER_WRAPPER;post_bodies[new]=INITIALIZER_POST;caller_inventory=INITIALIZER_CALLERS
    if unit.get('contract_version')!='core0-kernel-v0.6' or len(rows)!=len(unit.get('functions',[])) or reached!=set(expected):
        raise Core0Error('USBWire complete source/Kernel6 inventory differs')
    if any(source.startswith(('Lemma.Boot.Product','Lemma.Platform.LemmaSim.BootHealth')) or source.endswith(('.initProduct','.prepareManagedProduct','.configureProduct')) for source in rows):
        raise Core0Error('USBWire acquired product boot/NV authority')
    names={r['symbol']:source for source,r in rows.items()}
    aliases=literal_aliases(ir,unit) if optimized else {}
    from audit_kernel import _ir_definition_body
    if not optimized:
        leaf=rows['Lemma.Platform.LemmaSim.DescriptorDTB.leafPropertyWire']
        fixed=next((r['symbol'] for r in unit['functions'] if canonical(r['source'])=='Lemma.Platform.LemmaSim.DescriptorDTB.fixedCell'),None)
        if fixed is None:raise Core0Error('USBWire fixed-cell authority absent')
        leaf_body=_ir_definition_body(ir,leaf['symbol'])
        masks=re.findall(r'call \{ i64, i64 \} @'+re.escape(fixed)+r'\(([^)]+)\)',leaf_body)
        if masks.count('i64 %arg0, i64 %arg1, i64 0, i64 256')!=1 or 'i64 %arg0, i64 %arg1, i64 0, i64 128' in masks:
            raise Core0Error('USBWire decoded boundary must use distinct flag256')
    observed={}
    for source,(args,effects,digest) in expected.items():
        row=rows.get(source)
        if row is None or (row.get('args'),row.get('effects'))!=(args,effects):raise Core0Error('USBWire source signature/effects differ: '+source)
        actual=hashlib.sha256(body_normalized(ir,row,names,aliases).encode()).hexdigest()
        if actual!=(post_bodies[source] if optimized else digest):raise Core0Error('USBWire exact discovery/staging/owned-call/power/boot authority differs: '+source)
        observed[source]=actual
    # Scheduler and boot wrappers admit only the actual Wire binding11. Shared
    # Product10 and earlier USB callbacks are independently preserved.
    if not optimized:
        for caller,target,args in [('wireUSBStep','wireStep','i64 11'),(('siliconUSBWireInitializeMedium' if cfg.endswith('-initialize') else 'siliconUSBWireBoot'),'bootWire',('i64 1, i64 11' if cfg.endswith('-initialize') else 'i64 0, i64 11'))]:
            a=rows['Lemma.Platform.LemmaSim.NotebookKernel.'+caller];b=rows['Lemma.Platform.LemmaSim.NotebookKernel.'+target]
            calls=re.findall(r'call \{ i64, i64 \} @'+re.escape(b['symbol'])+r'\(([^)]+)\)',_ir_definition_body(ir,a['symbol']))
            if calls!=[args]:raise Core0Error('USBWire scheduler/boot literal binding differs')
    edges=[]
    for source,row in rows.items():
        body=_ir_definition_body(ir,row['symbol'])
        if body is None:continue
        for target in set(re.findall(r'\bcall\b[^\n]*?@([A-Za-z0-9_.$-]+)\(',body)):
            if names.get(target) in expected:edges.append((source,names[target]))
    callers=hashlib.sha256(json.dumps(sorted(edges),separators=(',',':')).encode()).hexdigest()
    if callers!=caller_inventory[bool(optimized)]:raise Core0Error('USBWire checked authority caller inventory differs')
    return {'contract_version':'lemma-usb-wire-discovery-v1','configuration':cfg,'binding':11,'descriptor_abi':12,'features':15,'stage_offset':3584,'stage_bytes':512,'paper_version':3,'phy_version':1,'sample_hz':48000000,'bit_hz':12000000,'development_mac':1,'pre_or_post':'post' if optimized else 'pre','complete_body_identities':observed,'caller_inventory_sha256':callers,'scope':'Genuine checked artifact authority; complete guest/physical SEND/Pending and cold workflow require separate observations'}
