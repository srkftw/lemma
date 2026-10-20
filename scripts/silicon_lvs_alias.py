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
