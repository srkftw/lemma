#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Clocked13 adapter for the unchanged, source-pinned real USB notebook workflow.

Every Ready/pixel/record/Save/lost-reply/restart/cold oracle is inherited from
the frozen maintained workflow. This adapter registers one hardware deployment
and enforces its process bounds; it does not implement a machine or guest policy.
"""
from pathlib import Path

import check_guest_usb_notebook as scenario
import silicon_guest_bundle as bundle

NAME='lemma-silicon-dev/0.13.0'
ROLE='usb-clocked-bulk-notebook'
BASE_SHA256='5e3d138686d1e0704f3100dd26c978af622c7e813e1fbcccfb18762eb28fa869'

def source_authority_valid(args):
    return (args.profile==NAME and args.native_bundle is not None and
            args.rtl_source_root is None and args.guest_source_root is None)

class ClockedLive(scenario.NativeUSBSession):
    def boot(self,expected):
        result=super().boot(expected)
        clock=result.get('usb_clocks',{})
        scenario.require((clock.get('quantum_hz'),clock.get('controller_hz'),clock.get('nominal_phy_hz'),
                          clock.get('position'),clock.get('host_ppm'),clock.get('chip_ppm'))==
                         (2400000000,100000000,48000000,0,0,0),
                         'actual Clocked notebook clock facts differ')
        return result

class ClockedChecker(scenario.Checker):
    def __init__(self,args):
        scenario.require(source_authority_valid(args),'exact Clocked immutable bundle required')
        # Validate the whole package before creating a peer or modifying media.
        bundle.prepared(args.native_bundle,'rtl',ROLE,NAME)
        super().__init__(args)
        self.report['scope']=__doc__
        self.report['inherited_observer_sha256']=BASE_SHA256
        self.report['clocked_observer_sha256']=scenario.sha(__file__)
        self.report['bounds'].update(maximum_owned_tree_rss_kib=scenario.WIRE_MAX_TREE_RSS_KIB,
                                     maximum_owned_disk_bytes=scenario.WIRE_MAX_DISK_BYTES)
        self.report['not_qualified']=['full USB MAC/token/topology/electrical/analog CDC conformance',
                                     'privately live external-peer continuation','QEMU cached-state continuation',
                                     'browser hosted peer','owner authentication']

    def sample_resources(self):
        super().sample_resources()
        current=int(next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines()
                         if line.startswith('VmRSS:')))
        current+=sum(item.get('last_sample',{}).get('sampled_resident_kib',0)
                     for item in self.report.get('host_resources',{}).values())
        size=sum(path.stat().st_size for path in self.out.rglob('*')
                 if path.is_file() and not path.is_symlink())
        observed=self.report.setdefault('owned_resource_samples',{})
        observed['peak_rss_kib']=max(observed.get('peak_rss_kib',0),current)
        observed['peak_apparent_disk_bytes']=max(observed.get('peak_apparent_disk_bytes',0),size)
        scenario.require(current<=scenario.WIRE_MAX_TREE_RSS_KIB,'declared Clocked owned RAM ceiling')
        scenario.require(size<=scenario.WIRE_MAX_DISK_BYTES,'declared Clocked owned disk ceiling')

def main():
    scenario.require(scenario.sha(scenario.__file__)==BASE_SHA256,'inherited notebook observer changed')
    # Process-local registration only. The original file and running Wire11
    # owner retain their exact source, classes, rules and deadline semantics.
    scenario.PROFILE_WORKLOADS[NAME]=ROLE
    scenario.source_authority_valid=source_authority_valid
    scenario.NativeUSBSession=ClockedLive
    scenario.Checker=ClockedChecker
    return scenario.main()

if __name__=='__main__':main()
