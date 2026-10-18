"""Offline tests with a fake gh executable. No GitHub write requests are sent."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FAKE_GH = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['MOCK_LOG'], 'a') as f:
    f.write(json.dumps(args) + '\n')
state = pathlib.Path(os.environ['MOCK_STATE'])
if args[:2] == ['auth', 'status']:
    sys.exit(int(os.environ.get('MOCK_AUTH_FAIL', '0')))
if args and args[0] == 'api':
    print(os.environ.get('MOCK_USER', 'srkftw'))
    sys.exit(0)
if args[:2] == ['repo', 'view']:
    if not state.exists() and os.environ.get('MOCK_EXISTS') != '1':
        sys.exit(1)
    if 'nameWithOwner,isPrivate' in args:
        print('srkftw/lemma\t' + ('false' if os.environ.get('MOCK_PUBLIC') == '1' else 'true'))
    else:
        print('{"nameWithOwner":"srkftw/lemma"}')
    sys.exit(0)
if args[:2] == ['repo', 'create']:
    if os.environ.get('MOCK_CREATE_FAIL') == '1':
        sys.exit(1)
    state.write_text('created')
    sys.exit(0)
sys.exit(2)
'''

class PublishTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT/'scripts/publish-github.sh').is_file())
        self.temp = tempfile.TemporaryDirectory()
        tmp = Path(self.temp.name)
        self.root = tmp/'lemma'
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns('.git','__pycache__','build'))
        binpath = tmp/'bin'
        binpath.mkdir()
        gh = binpath/'gh'
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        self.log = tmp/'calls.jsonl'
        self.env = dict(os.environ, PATH=str(binpath)+os.pathsep+os.environ['PATH'],
                        MOCK_LOG=str(self.log), MOCK_STATE=str(tmp/'created'),
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0')
    def tearDown(self):
        self.temp.cleanup()
    def run_publish(self, **overrides):
        return subprocess.run(['bash',str(self.root/'scripts/publish-github.sh')],
                              env=dict(self.env,**overrides), capture_output=True, text=True, timeout=20)
    def calls(self):
        return [json.loads(s) for s in self.log.read_text().splitlines()] if self.log.exists() else []
    def did_create(self):
        return any(c[:2] == ['repo','create'] for c in self.calls())
    def prepare_git(self):
        def run(*args):
            subprocess.run(['git','-C',str(self.root),*args],env=self.env,check=True,capture_output=True)
        run('init','--initial-branch=main')
        run('config','user.name','Test')
        run('config','user.email','test@example.invalid')
        run('add','--all')
        run('commit','-m','Test scaffold')
        return run
    def test_snapshot_publishes_private_with_mock(self):
        p = self.run_publish()
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        creates=[c for c in self.calls() if c[:2]==['repo','create']]
        self.assertEqual(len(creates),1)
        self.assertIn('--private',creates[0])
        self.assertIn('--push',creates[0])
        self.assertNotIn('--public',creates[0])
    def test_wrong_account_refused(self):
        p = self.run_publish(MOCK_USER='someone-else')
        self.assertIn("Authenticated as 'someone-else'", p.stderr)
        self.assertNotEqual(p.returncode,0)
        self.assertFalse(self.did_create())
    def test_existing_repo_refused(self):
        p = self.run_publish(MOCK_EXISTS='1')
        self.assertIn('already exists', p.stderr)
        self.assertNotEqual(p.returncode,0)
        self.assertFalse(self.did_create())
    def test_missing_auth_refused(self):
        p = self.run_publish(MOCK_AUTH_FAIL='1')
        self.assertIn('Authenticate first', p.stderr)
        self.assertNotEqual(p.returncode,0)
        self.assertFalse(self.did_create())
    def test_existing_origin_refused(self):
        git = self.prepare_git()
        git('remote','add','origin','https://example.invalid/untouched.git')
        p = self.run_publish()
        self.assertNotEqual(p.returncode,0)
        self.assertFalse(self.did_create())
    def test_dirty_worktree_refused(self):
        self.prepare_git()
        (self.root/'docs/overview.html').write_text('Unreviewed change\n')
        p = self.run_publish()
        self.assertNotEqual(p.returncode,0)
        self.assertFalse(self.did_create())
    def test_failed_create_not_claimed_success(self):
        p = self.run_publish(MOCK_CREATE_FAIL='1')
        self.assertTrue(self.did_create())
        self.assertNotEqual(p.returncode,0)
        self.assertNotIn('Published private repository:',p.stdout)
    def test_visibility_not_verified_does_not_claim_success(self):
        p = self.run_publish(MOCK_PUBLIC='1')
        self.assertIn('private visibility was not verified', p.stderr)
        self.assertNotEqual(p.returncode,0)
        self.assertNotIn('Published private repository:',p.stdout)

if __name__ == '__main__':
    unittest.main()
