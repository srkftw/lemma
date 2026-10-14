"""Fail-closed artifact authority for USBClocked13 discovery and Paper3.

The selected genuine source/LLVM corpus supplies independently reviewed exact
body pins. No target code, device transaction, journal or policy runs here.
"""
from __future__ import annotations
import hashlib
import json
import re
from core0_common import Core0Error
from paper_next import canonical, normalized

CONFIGURATIONS = frozenset(('lemmasim-silicon-usb-clocked-bulk-notebook',
                           'lemmasim-silicon-usb-clocked-bulk-initialize'))
# Filled only from the genuine final kernel export after source, interface and
# error/caller semantics are independently inspected; absence never succeeds.
EXPECTED = {'Lemma.Drivers.Paper.initializeExecuted': ([],
                                            ['checked-access',
                                             'mmio-read',
                                             'io-order'],
                                            '69ecbbc0a5994932f19cb630ee4f7833f9b179e90bb26ba9a2326bf5e377783d'),
 'Lemma.Drivers.Paper.uploadNext': (['u64', 'u64', 'u64', 'u64', 'u64'],
                                    ['checked-access',
                                     'mmio-read',
                                     'mmio-write',
                                     'io-order',
                                     'physical-read'],
                                    '397b3df89466969175a03673d72f18784a8cb32f1e25d4e82315a87b80f9dfd0'),
 'Lemma.Drivers.Paper.uploadOffsetNext': (['u64',
                                           'u64',
                                           'u64',
                                           'u64',
                                           'u64',
                                           'u64'],
                                          ['checked-access',
                                           'mmio-read',
                                           'mmio-write',
                                           'io-order',
                                           'physical-read'],
                                          '871073f696f1c93737b85460fd40d108f0ec61fff41cc25c431260ce2cbda22d'),
 'Lemma.Drivers.Paper.uploadWordNext': (['u32',
                                         'u32',
                                         'u64',
                                         'u64',
                                         'u64',
                                         'u64',
                                         'u64'],
                                        ['checked-access',
                                         'mmio-write',
                                         'io-order',
                                         'physical-read'],
                                        '88d1e36f8a5aaf6ebdb04df92f9c124f0e35b781bda90b5a92d33dddaa30f2cc'),
 'Lemma.Platform.LemmaSim.Descriptor.expectedBindingClocked': (['u64', 'u64'],
                                                               [],
                                                               'b9e7b39446ddb9831749b85e3e144f4ffe9923358b4c9146c99aa9a37e894b47'),
 'Lemma.Platform.LemmaSim.Descriptor.fieldsStepClocked': (['u32',
                                                           'u32',
                                                           'u64',
                                                           'u64',
                                                           'u64',
                                                           'u64',
                                                           'u64'],
                                                          ['checked-access',
                                                           'mmio-read',
                                                           'io-order'],
                                                          '53b13c3f0b20a50d18952770c7584968b49edee8d324551be3ceb4ccbb18f83f'),
 'Lemma.Platform.LemmaSim.Descriptor.fieldsStepClocked.compare': (['u64',
                                                                   'u32',
                                                                   'u64'],
                                                                  ['checked-access',
                                                                   'mmio-read',
                                                                   'io-order'],
                                                                  '4863adfdcc6f7b7cb4b4553e59276be67737120bc61a8b5003802b21555cc9a3'),
 'Lemma.Platform.LemmaSim.Descriptor.geometryClocked': (['u64'],
                                                        ['checked-access',
                                                         'mmio-read',
                                                         'io-order',
                                                         'physical-read',
                                                         'physical-write'],
                                                        'ed8c7b3d9b8dc03d51b115b7eb90659240d21593bb5d718f6c24cc876542a07d'),
 'Lemma.Platform.LemmaSim.Descriptor.validateBindingClocked': (['u64'],
                                                               ['checked-access',
                                                                'mmio-read',
                                                                'io-order',
                                                                'physical-read',
                                                                'physical-write'],
                                                               'bc342122fb12618d650a239b279463bbc8ac53f91f8fe17c40c1a919b2861af7'),
 'Lemma.Platform.LemmaSim.Descriptor.validateBindingClocked.admitted': (['u64'],
                                                                        ['checked-access',
                                                                         'mmio-read',
                                                                         'io-order',
                                                                         'physical-read',
                                                                         'physical-write'],
                                                                        '0989bd93a1e06d1b4b25675a7ff9a7fd49f9512a8cf4c3700986732d5bc3e5bf'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.actualDevicesExecuted': ([],
                                                                 ['checked-access',
                                                                  'mmio-read',
                                                                  'io-order'],
                                                                 '80f67127d43b3fb76e5c4437d92c4e280a49404139e3040f9fc033f5b5505b9f'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.actualUSBClocked': ([],
                                                            ['checked-access',
                                                             'mmio-read',
                                                             'io-order'],
                                                            '4e1a694ab864889f3183340a1811ce41776d10e21ead24474cfdee09adebb490'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.actualUSBClockedStep': (['u32',
                                                                 'u32',
                                                                 'u64',
                                                                 'u64',
                                                                 'u64',
                                                                 'u64',
                                                                 'u64'],
                                                                ['checked-access',
                                                                 'mmio-read',
                                                                 'io-order'],
                                                                '8f9c2fbda0c89366b78cec72e30b9464dbd0ef2ddc8b081cf45c55a1b6ff48f5'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.clockedUSBIdentity': (['u64'],
                                                              [],
                                                              'f153bb35d86797329c6c5a26ce804c642e1ac894d597975f64a9d3c1a714aac6'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.endNodeClocked': (['u64', 'u64'],
                                                          ['checked-access',
                                                           'physical-read',
                                                           'physical-write'],
                                                          'e96dbaba0c1c7b88b24877adc4dc73ab1271d76b6c7acd189390cf8f29d8c402'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.equalLiteralClocked': (['u64',
                                                                'u64',
                                                                'u64'],
                                                               ['checked-access',
                                                                'physical-read'],
                                                               '0a7e7855b6b47a9b691356a4db09a43765830977416c5000edcd443b86179264'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.equalLiteralExecuted': (['u64',
                                                                 'u64',
                                                                 'u64'],
                                                                ['checked-access',
                                                                 'physical-read'],
                                                                '1d230e487fc11c829f03ad46f46ff2aad5ae81984e62133f7257d654f8dfb022'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.executedProperty': (['u64', 'u64'],
                                                            ['checked-access',
                                                             'physical-read',
                                                             'physical-write'],
                                                            '88657bf15fdd712589ca239e3cf0514afc49371f1b9ff100b27a175f995e3adb'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.executedRegisterStep': (['u32',
                                                                 'u32',
                                                                 'u64',
                                                                 'u64',
                                                                 'u64',
                                                                 'u64',
                                                                 'u64'],
                                                                ['checked-access',
                                                                 'physical-read'],
                                                                '0c6cdfc24e53fc4bae22930ff9ffcb7aec369106b00c74153134dfc11823c0f4'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.findCodeClocked': (['u64',
                                                            'u64',
                                                            'u64',
                                                            'u64'],
                                                           ['checked-access',
                                                            'physical-read'],
                                                           '0c0445188992c9f22e7b8be1e3ccc322a2585e7058b38249857ed628a763dae9'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.findStepClocked': (['u32',
                                                            'u32',
                                                            'u64',
                                                            'u64',
                                                            'u64',
                                                            'u64',
                                                            'u64'],
                                                           ['checked-access',
                                                            'physical-read'],
                                                           'e2f7122849837b7233bd748e463b52ffcc38372b0ac7deab8b0b00f75db5abb0'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.leafPropertyClocked': (['u64',
                                                                'u64',
                                                                'u64',
                                                                'u64'],
                                                               ['checked-access',
                                                                'physical-read',
                                                                'physical-write'],
                                                               '71d9812f61045bd3a5a9a86d7aff486fcf9d055eb499f92f008ac4b7dff18beb'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.leafPropertyExecuted': (['u64',
                                                                 'u64',
                                                                 'u64',
                                                                 'u64'],
                                                                ['checked-access',
                                                                 'physical-read',
                                                                 'physical-write'],
                                                                '0892f4074e915b8030ee99ea6bbd2ce2f450b1f3a57503666f6a4aeb92417ce0'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalLengthClocked': (['u64'],
                                                                [],
                                                                '4375d4eee34632eac10ff48130dd7f24b5fff9f43e61635ddf5aa41c4f1c289e'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalLengthExecuted': (['u64'],
                                                                 [],
                                                                 'c441f3bfa30e93a0ef2d1233a6c23d1a6da68a7a01c45f0ef61f8e85be291480'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalLengthNext': (['u64'],
                                                             [],
                                                             '2cb065efbb0087aadcee02aba000d1d6b75d2cbff429d610ab68af76a4fcafe2'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalWordClocked': (['u64', 'u64'],
                                                              [],
                                                              '46698fd0092cda1c5676d8cce8b2ae5732b307bac1bcd9b439091f837ed1dee4'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalWordExecuted': (['u64', 'u64'],
                                                               [],
                                                               '08876c2db152ac8c6eda246718539f42b54699aad09cac165a193c728617711e'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalWordNext': (['u64', 'u64'],
                                                           [],
                                                           'ada856e4b2c73bc306023c4690ba4617d77f04f15c1f8dd388cbedbfac99807f'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.matchStepClocked': (['u32',
                                                             'u32',
                                                             'u64',
                                                             'u64',
                                                             'u64',
                                                             'u64',
                                                             'u64'],
                                                            ['checked-access',
                                                             'physical-read'],
                                                            'db3f6aeac393b789eed3fefcdfe8546b4166b5cc9010418ab74ba283ecde695f'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.matchStepExecuted': (['u32',
                                                              'u32',
                                                              'u64',
                                                              'u64',
                                                              'u64',
                                                              'u64',
                                                              'u64'],
                                                             ['checked-access',
                                                              'physical-read'],
                                                             '21a08bcb119018e8bd1132a60b43ce74ac539d5538ed8fe37595c940633329b9'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.propertyClocked': (['u64',
                                                            'u64',
                                                            'u64'],
                                                           ['checked-access',
                                                            'physical-read',
                                                            'physical-write'],
                                                           'b8b4dbce4168ed821dd662d4c5d4acabb903fe90f38dc3999f4c06a1ae3e3458'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.tokenStepClocked': (['u32',
                                                             'u32',
                                                             'u64',
                                                             'u64',
                                                             'u64',
                                                             'u64',
                                                             'u64'],
                                                            ['checked-access',
                                                             'physical-read',
                                                             'physical-write'],
                                                            '5a071a97b56523ec39bc92215b3c783f542cfe21b0d2d5b77754014fd571a44e'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.validateBindingClockedCore': (['u64',
                                                                       'u64',
                                                                       'u64',
                                                                       'u64',
                                                                       'u64',
                                                                       'u64'],
                                                                      ['checked-access',
                                                                       'mmio-read',
                                                                       'io-order',
                                                                       'physical-read',
                                                                       'physical-write'],
                                                                      '32acd34f50941a8e648baf7a53e0f03e405b7547e5b57bbcf1aafa17fa9d8a2f'),
 'Lemma.Platform.LemmaSim.DescriptorDTB.validateSiliconUSBClocked': (['u64',
                                                                      'u64',
                                                                      'u64',
                                                                      'u64',
                                                                      'u64'],
                                                                     ['checked-access',
                                                                      'mmio-read',
                                                                      'io-order',
                                                                      'physical-read',
                                                                      'physical-write'],
                                                                     '92c5c20a854065d57ba36e87573aef2299ac2cf6eb6555f2669d9d5231fc67fa'),
 'Lemma.Platform.LemmaSim.DeviceService.bulkUploadStepNext': (['u32',
                                                               'u32',
                                                               'u64',
                                                               'u64',
                                                               'u64',
                                                               'u64',
                                                               'u64'],
                                                              ['checked-access',
                                                               'mmio-read',
                                                               'mmio-write',
                                                               'io-order',
                                                               'physical-read'],
                                                              '1944203fd010cdb478006cc5befed984ed36bfc18c603ab56ab87016b1ccfeb5'),
 'Lemma.Platform.LemmaSim.DeviceService.surfaceV2Next': (['u64',
                                                          'u64',
                                                          'u64',
                                                          'u64',
                                                          'u64',
                                                          'u64'],
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
 'Lemma.Platform.LemmaSim.DeviceService.uploadOrdinaryNext': (['u64',
                                                               'u64',
                                                               'u64'],
                                                              ['checked-access',
                                                               'mmio-read',
                                                               'mmio-write',
                                                               'io-order',
                                                               'physical-read',
                                                               'physical-write'],
                                                              '65dd460340c6ffdac1114f80fb889f3c43048665c85460ac39ed85f6aa49811a'),
 'Lemma.Platform.LemmaSim.NotebookKernel.acceptPendingClocked': (['u64'],
                                                                 ['checked-access',
                                                                  'mmio-read',
                                                                  'mmio-write',
                                                                  'io-order',
                                                                  'physical-read',
                                                                  'physical-write'],
                                                                 '4e0d29c89d75237d7f46785b9860baee86e1fb5d45992d0bcbdf6511a1f16b12'),
 'Lemma.Platform.LemmaSim.NotebookKernel.bootClocked': (['u64', 'u64'],
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
                                                        '6942354782cf0c72cdae1594a1810c096d0b3e0ab72f526094f9d156da36ad9c'),
 'Lemma.Platform.LemmaSim.NotebookKernel.clockedStep': (['u64'],
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
                                                        '4350301309d78fa2ce212d801d003a8f4784da2d6925b015e2428fd17721cc20'),
 'Lemma.Platform.LemmaSim.NotebookKernel.clockedUSBStep': ([],
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
                                                           '9eb43a25af1da0942ecd3eab2f9af3df48cb0ab1b98118c520144aa1366558a7'),
 'Lemma.Platform.LemmaSim.NotebookKernel.constructClocked': (['u64', 'u64'],
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
                                                             '2a96adfbd730cee4b7b59b948cea91bcab9464fc91bcac1ccf5be6f5a7446013'),
 'Lemma.Platform.LemmaSim.NotebookKernel.deviceCallClockedBulk': (['u64',
                                                                   'u64',
                                                                   'u64',
                                                                   'u64',
                                                                   'u64'],
                                                                  ['checked-access',
                                                                   'mmio-read',
                                                                   'mmio-write',
                                                                   'io-order',
                                                                   'machine-state',
                                                                   'physical-read',
                                                                   'physical-write',
                                                                   'firmware-call'],
                                                                  '4aadc06a95da0ff75d3391a311bb715df55186e6582738a95646abd8719743b7'),
 'Lemma.Platform.LemmaSim.NotebookKernel.dispatchClockedBulk': (['u64',
                                                                 'u64',
                                                                 'u64',
                                                                 'u64'],
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
                                                                'a27fe3deb7f24275c546ea5cee6977ca5a42aeb56735ebbf2ad5bb7e1d69a109'),
 'Lemma.Platform.LemmaSim.NotebookKernel.dispatchUSBClockedBulk': (['u64',
                                                                    'u64',
                                                                    'u64'],
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
                                                                   '22281e20b6469c49edbed11075e487b6c3ecb90ac8ec27a7043c875cd0590a87'),
 'Lemma.Platform.LemmaSim.NotebookKernel.siliconUSBClockedBoot': ([],
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
                                                                  'ed4f95a7a83c90459e9df8528df0452b15740d7bb5ca9594914901f28816082b'),
 'Lemma.Platform.Silicon.BindingUSBClocked.frame_pool_bytes': ([],
                                                               [],
                                                               '4fa0acfd3ce320ff2bf0018f7650ae87545467117c0507cfd364346ccf03e8df'),
 'Lemma.Platform.Silicon.BindingUSBClocked.power_base': ([],
                                                         [],
                                                         'f9ec268ee18f606b275f97360decd953bffbfb7cab1d3fc2c49187a6b436e9a8')}
