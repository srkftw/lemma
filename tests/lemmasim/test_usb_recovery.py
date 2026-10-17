"""Operator admission and namespace tests; actual circuit/guest checks are separate."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
import lemmasim_session as runtime
import usb_recovery


class Observed:
    def __init__(self):
        self.identity = {'backend': 'rtl', 'profile': 'lemma-silicon-dev/0.13.0',
                         'usb_recovery_contract': usb_recovery.CONTRACT}
        self.usb_recovery_spec = ('manifest', 'peer', 'socket', 'outbox', 'helper')
        self.commands = []
        self.state = {'cycle': 100000003, 'usb': {'recovery': True, 'terminal': 1,
            'connection_epoch': 1, 'next_request': 123456, 'namespace_binding': 'a'*64}}

    def call(self, command):
        self.commands.append(command)
        return self.state

    def close(self):
        pass


class RecoveryAdmission(unittest.TestCase):
    def session(self, root, mode='developer'):
        path = root/str(len(list(root.iterdir())))
        path.mkdir()
        machine = Observed()
        session = runtime.Session(machine, path,
            SimpleNamespace(mode=mode, paused=True, quantum=1000))
        self.addCleanup(session.close)
        return session, machine, path

    def request(self):
        return {'action': 'usb-reconnect', 'epoch': 2,
                'next_request': 123456, 'binding': 'a'*64}

    def test_non_original_or_unselected_owner_rejects_before_machine(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for mutation in ('student', 'running', 'restored', 'qemu', 'historical', 'unselected', 'no_namespace'):
                session, machine, _ = self.session(root)
                if mutation == 'student': session.mode = 'student'
                elif mutation == 'running': session.automatic = True
                elif mutation == 'restored': session.restored_parent = root/'snapshot'
                elif mutation == 'qemu': machine.identity['backend'] = 'qemu'
                elif mutation == 'historical': machine.identity['profile'] = 'lemma-silicon-dev/0.11.0'
                elif mutation == 'unselected': machine.identity.pop('usb_recovery_contract')
                else: machine.usb_recovery_spec = None
                with self.assertRaises(ValueError): session.dispatch(self.request())
                self.assertEqual(machine.commands, [])

    def test_namespace_or_malformed_request_rejects_before_machine(self):
        with tempfile.TemporaryDirectory() as raw, patch.object(usb_recovery, 'binding', return_value=('a'*64, {})):
            root = Path(raw)
            for field, value in (('binding', 'b'*64), ('epoch', 1), ('next_request', 0), ('extra', 0)):
                session, machine, path = self.session(root)
                request = self.request(); request[field] = value
                with self.assertRaises(ValueError): session.dispatch(request)
                self.assertEqual(machine.commands, [])
                self.assertEqual((path/'external.jsonl').read_bytes(), b'')

    def test_stale_or_active_state_has_no_capture_or_reconnect(self):
        with tempfile.TemporaryDirectory() as raw, patch.object(usb_recovery, 'binding', return_value=('a'*64, {})):
            root = Path(raw)
            for field, value in (('terminal', 0), ('connection_epoch', 2),
                                 ('next_request', 123457), ('namespace_binding', 'b'*64)):
                session, machine, path = self.session(root)
                machine.state['usb'][field] = value
                with self.assertRaises(ValueError): session.dispatch(self.request())
                self.assertEqual(machine.commands, ['inspect'])
                self.assertEqual((path/'external.jsonl').read_bytes(), b'')

    def test_selected_epoch_is_captured_as_external_action(self):
        with tempfile.TemporaryDirectory() as raw, patch.object(usb_recovery, 'binding', return_value=('a'*64, {'contract': usb_recovery.CONTRACT})):
            session, machine, path = self.session(Path(raw))
            request = self.request(); result = session.dispatch(request)
            self.assertEqual(machine.commands, ['inspect', 'usb-reconnect 2 123456'])
            row = json.loads((path/'external.jsonl').read_text())
            self.assertEqual((row['admission'], row['cycle'], row['request']), ('applied', 100000003, request))
            self.assertEqual((session.event_count, session.event_cursor), (1, 1))
            self.assertEqual(result['connection_binding']['contract'], usb_recovery.CONTRACT)
            with self.assertRaises(ValueError): runtime.external_command(request, 100000003)

    def test_container11_requires_explicit_recovery_scope(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw)/'state'; identity = '0'*64
            header = b'LMSSRTL1'+(11).to_bytes(8, 'little')+identity.encode()+(16).to_bytes(8, 'little')+(1).to_bytes(8, 'little')+bytes(16)+bytes(8)+(17).to_bytes(8, 'little')+b'x'
            path.write_bytes(header)
            machine = runtime.RTL.__new__(runtime.RTL)
            machine.identity = {'profile': 'lemma-silicon-dev/0.13.0', 'usb_recovery_contract': usb_recovery.CONTRACT}
            machine.checkpoint_identity = identity
            machine.preflight_checkpoint(path, 17)
            machine.identity.pop('usb_recovery_contract')
            with self.assertRaises(ValueError): machine.preflight_checkpoint(path, 17)
            path.write_bytes(header[:8]+(10).to_bytes(8, 'little')+header[16:])
            machine.preflight_checkpoint(path, 17)
            machine.identity['usb_recovery_contract'] = usb_recovery.CONTRACT
            with self.assertRaises(ValueError): machine.preflight_checkpoint(path, 17)

    def test_binding_preserves_changing_payload_but_names_immutable_owner(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); prepared = root/'prepared'; helper = root/'helper'; peer = root/'peer'; peer.mkdir()
            prepared.write_bytes(b'exact manifest'); helper.write_bytes(b'raw IO')
            (peer/'base.img').touch()
            with (peer/'base.img').open('r+b') as stream: stream.truncate(268435456)
            host = {'schema': 'lemma-usb-host-dev/4', 'policy_version': 'lemma-usb-pending-policy/4', 'binary': {'sha256': 'c'*64}}
            with patch('lemmasim_usb_pending.validate', return_value=host), patch('lemmasim_companion.peer_info', return_value={'writer': 91}):
                args = (prepared, peer, root/'socket', root/'outbox', helper)
                first, identity = usb_recovery.binding(*args)
                with (peer/'base.img').open('r+b') as stream: stream.write(b'actual changed backing')
                (root/'outbox').write_bytes(b'actual changing transaction state')
                self.assertEqual(usb_recovery.binding(*args)[0], first)
                helper.write_bytes(b'changed raw IO')
                self.assertNotEqual(usb_recovery.binding(*args)[0], first)
                self.assertEqual(first, hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
