"""Closed artifact provenance for LemmaSim's bounded scalar literal lookups.

This inspects real LLVM and object bytes. It is not target policy or a compiler
correctness proof. Historical profiles continue through their original auditor.
"""
from __future__ import annotations
import re
import struct
import hashlib
from core0_common import Core0Error

CONFIGURATIONS = {'lemmasim-silicon-power-safety-probe','lemmasim-silicon-power-probe', 'lemmasim-silicon-power-notebook', 'lemmasim-silicon-power-initialize', 'lemmasim-silicon-devices','lemmasim-bringup', 'lemmasim-notebook', 'lemmasim-initialize', 'lemmasim-isolation-development', 'lemmasim-silicon-full-notebook', 'lemmasim-silicon-notebook', 'lemmasim-silicon-full-initialize', 'lemmasim-silicon-initialize'}
DTB_LITERALS = {
    1: '', 2: 'cpus', 3: 'soc', 4: 'lemma-paper@10010000', 5: 'lemma-pen@10011000',
    6: 'virtio_mmio@10001000', 7: 'interrupt-controller@c000000', 8: 'clint@2000000',
    9: 'serial@10000000', 10: 'rtc@101000', 18: 'lemma-power@10010500',
    **{code: f'virtio_mmio@1000{code-9}000' for code in range(11,18)},
    32: 'compatible', 33: 'reg', 34: 'interrupts', 35: 'interrupt-parent',
    36: 'phandle', 37: 'timebase-frequency', 38: 'lemma,abi-version',
    39: 'lemma,width', 40: 'lemma,height', 41: 'lemma,max-x', 42: 'lemma,max-y',
    43: 'lemma,pressure-max', 44: 'lemma,descriptor', 45: '#address-cells',
    46: '#size-cells', 47: '#interrupt-cells', 48: 'riscv,ndev',
    49: 'interrupt-controller', 50: 'interrupts-extended', 51: 'clock-frequency',
    52: 'ranges', 64: 'lemma,paper-v1', 65: 'lemma,pen-v1', 66: 'virtio,mmio',
    67: 'sifive,plic-1.0.0\0riscv,plic0', 68: 'sifive,clint0\0riscv,clint0',
    69: 'ns16550a', 70: 'google,goldfish-rtc', 71: 'simple-bus', 72: 'lemma,silicon-dev-v1', 73: 'lemma,diagnostic-uart-v1', 74: 'lemma,power-v1', 75: 'lemma,power-v2',
}
DTB_BYTES = {code: value.encode('ascii') + b'\0' for code,value in DTB_LITERALS.items()}
WORD_CODES = [18,4,5,6,7,*range(11,18),37,38,43,49,50,67,68,70,72,73]
PREFIX = 'Lemma.Platform.LemmaSim.'
# Independent visible rows for the guest-authored bounded font. These are
# packed here rather than imported from the production Lean lookup.
FONT_ROWS = {
    '(':'010100100100010', ')':'010001001001010', '*':'101010111010101',
    '+':'000010111010000', '-':'000000111000000', '/':'001001010100100',
    '=':'000111000111000', 'B':'110101110101110', 'M':'101111111101101',
    'Q':'111101101111001', 'T':'111010010010010', 'X':'101101010101101',
    'A':'010101111101101', 'C':'111100100100111', 'D':'110101101101110', 'E':'111100110100111',
    'F':'111100110100100', 'G':'111100101101111', 'H':'101101111101101',
    'I':'111010010010111', 'K':'101101110101101', 'L':'100100100100111', 'N':'101111111111101',
    'O':'111101101101111', 'P':'111101111100100', 'R':'110101110101101',
    'S':'111100111001111', 'U':'101101101101111', 'V':'101101101101010',
    'W':'101101101111111', 'Y':'101101010010010', '0':'111101101101111',
    '1':'010110010010111', '2':'111001111100111', '3':'111001111001111',
    '4':'101101111001001', '5':'111100111001111', '6':'111100111101111',
    '7':'111001010010010', '8':'111101111101111', '9':'111101111001111',
}