POST_BODIES = {'Lemma.Drivers.Paper.initializeExecuted': '0ffad45205f89c9d9785bf6d00d01e9e7e138a408fa473d9dba1d8620ad43a7c',
 'Lemma.Drivers.Paper.uploadNext': 'ceacda363fbc56ad14619cdd98fd21d54c04866c682943a7ecf2b96d64edfdcb',
 'Lemma.Drivers.Paper.uploadOffsetNext': 'a9686bf4ae6936cdc75f6fa42d9c031ec454ca0b6a5c1183418e8293f717f309',
 'Lemma.Drivers.Paper.uploadWordNext': 'fe104011af00b39b56c4fc30dfafa4c9074121a7dae8b694ec96f775ff2bcb3f',
 'Lemma.Platform.LemmaSim.Descriptor.expectedBindingClocked': '8708317f57c5f085159b706b8513f44d86481fc8c22a7412f70395ff36145b5a',
 'Lemma.Platform.LemmaSim.Descriptor.fieldsStepClocked': '67507fe833f1e306d31126a43d11683834cefeb4de0462a4d9c9e71894849d1a',
 'Lemma.Platform.LemmaSim.Descriptor.fieldsStepClocked.compare': '0e805bae6582e32b715b7a1455c9c17a85e25474594768fc72910109e9ea4303',
 'Lemma.Platform.LemmaSim.Descriptor.geometryClocked': 'ce714d9fba14fca12c9036b3a2cb54439fce987cb3f3a6341f3e2667bbfa7d31',
 'Lemma.Platform.LemmaSim.Descriptor.validateBindingClocked': '845f8c4345f3e07fb9250887c35ad2f85f3650409179c90cd753e36a573342b2',
 'Lemma.Platform.LemmaSim.Descriptor.validateBindingClocked.admitted': '7b5235afbbc4a3bd51daeb470ab86c967cef8fa5baab20421b98159fb966e216',
 'Lemma.Platform.LemmaSim.DescriptorDTB.actualDevicesExecuted': '92522a39058d1c4fdc69ee0bcc477dac32393a6d9ed22cc40a07842f3def2974',
 'Lemma.Platform.LemmaSim.DescriptorDTB.actualUSBClocked': 'a691904b932cdfc6dfd751f28dd98569cedfd55420247d5921da83a687466f1c',
 'Lemma.Platform.LemmaSim.DescriptorDTB.actualUSBClockedStep': '7de616981d160affc575d4ac2c1b9e653dd9a29d6052c217a0ac6ebc756f152f',
 'Lemma.Platform.LemmaSim.DescriptorDTB.clockedUSBIdentity': '4e8fcaf7738f6a28b2c314b537137c561048e2e4e2858a5008a0eb505dd79f67',
 'Lemma.Platform.LemmaSim.DescriptorDTB.endNodeClocked': 'c568821de45df86d410fdaab1b49851520d6519d335d78b2d841f58beb269d26',
 'Lemma.Platform.LemmaSim.DescriptorDTB.equalLiteralClocked': '98a7e17de90460520b7e1df27038efba9106582463922b7f08bbf4a79d906ab3',
 'Lemma.Platform.LemmaSim.DescriptorDTB.equalLiteralExecuted': '7913b75af7a61ce954d3148231dc70e7c4d6b2fb740354be35e6c0752053a248',
 'Lemma.Platform.LemmaSim.DescriptorDTB.executedProperty': '02d954fed44a774bc6e5a5840927b8dfe8c17c95673d446021d3591f3eb30144',
 'Lemma.Platform.LemmaSim.DescriptorDTB.executedRegisterStep': '88fefdfe7900a27a215a09cd08724ef8530f53f4972d4eed3ea63bf5a0630ad3',
 'Lemma.Platform.LemmaSim.DescriptorDTB.findCodeClocked': 'c321db5c73f062fdc9841be320b62b43a0a4fab458cccab9a74678f6681e43e8',
 'Lemma.Platform.LemmaSim.DescriptorDTB.findStepClocked': 'ff60fbb2d68fae9677c1473f507cb93c492d48004588cbc034bd2188e5e77e32',
 'Lemma.Platform.LemmaSim.DescriptorDTB.leafPropertyClocked': 'ea34bc58edf5705ce02e7a9d5efb0f3a62517e3f924fecf96429548639d50691',
 'Lemma.Platform.LemmaSim.DescriptorDTB.leafPropertyExecuted': '1cf3441d346d4fe601a5d6e451989d9fa659cbedf81dd6789e8f1fe7c968678c',
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalLengthClocked': '5af7c8ec2c2c81b6847c05bf7449ecca3b8ac6c3fb15bc6b36b0b38baa14db28',
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalLengthExecuted': 'd371316e921a182f068afb25eed8a21cc32e9a76c419f16fb1d5e6e963368760',
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalLengthNext': '0431978d2b4e2b35100e09db0d1985fc2685a858f28ba45dbd28c226dbedd80a',
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalWordClocked': 'f7e99f7c475bd82511626ad467d382e6901a12e60295af23620e209b85129f55',
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalWordExecuted': '31e5eb77930481963e1d49c49b12f331aea88df458e7eff6872bfbb6f11a148a',
 'Lemma.Platform.LemmaSim.DescriptorDTB.literalWordNext': 'fe832b6a6b3465d0fb93a737954b4b86b9c9f07279160fea23eb2b820b0423ea',
 'Lemma.Platform.LemmaSim.DescriptorDTB.matchStepClocked': 'b07bf71060975feacdd748f91ff731910dd0dda5c02e13fb756a85237786ca05',
 'Lemma.Platform.LemmaSim.DescriptorDTB.matchStepExecuted': '0c525f9cf1078747353f550c569438b9528e03e7c45a666e1dc407166fc8a22d',
 'Lemma.Platform.LemmaSim.DescriptorDTB.propertyClocked': '1ed1dcf3b923891bcdb40ff757ee693f299f22a17dc2f21c7949950213c02920',
 'Lemma.Platform.LemmaSim.DescriptorDTB.tokenStepClocked': 'b2257cc118401dc254b2ad4dbd880ae8e33d364939e41afc182806f4d1191d6c',
 'Lemma.Platform.LemmaSim.DescriptorDTB.validateBindingClockedCore': 'be9b917575e6f88a9925da131e65950c6550462e1ce58e08f869871f2e8b0e93',
 'Lemma.Platform.LemmaSim.DescriptorDTB.validateSiliconUSBClocked': 'c0b47aa2bf496da914a6be4babdb628cf089d502aa10d877323aca6693b5c7a6',
 'Lemma.Platform.LemmaSim.DeviceService.bulkUploadStepNext': '4a356778644d1a813c29cd809b0a1d95f02ffefed99ec10e6ccdba210d4e3e1e',
 'Lemma.Platform.LemmaSim.DeviceService.surfaceV2Next': '9e09f3016afdcd9f5574f57b1335d7f57d7187f74ee66e7964402410364a1a4a',
 'Lemma.Platform.LemmaSim.DeviceService.uploadBulkNext': '0815f6f7d4aa51fb21f00919b93b999d6bd11ac68e1163000d013bc1a8938ecb',
 'Lemma.Platform.LemmaSim.DeviceService.uploadOrdinaryNext': '3f70688d60d50e8505558abb33f528a3e7a966983b100cb592890d07fe577b98',
 'Lemma.Platform.LemmaSim.NotebookKernel.acceptPendingClocked': '14207257b8a96f508cc31da58a2465b1d514698d210818971c816eebba763d96',
 'Lemma.Platform.LemmaSim.NotebookKernel.bootClocked': '370ba8c83cd41173eadefe20dde4a191e7015f627b3d897bc89e5ba8cc6b739d',
 'Lemma.Platform.LemmaSim.NotebookKernel.clockedStep': '767cfec0d7bd7270cdabe6f05079698633677979a373f4f55ac1fe5aff1d2d5d',
 'Lemma.Platform.LemmaSim.NotebookKernel.clockedUSBStep': '851b36b71360c0e7def21393824ec7c896719103d0221ce05dbc18dcab22b742',
 'Lemma.Platform.LemmaSim.NotebookKernel.constructClocked': '913a8fec130117a83f7cf8d56e3e1152bdae7289dd09cef66034920040b39a38',
 'Lemma.Platform.LemmaSim.NotebookKernel.deviceCallClockedBulk': '780e3820ab47b961e32f880baadfd6deff891479135637d6e79255c382114850',
 'Lemma.Platform.LemmaSim.NotebookKernel.dispatchClockedBulk': '8e9610e7dc4259c377838f242c898728cde12f821c47a2c4ee319018e8887caf',
 'Lemma.Platform.LemmaSim.NotebookKernel.dispatchUSBClockedBulk': 'aeeabb6269a535ab52a44337434e35de1129afca0911ff9f9e96349d47ee241f',
 'Lemma.Platform.LemmaSim.NotebookKernel.siliconUSBClockedBoot': '0557b5826fea49af9960f43d67a4679a6f817c6cd8ec97985576e7d980062a33',
 'Lemma.Platform.Silicon.BindingUSBClocked.frame_pool_bytes': '4fa0acfd3ce320ff2bf0018f7650ae87545467117c0507cfd364346ccf03e8df',
 'Lemma.Platform.Silicon.BindingUSBClocked.power_base': 'f9ec268ee18f606b275f97360decd953bffbfb7cab1d3fc2c49187a6b436e9a8'}
