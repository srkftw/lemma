#!/usr/bin/env python3
"""Bounded current-document policy checks; no build, execution or historical receipt rewriting."""
from __future__ import annotations
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
HOOKS = {'AGENTS.md': 'docs/contributing.html',
         '.github/pull_request_template.md': 'docs/pull-request-guidance.html'}

class Document(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.ids, self.links, self.errors = set(), [], []
        self.charset = False
        self.feed(text)
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            if attrs['id'] in self.ids: self.errors.append('duplicate anchor: ' + attrs['id'])
            self.ids.add(attrs['id'])
        if tag == 'meta' and attrs.get('charset', '').lower() == 'utf-8': self.charset = True
        for key in ('href', 'src'):
            if key in attrs: self.links.append(attrs[key])

def source_paths(root):
    """Include new source documents, exclude ignored artifacts and absent deleted paths."""
    try:
        result = subprocess.run(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
            cwd=root, check=True, capture_output=True, timeout=15)
        return sorted({name for name in result.stdout.decode().split('\0') if name and (root / name).is_file()})
    except (subprocess.SubprocessError, OSError):
        # Tests also exercise copied, non-Git trees. Generated output is never source.
        return sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()
                      and not {'.git', 'build', '.lake', '__pycache__', 'dist'} & set(p.relative_to(root).parts))

def validate(root):
    root = Path(root).resolve()
    errors = []
    try:
        inventory = json.loads((root / 'docs/document-map.json').read_text(encoding='utf-8'))
        if inventory.get('schema') != 'lemma-document-map/v1': raise ValueError('unsupported document map')
        rows = inventory['documents']
        exceptions = inventory['exceptions']
        if not isinstance(rows, list) or not rows or not isinstance(exceptions, dict): raise ValueError('empty or malformed map')
    except (OSError, ValueError, KeyError) as exc: return ['Unreadable documentation inventory: ' + str(exc)]
    paths = source_paths(root)
    for name in paths:
        if Path(name).suffix.lower() == '.md' and name not in exceptions:
            errors.append('Unapproved narrative Markdown: ' + name)
        if re.fullmatch(r'readme(?:\..*)?', Path(name).name, re.I):
            errors.append('Automatically selected README must not be generated or maintained: ' + name)
    for name, target in HOOKS.items():
        try: text = (root / name).read_text(encoding='utf-8')
        except OSError: errors.append('Missing agent/template entry point: ' + name); continue
        if not re.fullmatch(r'\s*<!--(?:(?!-->|<!--)[\s\S])*-->\s*', text) or target not in text:
            errors.append('Entry point must be a minimal raw-readable comment linking its HTML guide: ' + name)
        if not (root / target).is_file(): errors.append('Missing entry point guide: ' + target)
    for row in rows:
        if row.get('current'):
            if not (root / row['current']).is_file(): errors.append('Missing converted document: ' + row['current'])
        elif row.get('exception'):
            path = root / row['original']
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row['original_sha256']:
                errors.append('Changed immutable historical documentation: ' + row['original'])
    # Scope only first-party narrative HTML. Browser application HTML remains code.
    html_paths = [name for name in paths if name.endswith('.html') and
                  (name.startswith(('docs/', 'codex/', 'conformance/', 'templates/', 'tooling/'))
                   or name in {row.get('current') for row in rows})]
    documents = {}
    for name in html_paths:
        try:
            text = (root / name).read_text(encoding='utf-8')
            parsed = Document(text)
            if not text.lstrip().lower().startswith('<!doctype html>') or not parsed.charset:
                errors.append('HTML document needs doctype and UTF-8 declaration: ' + name)
            errors.extend(name + ': ' + item for item in parsed.errors)
            documents[name] = parsed
        except (OSError, UnicodeError, ValueError) as exc: errors.append(name + ': ' + str(exc))
    for name, parsed in documents.items():
        for link in parsed.links:
            url = urlsplit(link)
            if url.scheme or url.netloc: continue  # Historical pinned URLs remain untouched.
            if url.path.startswith('/'): continue  # Absolute external environment/file references.
            target = ((root / name).parent / unquote(url.path)).resolve() if url.path else root / name
            if not target.is_relative_to(root): errors.append(name + ': current link escapes source tree: ' + link); continue
            if not target.exists(): errors.append(name + ': broken current link: ' + link); continue
            relative = str(target.relative_to(root))
            if url.fragment and relative in documents and unquote(url.fragment) not in documents[relative].ids:
                errors.append(name + ': missing current anchor: ' + link)
    return errors

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    errors = validate(args.root)
    for error in errors: print('ERROR: ' + error, file=sys.stderr)
    if errors: return 1
    print('PASS_CURRENT_HTML_DOCUMENTATION_POLICY')
    return 0

if __name__ == '__main__': raise SystemExit(main())
