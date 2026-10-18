#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Apply the exact QEMU11.1.1 host TCI helper optimization, with no type guessing."""
from pathlib import Path
import argparse,hashlib,json,subprocess
HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def apply(root):
    root=Path(root);manifest=json.loads((HERE/'typed_helpers.json').read_text());patch=HERE/'tci-typed-helpers.patch'
    if (root/'VERSION').read_text().strip()!='11.1.1':raise ValueError('Exact QEMU11.1.1 helper source required')
    if sha(patch)!=manifest['patch_sha256']:raise ValueError('Typed helper patch identity differs')
    for relative,expected in manifest['sources'].items():
        if not (root/relative).is_file() or (root/relative).is_symlink() or sha(root/relative)!=expected['before']:
            raise ValueError('Exact upstream helper source differs before any mutation:'+relative)
    subprocess.run(['patch','--batch','--forward','-p1','--input',str(patch.resolve())],cwd=root,check=True,timeout=30)
    for relative,expected in manifest['sources'].items():
        if sha(root/relative)!=expected['after']:raise ValueError('Patched exact helper source differs:'+relative)
    return manifest

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--report',required=True,type=Path);a=p.parse_args()
    value=apply(a.source);a.report.write_text(json.dumps(value,indent=2)+'\n')
if __name__=='__main__':main()
