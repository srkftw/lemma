# SPDX-License-Identifier: Apache-2.0
"""Host fixtures use literal v1/v2 bytes and reject changed extents and identity."""
import copy,json,struct,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from audit_kernel import validate_package_contract,validate_package_payloads
from core0_common import Core0Error

def contract(configuration):
    version=2 if configuration=='lemmasim-silicon-devices' else 1
    return {'schema_version':1,'configuration':configuration,'startup_case':'normal','user_startup_case':'none',
            'contract_version':f'lemma-boot-package-v{version}','magic':0x31474b50414d454c,'version':version,'image_count':1,
            'header_bytes':32,'descriptor_bytes':96,'offset_encoding':'generated-label-differences',
            'image':{'id':1,'entry':0x1000000 if version==2 else 0x10000,'text_va':0x1000000 if version==2 else 0x10000,
              'text_capacity':0x80000 if version==2 else 0xf000,'data_va':0x20000,'data_mem_bytes':4096,
              'stack_va':0x3fffa000 if version==2 else 0x3fffc000,'stack_pages':4 if version==2 else 2,'flags':0}}

def fixture(version):
    # One literal 16-byte RV64 text span and initialized 8-byte data span.
    text=bytes.fromhex('13050000130600001307000067800000');data=b'\x31\0\0\0\0\0\0\0'
    values=(0x31474b50414d454c,version,1,152,1,0x1000000 if version==2 else 0x10000,
            0x1000000 if version==2 else 0x10000,128,16,0x20000,144,8,4096,
            0x3fffa000 if version==2 else 0x3fffc000,4 if version==2 else 2,0)
    return struct.pack('<16Q',*values)+text+data,text,data

class SinglePackagePayload(unittest.TestCase):
    def test_literal_declared_v1_and_v2_single_images(self):
        for configuration,version in (('normal',1),('lemmasim-silicon-devices',2)):
            with self.subTest(configuration=configuration):
                declared=validate_package_contract(contract(configuration),configuration=configuration)
                raw,text,data=fixture(version);rows=validate_package_payloads(raw,declared,[(text,data)])
                self.assertEqual((len(rows),rows[0]['id'],rows[0]['text_offset'],rows[0]['data_offset']),(1,1,128,144))
    def test_v2_cannot_use_v1_identity_or_stack_even_if_payload_matches(self):
        declared=validate_package_contract(contract('lemmasim-silicon-devices'),configuration='lemmasim-silicon-devices')
        raw,text,data=fixture(2)
        for offset,value in ((8,1),(40,0x10000),(48,0x10000),(104,0x3fffc000),(112,2)):
            with self.subTest(offset=offset):
                bad=bytearray(raw);struct.pack_into('<Q',bad,offset,value)
                with self.assertRaises(Core0Error):validate_package_payloads(bytes(bad),declared,[(text,data)])
    def test_single_payload_rejects_alignment_overlap_unknown_bytes_and_trailer(self):
        for configuration,version in (('normal',1),('lemmasim-silicon-devices',2)):
            declared=validate_package_contract(contract(configuration),configuration=configuration);raw,text,data=fixture(version)
            mutations=[]
            for offset,value in ((56,129),(80,128),(64,15),(96,4095)):
                bad=bytearray(raw);struct.pack_into('<Q',bad,offset,value);mutations.append(bytes(bad))
            bad=bytearray(raw);bad[-1]^=1;mutations.append(bytes(bad))
            bad=bytearray(raw)+b'\0';struct.pack_into('<Q',bad,24,len(bad));mutations.append(bytes(bad))
            for bad in mutations:
                with self.subTest(configuration=configuration,mutation=bad.hex()):
                    with self.assertRaises(Core0Error):validate_package_payloads(bad,declared,[(text,data)])
    def test_unaccounted_nonzero_gap_is_rejected(self):
        declared=validate_package_contract(contract('lemmasim-silicon-devices'),configuration='lemmasim-silicon-devices')
        raw,text,data=fixture(2)
        fields=list(struct.unpack_from('<16Q',raw));fields[3]=168;fields[7]=136;fields[10]=160
        padded=struct.pack('<16Q',*fields)+bytes(8)+text+bytes(8)+data
        self.assertEqual(len(validate_package_payloads(padded,declared,[(text,data)])),1)
        changed=bytearray(padded);changed[129]=0x73
        with self.assertRaises(Core0Error):validate_package_payloads(bytes(changed),declared,[(text,data)])

    def test_contract_validation_remains_closed(self):
        for key,value in (('version',1),('image_count',True),('contract_version','arbitrary-package')):
            bad=contract('lemmasim-silicon-devices');bad[key]=value
            with self.subTest(key=key),self.assertRaises(Core0Error):validate_package_contract(bad,configuration='lemmasim-silicon-devices')

if __name__=='__main__':unittest.main(verbosity=2)