def canonical_specs():
    lengths = [len(DTB_BYTES.get(code,b'')) for code in range(1,76)]
    words = [list(struct.unpack('<' + str((len(DTB_BYTES[code])+7)//8) + 'Q',
                               DTB_BYTES[code].ljust((len(DTB_BYTES[code])+7)//8*8,b'\0')))
             for code in WORD_CODES]
    # Code73's terminating NUL occupies a fourth all-zero word. LLVM uses the
    # independently checked scalar-zero default for that word, not a table row.
    words[WORD_CODES.index(73)] = words[WORD_CODES.index(73)][:3]
    fields = [0]*32
    for key,value in {0:1280132179,1:1,2:256,4:0x80000000,5:0x8000000,
       6:0x82000000,7:0x2000000,8:10000000,9:0x10010000,10:4096,11:12,
       12:0x10011000,13:4096,14:13,15:0x10001000,16:4096,17:1,
       22:0x2000000,23:0xc000000,24:0x10000000,25:0x101000,
       28:0x80000000,29:0x2000000,30:0x87e00000,31:0x200000}.items():
        fields[key]=value
    letters=[int(FONT_ROWS[chr(code)],2) if chr(code) in FONT_ROWS else 0
             for code in range(40,90)]
    return {
      PREFIX+'DescriptorDTB.literalLength': ('kernel',['u64'],[],[lengths]),
      PREFIX+'DescriptorDTB.literalWord': ('kernel',['u64','u64'],[],words),
      PREFIX+'DescriptorDTB.nodeRole': ('kernel',['u64','u64'],[],[[1,2,3,4,5,6,7,*([None]*7),8]]),
      PREFIX+'DescriptorDTB.requiredFlags': ('kernel',['u64'],[],[[255,255,15,1011,515,31,15,31]]),
      PREFIX+'DescriptorDTB.compatibleCode': ('kernel',['u64'],[],[[64,65,66,67,68,69,70,74]]),
      PREFIX+'DescriptorDTB.expectedIRQ': ('kernel',['u64'],[],[[12,13,1,None,None,10,11,14]]),
      PREFIX+'DescriptorDTB.expectedBase': ('kernel',['u64'],[],[[0x10010000,0x10011000,0x10001000,0xc000000,0x2000000,0x10000000,0x101000,0x10010500]]),
      PREFIX+'DescriptorDTB.expectedSpan': ('kernel',['u64'],[],[[0x600000,0x10000,0x100,4096,256]]),
      PREFIX+'Descriptor.expected': ('kernel',['u64'],[],[fields]),
      'Lemma.Ink.Surface.letter': ('user',['u64'],[],[letters]),
      'Lemma.Applications.Notebook.statusCharacter': ('user',['u64']*5,[],
             [list(map(ord,text)) for text in ['SAVED','PENDING','FAILED','READ ONLY']]),
    }

# Closed normalized bodies of the pinned optimizer's four hardware primitives.
# Their pre-optimization range/alignment checks are also inspected below; these
# fingerprints pin the otherwise complex optimized pointer-PHI/mask transform.
DEVICE_BODY_DIGESTS = {
 'read64': ('a02c03847558e4154b49e8fae68d6bbdbe35380b90d9c2a79cfa3d9c819cb474', 'ea81725512b4c63280c993cebbd3f81b0cf771f26f1457151fc47aac47c63ac9'),
 'read32': ('80c06eeb898a093c0894371838b30c02f4853c5b2ba13ccd747ca846eb347eef', 'cc6cf56426abe421df95ac1d4800f3f5cb8c554bf03a35eca4cefe855a079b89'),
 'write32': ('a9c450a0bbdc45f0dafe60fec3e5a9bb0133ad2ed3f138569115f09e8c3814ba', '7ca1f1478a316664648ce52b96ddb6cf681e578c99930006cf0ae5501a66ff75'),
 'write64': ('f80d937bfcae448dba30e2ec6b51eaa9d76db6b2ff8544366f91ed798cd2f6dc', 'cc11d117f7e5d9a281b2091def205363f37ea2de68e8ead8475c67d098da4229'),
}
POWER_CONFIGURATIONS = {'lemmasim-silicon-power-safety-probe','lemmasim-silicon-power-probe',
    'lemmasim-silicon-power-notebook', 'lemmasim-silicon-power-initialize'}
POWER_DEVICE_BODY_DIGESTS = {**DEVICE_BODY_DIGESTS,
 'read32': ('f177cfe6f4ec9fa88914aa3b7c66a3f47ecab6cca81150aed66a1e0c56af5731',
            '58fdc1dbbfa4867f5ca728331bf22dfcd32b393548c9db01e0b3a47387c84a28'),
 'write32': ('447fba5dd72534375f7250a6a6d1365d456e21b52dd7afa2816b41bca8018628',
             'cd11af39d7c16521096e8a8870841ecd5c10a591ab541598b24786066ed64554'),
}
ARITHMETIC_DEVELOPMENT_CONFIGURATIONS = {'lemmasim-silicon-power-arithmetic-oom-development',
    'lemmasim-silicon-power-arithmetic-fault-development', 'lemmasim-silicon-power-arithmetic-stall-development'}
CONFIGURATIONS |= ARITHMETIC_DEVELOPMENT_CONFIGURATIONS
POWER_CONFIGURATIONS |= ARITHMETIC_DEVELOPMENT_CONFIGURATIONS
MANAGED_NOTEBOOK_CONFIGURATIONS = {'lemmasim-silicon-managed-notebook',
    'lemmasim-silicon-managed-initialize'}
CONFIGURATIONS |= MANAGED_NOTEBOOK_CONFIGURATIONS
POWER_CONFIGURATIONS |= MANAGED_NOTEBOOK_CONFIGURATIONS
SUMS_NOTEBOOK_CONFIGURATIONS = {'lemmasim-silicon-sums-notebook',
    'lemmasim-silicon-sums-initialize','lemmasim-silicon-sums-arithmetic-oom-development'}
CONFIGURATIONS |= SUMS_NOTEBOOK_CONFIGURATIONS
POWER_CONFIGURATIONS |= SUMS_NOTEBOOK_CONFIGURATIONS
BLE_CONFIGURATIONS = {'lemmasim-silicon-ble-link-probe'}
CONFIGURATIONS |= BLE_CONFIGURATIONS
BLE_LITERALS = {19:'lemma-ble@10010600',53:'lemma,payload-max',54:'lemma,clocks-per-bit',55:'lemma,manual-context',76:'lemma,ble-packet-v1'}
BLE_BYTES = {**DTB_BYTES, **{code:value.encode('ascii')+b'\0' for code,value in BLE_LITERALS.items()}}
BLE_WORD_CODES = [19,53,54,55,76,*WORD_CODES]
BLE_DEVICE_BODY_DIGESTS = {**DEVICE_BODY_DIGESTS,
 'read32': ('40856209d13c0216986e1da617017e8c9484d9e4d94d847e870a4686f84bf19d',
            '50e97a0a6e45697b135f3628381f3d29758184b5d55700cf30ab448f8fd8fd34'),
 'write32': ('9cf06ddf2472e44e7d8cadeddbaa4aa975278f2032a60e05a5e5b3653b424302',
             'c15a1e6a0be1b43b301839f681944ddec2db5a354554fd7a45143bcd2749696a'),
}

def ble_specs():
    specs=canonical_specs()
    replacements={
      'literalLength':[len(BLE_BYTES.get(code,b'')) for code in range(1,77)],
      'nodeRole':[1,2,3,4,5,6,7,*([None]*7),8,9],
      'requiredFlags':[255,255,15,1011,515,31,15,31,255],
      'compatibleCode':[64,65,66,67,68,69,70,74,76],
      'expectedIRQ':[12,13,1,None,None,10,11,14,15],
      'expectedBase':[0x10010000,0x10011000,0x10001000,0xc000000,0x2000000,0x10000000,0x101000,0x10010500,0x10010600],
      'expectedSpan':[0x600000,0x10000,0x100,4096,256,1024],
    }
    for suffix,values in replacements.items():
        source=PREFIX+'DescriptorDTB.'+suffix
        specs[source]=(*specs[source][:3],[values])
    words = []
    for code in BLE_WORD_CODES:
        raw = BLE_BYTES[code]
        values = list(struct.unpack('<' + str((len(raw)+7)//8) + 'Q',
                                  raw.ljust((len(raw)+7)//8*8,b'\0')))
        words.append(values[:3] if code == 73 else values)
    source=PREFIX+'DescriptorDTB.literalWord'
    specs[source]=(*specs[source][:3],words)
    return specs

USB_CONFIGURATIONS = {'lemmasim-silicon-usb-link-probe',
    'lemmasim-silicon-usb-notebook','lemmasim-silicon-usb-initialize'}
CONFIGURATIONS |= USB_CONFIGURATIONS
USB_LITERALS = {20:'lemma-usb@10010a00',56:'lemma,endpoints',57:'lemma,reset-clocks',
                58:'lemma,decoded-packet-boundary',77:'lemma,usb-device-packet-v1'}
USB_BYTES = {**BLE_BYTES, **{code:value.encode('ascii')+b'\0' for code,value in USB_LITERALS.items()}}
# Code56 fits two immediate words; it creates no readonly table. Code73's NUL
# remains the separately checked scalar-zero default, as in historical schemas.
USB_WORD_CODES = [20,57,58,77,*BLE_WORD_CODES]
USB_DEVICE_BODY_DIGESTS = {**DEVICE_BODY_DIGESTS,
 'read32': ('c6a8fa2fd33e12997029a7ebd25ad5d173d6d1095d48d5982614eebd144214fa',
            '869a1f9d6cfa86fae90139b19857858610274557212725b699c5d159e2caf62e'),
 'write32': ('7e2647bd779cce977c967eee5607137fe88d02a003dddfbeafdecf2ce13ae87f',
             '9c7920cd48733c306ac45a846662eebe905c6b0d14ee2e5a269432ab92f2649f'),
}

def usb_specs():
    specs=ble_specs()
    replacements={
      'literalLength':[len(USB_BYTES.get(code,b'')) for code in range(1,78)],
      'nodeRole':[1,2,3,4,5,6,7,*([None]*7),8,9,13],
      'requiredFlags':[255,255,15,1011,515,31,15,31,255,15,15,15,511],
      'compatibleCode':[64,65,66,67,68,69,70,74,76,66,66,66,77],
      'expectedIRQ':[12,13,1,None,None,10,11,14,15,None,None,None,16],
      'expectedBase':[0x10010000,0x10011000,0x10001000,0xc000000,0x2000000,
                      0x10000000,0x101000,0x10010500,0x10010600,None,None,None,0x10010a00],
      'expectedSpan':[0x600000,0x10000,0x100,4096,256,1024,4096,4096,4096,1024],
    }
    for suffix,values in replacements.items():
        source=PREFIX+'DescriptorDTB.'+suffix
        specs[source]=(*specs[source][:3],[values])
    words=[]
    for code in USB_WORD_CODES:
        raw=USB_BYTES[code]
        values=list(struct.unpack('<'+str((len(raw)+7)//8)+'Q',raw.ljust((len(raw)+7)//8*8,b'\0')))
        words.append(values[:3] if code==73 else values)
    source=PREFIX+'DescriptorDTB.literalWord'
    specs[source]=(*specs[source][:3],words)
    return specs

PRODUCT_CONFIGURATIONS = {'lemmasim-silicon-product-notebook',
    'lemmasim-silicon-product-initialize','lemmasim-silicon-product-boot-probe'}
CONFIGURATIONS |= PRODUCT_CONFIGURATIONS
# All selected Notebook roots share this bounded scalar fetch. Historical
# main selects Protocol2 and still rejects document4 in Mathematics.validate;
# fetching its bounded bytes grants neither sums lowering nor format authority.
# Genuine User1/User2 exports independently retain the same complete owner pin.
LEGACY_NOTEBOOK_CONFIGURATIONS = {
    'lemmasim-notebook','lemmasim-initialize','lemmasim-isolation-development',
    'lemmasim-silicon-notebook','lemmasim-silicon-initialize',
    'lemmasim-silicon-full-notebook','lemmasim-silicon-full-initialize',
    'lemmasim-silicon-power-notebook','lemmasim-silicon-power-initialize',
    'lemmasim-silicon-usb-notebook','lemmasim-silicon-usb-initialize',
    'lemmasim-silicon-product-notebook'} | ARITHMETIC_DEVELOPMENT_CONFIGURATIONS
DOCUMENT4_NOTEBOOK_CONFIGURATIONS = (SUMS_NOTEBOOK_CONFIGURATIONS |
    MANAGED_NOTEBOOK_CONFIGURATIONS | LEGACY_NOTEBOOK_CONFIGURATIONS)
DOCUMENT4_NOTEBOOK_PROFILES = {configuration: ('core0-user-v0.2'
    if configuration in SUMS_NOTEBOOK_CONFIGURATIONS | MANAGED_NOTEBOOK_CONFIGURATIONS
    else 'core0-user-v0.1') for configuration in DOCUMENT4_NOTEBOOK_CONFIGURATIONS}
PRODUCT_LITERALS = {21:'lemma-boot-nv@10012000',59:'lemma,sector-bytes',
    60:'lemma,capacity-sectors',61:'lemma,rom-bytes',62:'lemma,integrity-only',
    78:'lemma,boot-nv-v1'}
PRODUCT_BYTES = {**USB_BYTES, **{code:value.encode('ascii')+b'\0'
                              for code,value in PRODUCT_LITERALS.items()}}
# rom-bytes fits two immediate words. boot-nv-v1 has two nonzero
# words plus a scalar zero terminator, so neither needs a readonly table.
PRODUCT_WORD_CODES = [21,59,60,62,*USB_WORD_CODES]
PRODUCT_DEVICE_BODY_DIGESTS = {
 'read64': ('34649ec362f251ed67b868746f41fd59f235e6e859a0647b9337cb11916ddd7c',
            '7f64c9cb3523c75d0c15e3742293f12b8a915f79a6bda929103a55afa5e3a275'),
 'write64': ('b701403a24cbc0237cccf2063f11a5abf4330c715533b2416b8604fef1a17757',
             '2e1e9517d8eda66631f71961f6b96086191e76c6bbcda0f4463c96046f680c1b'),
 'read32': ('3a4c474975826132424526e5285ea2807d257965578701caaaeaace976a35a62',
            '2335ce1a3fa88748c2643bee9c3aa10718a001df67f6ed08ee596bfc0d8eee9e'),
 'write32': ('03a635392c07b32c523dd2944cb177b3c48f7bbad3f82be7b14bc16a17724fed',
             '4edb487c83b518ee2124f5cdbd289fb1a5854225a7a5a500c9009189876bd542'),
}
PRODUCT_LITERAL_BODIES = {
 PREFIX+'DescriptorDTB.validateBinding': 'fb5b711c46d80edbffebd38c7d9e644f814a38416208ae3f7bc734b3a5b7ac32',
 PREFIX+'Descriptor.geometry': '2df6496627c257026e01897b6b9cfacaa541249b1ca4c6e8e9c54e6b5c4695f3',
}

def product_specs():
    specs=usb_specs()
    replacements={
      'literalLength':[len(PRODUCT_BYTES.get(code,b'')) for code in range(1,79)],
      'nodeRole':[1,2,3,4,5,6,7,*([None]*7),8,9,13,14],
      'requiredFlags':[255,255,15,1011,515,31,15,31,255,15,15,15,511,511],
      'compatibleCode':[64,65,66,67,68,69,70,74,76,66,66,66,77,78],
      'expectedIRQ':[12,13,1,None,None,10,11,14,15,None,None,None,16,17],
      'expectedBase':[0x10010000,0x10011000,0x10001000,0xc000000,0x2000000,
                      0x10000000,0x101000,0x10010500,0x10010600,None,None,None,
                      0x10010a00,0x10012000],
      'expectedSpan':[0x600000,0x10000,0x100,4096,256,1024,4096,4096,4096,1024,1024],
    }
    for suffix,values in replacements.items():
        source=PREFIX+'DescriptorDTB.'+suffix
        specs[source]=(*specs[source][:3],[values])
    words=[]
    for code in PRODUCT_WORD_CODES:
        raw=PRODUCT_BYTES[code]
        values=list(struct.unpack('<'+str((len(raw)+7)//8)+'Q',raw.ljust((len(raw)+7)//8*8,b'\0')))
        words.append(values[:3] if code==73 else values)
    source=PREFIX+'DescriptorDTB.literalWord'
    specs[source]=(*specs[source][:3],words)
    # These three-entry masks arise in genuine optimized checked bodies.
    # Full normalized bodies, source signatures and unsigned index guards are
    # required below; they cannot create a generic memory-table permission.
    specs[PREFIX+'DescriptorDTB.validateBinding']=('kernel',['u64']*6,
        ['checked-access','mmio-read','io-order','physical-read','physical-write'],[[8062,16254,32638]])
    specs[PREFIX+'Descriptor.geometry']=('kernel',['u64'],
        ['checked-access','mmio-read','io-order','physical-read','physical-write'],[[7,15,31]])
    return specs

def lookup_schema(ir: str, unit: dict):
    """Select one complete closed source schema, including historical artifacts.

    New literal declarations are shared source across the legacy bindings;
    the binding-specific guest pass still rejects an unexpected BLE node.
    A source schema cannot mix old and new table extents or word ordering.
    """
    functions={row['symbol']:re.sub(r'^_private\..*?\.[0-9]+\.','',row['source'])
               for row in unit['functions']}
    legacy=canonical_specs();new=ble_specs();usb=usb_specs();product=product_specs();observed={}
    for symbol,count in re.findall(r'^@switch\.table\.([A-Za-z0-9_.$-]+?) = private unnamed_addr constant \[(\d+) x i64\]',ir,re.M):
        source=functions.get(symbol)
        if source in legacy and source.startswith(PREFIX+'DescriptorDTB.'):
            observed[source]=int(count)
    usb_modern=any(count == len(usb[source][3][0]) and count != len(new[source][3][0])
                   for source,count in observed.items())
    product_modern=any(count == len(product[source][3][0]) and count != len(usb[source][3][0])
                      for source,count in observed.items())
    modern=any(count == len(new[source][3][0]) and count != len(legacy[source][3][0])
               for source,count in observed.items())
    word=PREFIX+'DescriptorDTB.literalWord'
    word_symbol=next((symbol for symbol,source in functions.items() if source==word),None)
    if word_symbol is not None:
        number=len(re.findall(r'^@switch\.table\.'+re.escape(word_symbol)+r'(?:\.\d+)? = ',ir,re.M))
        usb_modern=usb_modern or number==len(USB_WORD_CODES)
        modern=modern or number==len(BLE_WORD_CODES)
        product_modern=product_modern or number==len(PRODUCT_WORD_CODES)
    if unit.get('configuration') in PRODUCT_CONFIGURATIONS and observed and not product_modern:
        raise Core0Error('Product discovery lacks its versioned complete literal schema')
    if product_modern:return product,PRODUCT_WORD_CODES,'boot-nv-v1'
    if unit.get('configuration') in USB_CONFIGURATIONS and observed and not usb_modern:
        raise Core0Error('USB discovery lacks its versioned complete literal schema')
    if usb_modern:return usb,USB_WORD_CODES,'usb-device-packet-v1'
    if unit.get('configuration') in BLE_CONFIGURATIONS and observed and not modern:
        raise Core0Error('BLE discovery lacks its versioned complete literal schema')
    return (new,BLE_WORD_CODES,'ble-packet-v1') if modern else (legacy,WORD_CODES,'power-v2')

def validate_devices(ir: str, unit: dict, optimized: bool) -> tuple[set[int],list[dict]]:
    from audit_kernel import _ir_definition_body, _line_functions
    if unit.get('configuration') not in CONFIGURATIONS: return set(),[]
    if unit['role']!='kernel':
        if any(row['stable_id'].startswith('lemmasim.device-') for row in unit['used_execution_ops']):
            raise Core0Error('Lemmasim hardware operation reached user authority')
        return set(),[]
    power = unit['configuration'] in POWER_CONFIGURATIONS
    ble = unit['configuration'] in BLE_CONFIGURATIONS
    usb = unit['configuration'] in USB_CONFIGURATIONS
    product = unit['configuration'] in PRODUCT_CONFIGURATIONS
    expected_contract = 'core0-kernel-v0.7' if product else 'core0-kernel-v0.6' if usb else 'core0-kernel-v0.5' if ble else 'core0-kernel-v0.4' if power else 'core0-kernel-v0.3'
    if unit.get('contract_version') != expected_contract:
        raise Core0Error('Lemmasim device aperture configuration/profile differs')
    digests = PRODUCT_DEVICE_BODY_DIGESTS if product else USB_DEVICE_BODY_DIGESTS if usb else BLE_DEVICE_BODY_DIGESTS if ble else POWER_DEVICE_BODY_DIGESTS if power else DEVICE_BODY_DIGESTS
    sites=set();observed=[];owners=_line_functions(ir.splitlines())
    for row in unit['functions']:
        if not row['source'].startswith(PREFIX+'IO.'): continue
        operation=row['source'].rsplit('.',1)[1]
        if operation not in digests: raise Core0Error('Unknown Lemmasim hardware source')
        write=operation.startswith('write');bits=int(operation[-2:]);width=bits//8
        if row['args']!=(['u64','u64'] if write else ['u64']) or row['effects']!=['checked-access','mmio-write' if write else 'mmio-read','io-order']:
            raise Core0Error('Lemmasim hardware source signature/effects differs')
        body='\n'.join(line.split(';',1)[0].strip() for line in _ir_definition_body(ir,row['symbol']).splitlines() if line.split(';',1)[0].strip())
        if not optimized:
            regions=[(0x10001000,0x10001200),(0xc000004,0xc000048 if product else 0xc000044 if usb else 0xc000040 if ble else 0xc00003c if power else 0xc000038),(0xc002080,0xc002084),(0xc201000,0xc201008)] if width==4 else [(0x10010000,0x10011000),(0x10011000,0x10012000),*([(0x10012000,0x10012400)] if product else [])]
            lower=[int(value) for value in re.findall(r'icmp uge i64 %arg0, (\d+)',body)]
            upper=[int(value) for value in re.findall(r'icmp ule i64 %arg0, (\d+)',body)]
            if lower!=[start for start,end in regions] or upper!=[end-width for start,end in regions] or len(re.findall(r'and i64 %arg0, '+str(width-1)+r'$',body,re.M))!=1:
                raise Core0Error('Lemmasim device primitive range/alignment authority differs')
        digest=hashlib.sha256(body.encode()).hexdigest()
        if digest!=digests[operation][int(optimized)]:
            raise Core0Error('Lemmasim device primitive closed guard/pointer/fence/result CFG differs: '+operation)
        located={i for i,line in enumerate(ir.splitlines()) if owners[i]==row['symbol'] and re.search(r'\b(?:load|store) volatile i'+str(bits)+r'\b',line)}
        if len(located)!=(1 if optimized else 4 if width==4 else 3 if product else 2):
            raise Core0Error('Lemmasim device primitive volatile access inventory differs')
        sites|=located;observed.append(dict(source=row['source'],function=row['symbol'],width_bytes=width,
             direction='write' if write else 'read',access_sites=len(located),body_sha256=digest,
             optimized=optimized,scope='closed pinned lowering/provenance; not a compiler correctness proof'))
    return sites,observed

def validate_sums_record_length(ir: str, unit: dict) -> tuple[set[int],list[dict],set[str]]:
    """Admit the actual version2..4 course-recovery length, never an address.

    The complete normalized owner remains pinned in addition to independent
    content, unsigned bound, single-use and checked readObject binding checks.
    This is a versioned software lookup only; the machine profile is unchanged.
    """
    if unit.get('configuration') not in DOCUMENT4_NOTEBOOK_CONFIGURATIONS:
        return set(),[],set()
    from audit_kernel import _ir_definition_body, _line_functions
    source='Lemma.Applications.Notebook.openCourse'
    names={row['symbol']:re.sub(r'^_private\..*?\.[0-9]+\.','',row['source'])
           for row in unit['functions']}
    rows=[row for row in unit['functions'] if names[row['symbol']]==source]
    if not rows:return set(),[],set()
    effects=['checked-access','io-order','virtual-read','virtual-write','user-syscall','privilege-transition']
    if (len(rows)!=1 or unit.get('role')!='user' or unit.get('image_key')!='notebook'
            or unit.get('contract_version')!=DOCUMENT4_NOTEBOOK_PROFILES[unit['configuration']]
            or rows[0]['args']!=[] or rows[0]['effects']!=effects):
        raise Core0Error('Sums record-length source/signature/effects differs')
    symbol=rows[0]['symbol'];table='switch.table.'+symbol
    definition=f'@{table} = private unnamed_addr constant [3 x i64] [i64 1856, i64 2496, i64 2496], align 8'
    if ir.splitlines().count(definition)!=1 or len(re.findall('@'+re.escape(table)+r'(?![A-Za-z0-9_.$-])',ir))!=2:
        raise Core0Error('Sums record-length table content/extent/use differs')
    body='\n'.join(line.split(';',1)[0].rstrip() for line in _ir_definition_body(ir,symbol).splitlines())
    normalized_table=body.replace('@'+table,'@record-length')
    rebound=re.sub(r'@([^ (]+)',lambda m:'@'+names.get(m[1],m[1]),normalized_table)
    normalized=' '.join(' '.join(line.strip() for line in rebound.splitlines()).split())
    if hashlib.sha256(normalized.encode()).hexdigest()!='8cba4770e09dbb24ae2819a55d646e2f69029fe725bcb1aaebd27e6dfb2e8503':
        raise Core0Error('Sums record-length complete checked owner differs')
    read=next((row['symbol'] for row in unit['functions']
               if names[row['symbol']]=='Lemma.Applications.Notebook.readObject'),None)
    field=next((row['symbol'] for row in unit['functions']
                if names[row['symbol']]=='Lemma.Documents.Mathematics.field'),None)
    if read is None or field is None:
        raise Core0Error('Sums record-length checked callees missing')
    guard=['%action.call.value39 = extractvalue { i64, i64 } %action.call.result36, 1',
           '%switch.tableidx = add i64 %action.call.value39, -2',
           '%0 = icmp ult i64 %switch.tableidx, 3',
           'br i1 %0, label %switch.lookup, label %action.if.merge.20']
    lookup=[f'%switch.gep = getelementptr inbounds nuw [3 x i64], ptr @{table}, i64 0, i64 %switch.tableidx',
            '%switch.load = load i64, ptr %switch.gep, align 8',
            f'%action.call.result54 = call {{ i64, i64 }} @{read}(i64 %call22, i64 3313664, i64 %switch.load)',
            '%action.call.status-word55 = extractvalue { i64, i64 } %action.call.result54, 0',
            '%action.call.status56 = trunc nuw i64 %action.call.status-word55 to i8',
            'br label %action.if.merge.20']
    from audit_kernel import _structured_ir_blocks
    blocks=_structured_ir_blocks(body)
    if blocks.get('action.if.else.16')!=guard or blocks.get('switch.lookup')!=lookup:
        raise Core0Error('Sums record-length exact version bound/read binding differs')
    if f'%action.call.result36 = call {{ i64, i64 }} @{field}(i64 3313664, i64 8)' not in body:
        raise Core0Error('Sums record-length version does not come from the actual document header')
    if len(re.findall(r'%switch\.load(?![A-Za-z0-9_.$-])',body))!=2 or len(re.findall(r'%switch\.gep(?![A-Za-z0-9_.$-])',body))!=2:
        raise Core0Error('Sums record-length result/pointer escapes its sole checked read')
    owners=_line_functions(ir.splitlines())
    sites={i for i,line in enumerate(ir.splitlines()) if owners[i]==symbol and line.strip()=='%switch.load = load i64, ptr %switch.gep, align 8'}
    if len(sites)!=1:raise Core0Error('Sums record-length load inventory differs')
    return sites,[dict(source=rows[0]['source'],function=symbol,values=[1856,2496,2496],
        **{'global':table},element_bits=64,alignment_bytes=8,index_bound=3,guarded_loads=1,readonly=True,
        guard='action.if.else.16',literal_schema='document-v4-length-v1')],{definition}


def validate_lookup(ir: str, unit: dict) -> tuple[set[int],list[dict],set[str]]:
    from audit_kernel import (_ir_definition_body, _line_functions, _structured_ir_blocks,
                              _structured_successors, _structured_reachable)
    if unit.get('configuration') not in CONFIGURATIONS:
        raise Core0Error('Lemmasim readonly admission requires its exact selected configuration')
    specs,word_codes,schema=lookup_schema(ir,unit);by_symbol={row['symbol']:row for row in unit['functions']}
    globals_=[line.strip() for line in ir.splitlines() if re.match(r'^\s*@',line)]
    sites,known,removed=validate_sums_record_length(ir,unit)
    owners=_line_functions(ir.splitlines())
    for global_line in globals_:
        if global_line in removed:continue
        match=re.fullmatch(r'@(switch\.table\.([A-Za-z0-9_.$-]+?)(?:\.(\d+))?) = private unnamed_addr constant \[(\d+) x i64\] \[(.*?)\], align 8',global_line)
        if match is None: continue  # original kernel whitelist will reject it
        table,symbol,suffix,count,raw=match.groups();count=int(count)
        row=by_symbol.get(symbol)
        if row is None: continue
        source=re.sub(r'^_private\..*?\.[0-9]+\.','',row['source'])
        spec=specs.get(source)
        if spec is None: continue
        role,args,effects,tables=spec
        if (unit['role'],row['args'],row['effects'])!=(role,args,effects):
            raise Core0Error('Lemmasim literal source/signature/effects differs: '+source)
        index=int(suffix) if suffix is not None else 0
        if index>=len(tables): raise Core0Error('Lemmasim literal table suffix exceeds exact inventory')
        values=[None if value=='poison' else int(value) for value in re.findall(r'i64 (poison|-?\d+)',raw)]
        expected=tables[index]
        if values!=expected or len(values)!=count or len(re.findall(r'@'+re.escape(table)+r'(?![A-Za-z0-9_.$-])',ir))!=2:
            raise Core0Error('Lemmasim literal content/global use inventory differs: '+source)
        body='\n'.join(line.split(';',1)[0].rstrip() for line in _ir_definition_body(ir,symbol).splitlines())
        if source in PRODUCT_LITERAL_BODIES:
            names={r['symbol']:re.sub(r'^_private\..*?\.[0-9]+\.','',r['source']) for r in unit['functions']}
            # Rebind exactly this owner's already content/extent/use-checked
            # table, as well as function symbols. Module prefixes have no
            # semantics; all remaining instructions and names stay pinned.
            normalized_table=re.sub(r'@switch\.table\.'+re.escape(symbol)+r'(?![A-Za-z0-9_.$-])',
                                    '@switch.table.'+source,body)
            rebound=re.sub(r'@([^ (]+)',lambda m:'@'+names.get(m[1],m[1]),normalized_table)
            normalized=' '.join(' '.join(line.strip() for line in rebound.splitlines()).split())
            if hashlib.sha256(normalized.encode()).hexdigest()!=PRODUCT_LITERAL_BODIES[source]:
                raise Core0Error('Product discovery mask escapes its complete checked body')
        blocks=_structured_ir_blocks(body);successors=_structured_successors(blocks)
        # The inherited local CFG helper intentionally recognizes branches.
        # These pinned lookup owners also have scalar i64 switch selection;
        # model every edge explicitly so a bound cannot be "proved" by omitting
        # a route through a switch. Unknown switch forms fail closed.
        for block,lines in blocks.items():
            starts=[i for i,line in enumerate(lines) if line.startswith('switch ')]
            if not starts: continue
            if len(starts)!=1 or lines[-1]!=']':
                raise Core0Error('Literal owner has an unrecognized switch terminator')
            start=starts[0]
            head=re.fullmatch(r'switch i64 %[A-Za-z0-9_.$-]+, label %([A-Za-z0-9_.$-]+) \[',lines[start])
            rows=[re.fullmatch(r'i64 (-?\d+), label %([A-Za-z0-9_.$-]+)',line)
                  for line in lines[start+1:-1]]
            if head is None or not rows or any(row is None for row in rows) or len({row[1] for row in rows})!=len(rows):
                raise Core0Error('Literal owner switch cases are malformed or repeated')
            targets=(head[1],*(row[2] for row in rows))
            if any(target not in blocks for target in targets):
                raise Core0Error('Literal owner switch targets an unknown block')
            successors[block]=targets
        geps=re.findall(r'(%[A-Za-z0-9_.$-]+) = getelementptr inbounds nuw \['+str(count)+r' x i64\], ptr @'+re.escape(table)+r', i64 0, i64 (%[A-Za-z0-9_.$-]+)',body)
        if len(geps)!=1: raise Core0Error('Lemmasim literal lacks one exact typed pointer derivation')
        pointer,operand=geps[0]
        argument,shift={
            PREFIX+'DescriptorDTB.literalLength':('%arg0',-1), PREFIX+'DescriptorDTB.literalWord':('%arg1',0),
            PREFIX+'DescriptorDTB.nodeRole':('%arg1',-4), PREFIX+'DescriptorDTB.compatibleCode':('%arg0',-1),
            PREFIX+'DescriptorDTB.requiredFlags':('%arg0',-1), PREFIX+'DescriptorDTB.expectedIRQ':('%arg0',-1),
            PREFIX+'DescriptorDTB.expectedBase':('%arg0',-1), PREFIX+'DescriptorDTB.expectedSpan':('%arg0',-4),
            PREFIX+'Descriptor.expected':('%arg0',0), 'Lemma.Ink.Surface.letter':('%arg0',-40),
            'Lemma.Applications.Notebook.statusCharacter':('%arg1',0),
            PREFIX+'DescriptorDTB.validateBinding':('%arg0',-4),
            PREFIX+'Descriptor.geometry':('%arg0',-5),
        }[source]
        if shift:
            if len(re.findall(re.escape(operand)+r' = add i64 '+re.escape(argument)+', '+str(shift)+r'$',body,re.M))!=1:
                raise Core0Error('Lemmasim literal index differs from its exact source coordinate')
        elif operand!=argument: raise Core0Error('Lemmasim literal index is not its exact source argument')
        loads=re.findall(r'(%[A-Za-z0-9_.$-]+) = load i64, ptr '+re.escape(pointer)+r', align 8',body)
        if len(loads)!=1 or len(re.findall(re.escape(pointer)+r'(?![A-Za-z0-9_.$-])',body))!=2:
            raise Core0Error('Lemmasim readonly pointer escapes its single load')
        load=loads[0];load_block=next(block for block,lines in blocks.items() if any(line.startswith(load+' = load') for line in lines))
        guarded_operand=operand;guarded_type='i64'
        conversion=re.search(re.escape(operand)+r' = zext(?: nneg)? i32 (%[A-Za-z0-9_.$-]+) to i64',body)
        if conversion: guarded_operand=conversion[1];guarded_type='i32'
        guards=[]
        for block,lines in blocks.items():
            for line in lines:
                bound=re.fullmatch(r'(%[A-Za-z0-9_.$-]+) = icmp ult '+guarded_type+' '+re.escape(guarded_operand)+', '+str(count),line)
                if bound and re.fullmatch(r'br i1 '+re.escape(bound[1])+r', label %[A-Za-z0-9_.$-]+, label %[A-Za-z0-9_.$-]+',lines[-1]):
                    true,false=successors[block];without={name:targets for name,targets in successors.items()};without[block]=(false,)
                    if not _structured_reachable(without,'entry',load_block) and _structured_reachable(successors,true,load_block): guards.append(block)
        if len(guards)!=1: raise Core0Error('Lemmasim table load lacks a dominating exact unsigned bound: '+source+' '+table)
        if source.endswith('expectedIRQ') or source.endswith('nodeRole') or (schema in {'usb-device-packet-v1','boot-nv-v1'} and source.endswith('expectedBase')):
            hole=blocks.get('switch.hole_check')
            if source.endswith('nodeRole'):
                bits,mask,fallback=(32,245887,'if.else.49') if schema=='boot-nv-v1' else (32,114815,'if.else.46') if schema=='usb-device-packet-v1' else (16,-16257,'if.else.43') if schema=='ble-packet-v1' else (16,16511,'if.else.40')
            else:
                bits,mask,fallback=((16,12799,'if.else.31') if source.endswith('expectedBase') else (16,12775,'if.else.25')) if schema=='boot-nv-v1' else (16,4607,'if.else.28') if source.endswith('expectedBase') else (16,4583,'if.else.22') if schema=='usb-device-packet-v1' else (16,487,'if.else.19') if schema=='ble-packet-v1' else (8,-25,'if.else.16')
            visible=sum(1 << ordinal for ordinal,value in enumerate(expected) if value is not None)
            if (mask & ((1 << bits)-1)) != visible:
                raise Core0Error('Literal schema mask does not independently exclude every poison row')
            if hole!=[f'%switch.maskindex = trunc nuw i64 %switch.tableidx to i{bits}',f'%switch.shifted = lshr i{bits} {mask}, %switch.maskindex',f'%switch.lobit = trunc i{bits} %switch.shifted to i1',f'br i1 %switch.lobit, label %switch.lookup, label %{fallback}']:
                raise Core0Error('Lemmasim poisoned literal holes lack their exact exclusion mask')
        if source.endswith('nodeRole'):
            parent=re.search(r'switch i64 %arg0, label %(\S+) \[\s*i64 0, label %(\S+)\s*i64 10, label %(\S+)\s*i64 12, label %(\S+)\s*\]',body)
            if parent is None or not _structured_reachable(successors,parent[4],load_block) or any(_structured_reachable(successors,parent[i],load_block) for i in (1,2,3)):
                raise Core0Error('Power node-role lookup escaped its exact soc parent12 gate')
        if source.endswith('literalWord'):
            guard=guards[0];code=word_codes[index]
            if len(re.findall(r'i64 '+str(code)+r', label %'+re.escape(guard)+r'(?![A-Za-z0-9_.$-])',body))!=1:
                raise Core0Error('FDT word table is not bound to its exact literal code')
        if source.endswith('statusCharacter'):
            # Each word belongs to one declared save state; the default state
            # is read-only. A valid index bound alone cannot certify that bind.
            branch = re.search(r'switch i64 %arg0, label %([A-Za-z0-9_.$-]+) \[\s*'
                r'i64 0, label %([A-Za-z0-9_.$-]+)\s*'
                r'i64 1, label %([A-Za-z0-9_.$-]+)\s*'
                r'i64 2, label %([A-Za-z0-9_.$-]+)\s*\]', body)
            if branch is None:
                raise Core0Error('Notebook status words lack the exact save-state selection')
            selected=branch[index+2] if index<3 else branch[1]
            if not _structured_reachable(successors,selected,load_block):
                raise Core0Error('Notebook status word is not reached by its declared save state')
            for other in [branch[1],branch[2],branch[3],branch[4]]:
                if other!=selected and _structured_reachable(successors,other,load_block):
                    raise Core0Error('Notebook status word is reachable from a different save state')
        located={i for i,line in enumerate(ir.splitlines()) if owners[i]==symbol and line.strip().startswith(load+' = load')}
        if len(located)!=1: raise Core0Error('Lemmasim literal load inventory differs')
        sites|=located;removed.add(global_line)
        known.append(dict(source=row['source'],function=symbol,global_=table,values=values,
            element_bits=64,alignment_bytes=8,index_bound=count,guarded_loads=1,readonly=True,guard=guards[0],literal_schema=schema))
        known[-1]['global']=known[-1].pop('global_')
    for source,spec in specs.items():
        if any(re.sub(r'^_private\..*?\.[0-9]+\.','',row['source'])==source for row in unit['functions']):
            present=[row for row in known if re.sub(r'^_private\..*?\.[0-9]+\.','',row['source'])==source]
            if len(present)!=len(spec[3]): raise Core0Error('Lemmasim exact reachable table inventory incomplete: '+source)
    return sites,known,removed

def validate_object(section_text: str, symbol_text: str, relocation_text: str,
                    section_bytes: dict[str,bytes], tables: list[dict], object_file: str) -> dict:
    """Every optimized literal owns exact local object bytes, without relocation."""
    sections={match[1]:match[2] for match in re.finditer(r'(?m)^\s*\[\s*(\d+)\]\s+(\S+)\s+',section_text)}
    for name,raw in section_bytes.items():
        flags,entry_size=('AM','20') if name=='.rodata.cst32' else ('A','00')
        section=re.findall(r'(?m)^\s*\[\s*\d+\]\s+'+re.escape(name)+r'\s+PROGBITS\s+0+\s+[0-9a-f]+\s+([0-9a-f]+)\s+'+entry_size+r'\s+'+flags+r'\s+0\s+0\s+8\s*$',section_text)
        if len(section)!=1 or int(section[0],16)!=len(raw) or name=='.rodata.cst32' and len(raw)%32:
            raise Core0Error('Lemmasim literal section readonly flags/alignment/extent differs')
    rows=[line.split() for line in symbol_text.splitlines() if len(line.split())==8 and line.split()[3]=='OBJECT' and line.split()[6]!='UND']
    expected={'.L'+row['global'] for row in tables}
    if {row[-1] for row in rows}!=expected or len(rows)!=len(tables):
        raise Core0Error('Lemmasim readonly object-symbol inventory differs')
    observed=[];extents=[]
    for table in tables:
        row=next(row for row in rows if row[-1]=='.L'+table['global']);offset,size=int(row[1],16),int(row[2]);section=sections.get(row[6]);raw=section_bytes.get(section,b'')
        values=[0 if value is None else value & ((1<<64)-1) for value in table['values']]
        if row[4:6]!=['LOCAL','DEFAULT'] or section not in {'.rodata','.rodata.cst32'} or size!=len(values)*8 or offset%8 or offset+size>len(raw) or raw[offset:offset+size]!=struct.pack('<'+str(len(values))+'Q',*values):
            raise Core0Error('Lemmasim literal object extent/bytes/section differs')
        if any(previous==section and offset<end and begin<offset+size for previous,begin,end in extents):
            raise Core0Error('Lemmasim literal object extents overlap')
        extents.append((section,offset,offset+size));current=None
        for line in relocation_text.splitlines():
            heading=re.search(r"Relocation section '([^']+)'",line)
            if heading: current=heading[1]
            relocation=re.match(r'\s*([0-9a-f]+)\s+[0-9a-f]+\s+(R_RISCV_[A-Z0-9_]+)\s',line)
            if relocation and current=='.rela'+section and int(relocation[1],16)<offset+size and offset<int(relocation[1],16)+(8 if relocation[2].endswith('64') else 4):
                raise Core0Error('Lemmasim literal bytes contain a relocation')
        observed.append(dict(source=table['source'],symbol=row[-1],section=section,offset=offset,bytes=size,
            values=values,sha256=hashlib.sha256(raw[offset:offset+size]).hexdigest(),relocations=[]))
    for section,raw in section_bytes.items():
        if section=='.rodata': continue  # shared with independently checked local jump tables
        occupied=bytearray(len(raw))
        for name,begin,end in extents:
            if name==section: occupied[begin:end]=b'\1'*(end-begin)
        if any(byte for byte,owned in zip(raw,occupied) if not owned):
            raise Core0Error('Unaccounted nonzero Lemmasim merged literal bytes')
    return dict(object=object_file,readonly_tables=observed)


def validate_linked_literals(section_text: str, symbol_text: str, text: bytes,
                             text_base: int, tables: list[dict]) -> list[dict]:
    """Bind every admitted object literal to the final RX image's actual bytes."""
    sections={match[1]:match[2] for match in re.finditer(r'(?m)^\s*\[\s*(\d+)\]\s+(\S+)\s+',section_text)}
    rows=[line.split() for line in symbol_text.splitlines() if len(line.split())==8 and line.split()[3]=='OBJECT' and line.split()[6]!='UND']
    if len(rows)!=len(tables) or {row[-1] for row in rows}!={table['symbol'] for table in tables}:
        raise Core0Error('Lemmasim final literal object inventory differs')
    observed=[];extents=[]
    for table in tables:
        row=next(row for row in rows if row[-1]==table['symbol']);address,size=int(row[1],16),int(row[2]);offset=address-text_base
        expected=struct.pack('<'+str(len(table['values']))+'Q',*table['values'])
        if row[4:6]!=['LOCAL','DEFAULT'] or sections.get(row[6])!='.text' or size!=table['bytes'] or address%8 or offset<0 or offset+size>len(text) or text[offset:offset+size]!=expected:
            raise Core0Error('Lemmasim final RX literal bytes/extent/ownership differs')
        if any(offset<end and begin<offset+size for begin,end in extents):
            raise Core0Error('Lemmasim final literal extents overlap')
        extents.append((offset,offset+size));observed.append(dict(symbol=row[-1],address=address,bytes=size,
            source=table['source'],sha256=hashlib.sha256(expected).hexdigest(),writable=False))
    return observed