CALLER_INVENTORIES = {False: '3e0bbdf34483dc2bdb92f794eb7673a87f8834b88abf40a9cf30c05524cd2679',
 True: 'afa2cf94ac1f7fec5bf229482496520064648944e4fcfaa53f3b1b048740a89e'}

LITERALS = {65: [7525563774295434604, 8028074745930329465, 110],
 66: [7525563774295434604, 7308339910404156793, 8022061],
 68: [7306013292461122924, 7954884646492988790, 426836307316],
 92: [8026307757863691628, 8243113905953600622, 7506774228711793453, 122],
 93: [7233674223446484332, 8028074745930329443, 110],
 94: [7233674223446484332, 7146490669352496483, 34186468169707617],
 95: [7021160616029939052, 8392847327947484003, 29541],
 96: [8319604683596195180, 7305798977753197922, 7234306451255878445, 3307053]}

def literal_aliases(ir, unit):
    from audit_kernel import _ir_definition_body, _line_functions
    rows=[r for r in unit.get('functions',[]) if canonical(r['source'])=='Lemma.Platform.LemmaSim.DescriptorDTB.literalWordClocked']
    if not rows:return {}
    if len(rows)!=1 or unit.get('configuration') not in CONFIGURATIONS | frozenset(('lemmasim-silicon-usb-clocked-retry-bulk-notebook','lemmasim-silicon-usb-clocked-retry-bulk-initialize')) or unit.get('role')!='kernel' or unit.get('contract_version')!='core0-kernel-v0.6' or (rows[0]['args'],rows[0]['effects'])!=(['u64','u64'],[]):
        raise Core0Error('USBClocked literal source/signature/role escaped exact Kernel6 selection')
    row=rows[0];symbol=row['symbol'];owners=_line_functions(ir.splitlines());result={};found=[]
    pattern=r'^@(switch\.table\.'+re.escape(symbol)+r'(?:\.\d+)?) = private unnamed_addr constant \[([34]) x i64\] \[(.*?)\], align 8$'
    body=_ir_definition_body(ir,symbol)
    for name,extent,raw in re.findall(pattern,ir,re.M):
        extent=int(extent)
        values=[int(x) for x in re.findall(r'i64 (-?\d+)',raw)]
        codes=[code for code,wanted in LITERALS.items() if values==wanted and len(wanted)==extent]
        if len(codes)!=1 or len(re.findall(r'@'+re.escape(name)+r'(?![A-Za-z0-9_.$-])',ir))!=2:
            raise Core0Error('USBClocked immutable UTF8 pool content/extent/use differs')
        uses=[owners[i] for i,line in enumerate(ir.splitlines()) if re.search(r'@'+re.escape(name)+r'(?![A-Za-z0-9_.$-])',line) and not line.startswith('@')]
        if uses!=[symbol] or len(re.findall(r'getelementptr inbounds nuw \['+str(extent)+r' x i64\], ptr @'+re.escape(name)+r', i64 0, i64 %arg1',body))!=1:
            raise Core0Error('USBClocked literal is not its one source-owned typed index')
        code=codes[0];found.append(code);result[name]='clocked.literal.'+str(code)
    if sorted(found)!=sorted(LITERALS):raise Core0Error('USBClocked complete UTF8 readonly pool inventory differs')
    return result

