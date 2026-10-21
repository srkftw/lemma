#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reversible SRAM reference spelling for Netgen's SPICE/Verilog readers.

No devices, values, connection arguments or bit identities are removed. Original
PDK/source bytes stay immutable. This does not address the lvsres model mismatch.
"""
import re

ALIASES = {'VDD!': 'lemma_lvs_VDD', 'VDDARRAY!': 'lemma_lvs_VDDARRAY', 'VSS!': 'lemma_lvs_VSS'}


def cdl_alias(raw):
    if '[' in raw or ']' in raw or 'lemma_lvs_' in raw.lower():
        raise ValueError('Unadmitted SRAM CDL alias collision')
    if any(bit != str(int(bit)) for bit in re.findall(r'<(\d+)>', raw)):
        raise ValueError('Noncanonical bus bit could merge in the Verilog reader')
    result = re.sub(r'<(\d+)>', r'[\1]', raw)
    for original, alias in ALIASES.items():
        result = re.sub(r'(?<!\S)' + re.escape(original) + r'(?!\S)', alias, result)
    if restore_cdl(result) != raw:
        raise ValueError('SRAM CDL alias is not exactly reversible')
    return result


def restore_cdl(derived):
    result = derived
    for original, alias in ALIASES.items():
        result = re.sub(r'(?<!\S)' + re.escape(alias) + r'(?!\S)', original, result)
    return re.sub(r'\[(\d+)\]', r'<\1>', result)


def verilog_alias(raw, connected_power):
    if 'lemma_lvs_' in raw.lower():
        raise ValueError('Unadmitted Verilog alias collision')
    result = raw
    for original, alias in ALIASES.items():
        token = '.\\' + original + ' '
        if connected_power and raw.count(token) != 3:
            raise ValueError('Missing exact three SRAM supply connections: ' + original)
        result = result.replace(token, '.' + alias + ' ')
    if restore_verilog(result) != raw:
        raise ValueError('Verilog PG port alias is not exactly reversible')
    return result


def restore_verilog(derived):
    result = derived
    for original, alias in ALIASES.items():
        result = result.replace('.' + alias + ' ', '.\\' + original + ' ')
    return result


def require_originals(derived_cdl, original_cdl, derived_verilog, original_verilog):
    if restore_cdl(derived_cdl) != original_cdl or restore_verilog(derived_verilog) != original_verilog:
        raise ValueError('Reference adapter changed a device, bit, connection, or source byte')



def coldec2_zero_defaults(raw, reference, original_psp):
    """Expand only the reviewed connected COLDEC2 leaf's absent zero defaults.

    All503 layout MOS devices and all44 reference NRS/NRD values are required.
    Existing parameters are never overwritten. This exact source relation covers
    the demonstrated Netgen parallel-MOS property false negative; it is not a
    general model adapter, resistor waiver or parameter-LVS qualification.
    """
    def need(value, message):
        if not value:
            raise ValueError(message)

    need(re.match(r'^\.subckt RM_IHPSG13_1P_COLDEC2\b', raw), 'unsupported default-only leaf')
    need(len(re.findall(r'^\.subckt\b', raw, re.M)) == 1, 'one exact extracted leaf required')
    for key in ('NRS', 'NRD'):
        declarations = re.findall(r'`IPRnb\(' + key + r'\s*,([^,]+),', original_psp)
        need(declarations and [x.strip() for x in declarations] == ['0.0'],
             'original PSP default must be explicitly0.0: ' + key)
        values = re.findall(r'(?i)\b' + key + r'\s*=\s*([^\s]+)', reference)
        need(len(values) == 44 and set(values) == {'0'},
             'all44 actual reference values must be exact zero: ' + key)
    need(not re.search(r'(?i)\bnrs\s*=|\bnrd\s*=', raw),
         'present NRS/NRD is outside the default-only domain')
    joined = re.sub(r'\n\+\s*', ' ', raw)
    devices = [line for line in joined.splitlines() if line.startswith('M')]
    need(len(devices) == 503, 'exact503 extracted MOS devices required')
    for line in devices:
        fields = line.split()
        need(len(fields) >= 8 and fields[5] in ('sg13_lv_nmos', 'sg13_lv_pmos'),
             'unreviewed MOS model or terminal arity')
        keys = re.findall(r'\b([A-Za-z_][A-Za-z_0-9]*)\s*=', line)
        need(len(keys) == len(set(keys)) and set(keys) <= {'w', 'l', 'ad', 'pd', 'as', 'ps'}
             and {'w', 'l'} <= set(keys), 'unexpected or duplicate extracted device parameter')
    derived = re.sub(r'(?m)^(M\S+[^\n]*)', r'\1 nrs=0 nrd=0', raw)
    need(re.sub(r' nrs=0 nrd=0(?=\n|$)', '', derived) == raw,
         'default expansion changed another source byte')
    return derived


def require_coldec2_defaults(raw, derived, reference, original_psp):
    if coldec2_zero_defaults(raw, reference, original_psp) != derived:
        raise ValueError('derived default, device or another source byte changed')