def body_normalized(ir,row,names,aliases):
    body=normalized(ir,row,names)
    for raw,stable in sorted(aliases.items(),key=lambda pair:-len(pair[0])):
        body=body.replace('@'+raw,'@'+stable)
        if raw=='switch.table.'+row['symbol']:
            body=body.replace('@switch.table.'+canonical(row['source']),'@'+stable)
    return body

def validate_identity_pool(ir,unit):
    """The six immutable hardware identity words have a separate exact owner."""
    from audit_kernel import _ir_definition_body, _line_functions
    rows=[r for r in unit['functions'] if canonical(r['source'])=='Lemma.Platform.LemmaSim.DescriptorDTB.clockedUSBIdentity']
    if len(rows)!=1 or (rows[0]['args'],rows[0]['effects'])!=(['u64'],[]):
        raise Core0Error('Clocked hardware identity owner/signature differs')
    symbol=rows[0]['symbol'];name='switch.table.'+symbol
    line='@'+name+' = private unnamed_addr constant [6 x i64] [i64 2, i64 48000000, i64 100000000, i64 1, i64 128, i64 67], align 8'
    globals_=[s for s in ir.splitlines() if s.startswith('@'+name)]
    owners=_line_functions(ir.splitlines())
    uses=[owners[i] for i,s in enumerate(ir.splitlines()) if re.search('@'+re.escape(name)+r'(?![A-Za-z0-9_.$-])',s) and not s.startswith('@')]
    body=_ir_definition_body(ir,symbol)
    if globals_!=[line] or uses!=[symbol] or len(re.findall(r'getelementptr inbounds nuw \[6 x i64\], ptr @'+re.escape(name)+r', i64 0, i64 %arg0',body))!=1:
        raise Core0Error('Clocked six hardware identity words/extent/single typed use differs')

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
 'aab72df68cbcb67dc518d559e748f14d5fddf42404b1966b206d3483ace2bf1d')
INITIALIZER_POST = '2067e17ad3ae3bd411af56bafd93c10b159121130479115fbff54915dada454c'
INITIALIZER_CALLERS = {False: '5c1f6d3ee0a8b48d699514abceed2ec99a4065240d9bf19fee583a5fd19d1f48',
 True: '37d80a1a155e7e69bb5f679a6bb8ae43d3216346a7f6bf8f1ca144c3404654c7'}

def _successor(source):
    return 'clocked' in source.lower() and source.startswith((
        'Lemma.Platform.LemmaSim.', 'Lemma.Platform.Silicon.BindingUSBClocked'))


def validate(ir,unit,*,optimized):
    rows={canonical(row['source']):row for row in unit.get('functions',[])}
    reached={source for source in rows if any(x in source.lower() for x in ('clocked','next','executed')) and source.startswith(('Lemma.Platform.LemmaSim.','Lemma.Platform.Silicon.Binding','Lemma.Drivers.Paper.','Lemma.Kernel.Memory.AddressSpace.'))}
    cfg=unit.get('configuration')
    if cfg not in CONFIGURATIONS or unit.get('role')!='kernel':
        if any(_successor(source) for source in rows):raise Core0Error('USBClocked declarations escaped exact Kernel6 deployment')
        return None
    expected=dict(EXPECTED);post_bodies=dict(POST_BODIES);caller_inventory=CALLER_INVENTORIES
    if cfg.endswith('-initialize'):
        old='Lemma.Platform.LemmaSim.NotebookKernel.siliconUSBClockedBoot';new='Lemma.Platform.LemmaSim.NotebookKernel.siliconUSBClockedInitializeMedium'
        del expected[old];del post_bodies[old]
        expected[new]=INITIALIZER_WRAPPER;post_bodies[new]=INITIALIZER_POST;caller_inventory=INITIALIZER_CALLERS
    if unit.get('contract_version')!='core0-kernel-v0.6' or len(rows)!=len(unit.get('functions',[])) or reached!=set(expected):
        raise Core0Error('USBClocked complete source/Kernel6 inventory differs')
    if any(source.startswith(('Lemma.Boot.Product','Lemma.Platform.LemmaSim.BootHealth')) or source.endswith(('.initProduct','.prepareManagedProduct','.configureProduct')) for source in rows):
        raise Core0Error('USBClocked acquired product boot/NV authority')
    names={r['symbol']:source for source,r in rows.items()}
    aliases=literal_aliases(ir,unit) if optimized else {}
    if optimized:validate_identity_pool(ir,unit)
    from audit_kernel import _ir_definition_body
    if not optimized:
        leaf=rows['Lemma.Platform.LemmaSim.DescriptorDTB.leafPropertyClocked']
        fixed=next((r['symbol'] for r in unit['functions'] if canonical(r['source'])=='Lemma.Platform.LemmaSim.DescriptorDTB.fixedCell'),None)
        if fixed is None:raise Core0Error('USBClocked fixed-cell authority absent')
        leaf_body=_ir_definition_body(ir,leaf['symbol'])
        masks=re.findall(r'call \{ i64, i64 \} @'+re.escape(fixed)+r'\(([^)]+)\)',leaf_body)
        if masks.count('i64 %arg0, i64 %arg1, i64 0, i64 256')!=1 or 'i64 %arg0, i64 %arg1, i64 0, i64 128' in masks:
            raise Core0Error('USBClocked decoded boundary must use distinct flag256')
        facts=[(0,256),(2,512),(48000000,1024),(12000000,2048),(1,4096),
               (100000000,8192),(1,16384),(128,32768),(67,65536)]
        wanted=['i64 %arg0, i64 %arg1, i64 '+str(value)+', i64 '+str(flag) for value,flag in facts]
        if sorted(masks)!=sorted(wanted):
            raise Core0Error('Clocked PHY/CDC facts must have nine exact distinct property flags')
    observed={}
    for source,(args,effects,digest) in expected.items():
        row=rows.get(source)
        if row is None or (row.get('args'),row.get('effects'))!=(args,effects):raise Core0Error('USBClocked source signature/effects differ: '+source)
        actual=hashlib.sha256(body_normalized(ir,row,names,aliases).encode()).hexdigest()
        if actual!=(post_bodies[source] if optimized else digest):raise Core0Error('USBClocked exact discovery/staging/owned-call/power/boot authority differs: '+source)
        observed[source]=actual
    # Scheduler and boot wrappers admit only the actual Clocked binding13. Shared
    # Product10 and earlier USB callbacks are independently preserved.
    if not optimized:
        for caller,target,args in [('clockedUSBStep','clockedStep','i64 13'),(('siliconUSBClockedInitializeMedium' if cfg.endswith('-initialize') else 'siliconUSBClockedBoot'),'bootClocked',('i64 1, i64 13' if cfg.endswith('-initialize') else 'i64 0, i64 13'))]:
            a=rows['Lemma.Platform.LemmaSim.NotebookKernel.'+caller];b=rows['Lemma.Platform.LemmaSim.NotebookKernel.'+target]
            calls=re.findall(r'call \{ i64, i64 \} @'+re.escape(b['symbol'])+r'\(([^)]+)\)',_ir_definition_body(ir,a['symbol']))
            if calls!=[args]:raise Core0Error('USBClocked scheduler/boot literal binding differs')
    edges=[]
    for source,row in rows.items():
        body=_ir_definition_body(ir,row['symbol'])
        if body is None:continue
        for target in set(re.findall(r'\bcall\b[^\n]*?@([A-Za-z0-9_.$-]+)\(',body)):
            if names.get(target) in expected:edges.append((source,names[target]))
    callers=hashlib.sha256(json.dumps(sorted(edges),separators=(',',':')).encode()).hexdigest()
    if callers!=caller_inventory[bool(optimized)]:raise Core0Error('USBClocked checked authority caller inventory differs')
    return {'contract_version':'lemma-usb-clocked-discovery-v1','configuration':cfg,'binding':13,'descriptor_abi':14,'features':15,'stage_offset':3584,'stage_bytes':512,'paper_version':3,'phy_version':2,'sample_hz':48000000,'bit_hz':12000000,'development_mac':1,'controller_hz':100000000,'cdc_version':1,'cdc_fifo_capacity':128,'packet_bytes':67,'pre_or_post':'post' if optimized else 'pre','complete_body_identities':observed,'caller_inventory_sha256':callers,'scope':'Genuine checked artifact authority; complete guest/physical SEND/Pending and cold workflow require separate observations'}
