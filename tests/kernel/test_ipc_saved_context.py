"""Independent literal CFG for the current four-page blocked context audit."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from audit_kernel import validate_current_ipc_saved_context
from core0_common import Core0Error
from test_ipc_audit import FAILED

P = 'Lemma.Kernel.'
NAMES = {P+'Task.'+name: name for name in ('lookup', 'failed', 'fatal', 'stateOffset', 'blocked')}
NAMES.update({P+'Memory.AddressSpace.'+name: name for name in ('base', 'activeRoot', 'userContextOffset')})
NAMES.update({P+'Memory.Access.read64': 'read64', P+'Process.validateStackAt': 'stack'})
CONSTANTS = {'stateOffset': 8, 'blocked': 5, 'activeRoot': 0x80400600, 'userContextOffset': 2048}
BODY = '''entry:
  %lookupCall = call { i64, i64 } @lookup(i64 %arg0)
  %lookupStatus = extractvalue { i64, i64 } %lookupCall, 0
  %lookupNarrow = trunc i64 %lookupStatus to i8
  %record = extractvalue { i64, i64 } %lookupCall, 1
  %lookupBad = call zeroext i1 @failed(i8 zeroext %lookupNarrow)
  %lookupFails = icmp eq i1 %lookupBad, 1
  br i1 %lookupFails, label %failure, label %stateRead
stateRead:
  %stateOffset = call i64 @stateOffset()
  %stateAddress = add i64 %record, %stateOffset
  %stateCall = call { i64, i64 } @read64(i64 %stateAddress)
  %stateStatus = extractvalue { i64, i64 } %stateCall, 0
  %stateNarrow = trunc i64 %stateStatus to i8
  %state = extractvalue { i64, i64 } %stateCall, 1
  %stateBad = call zeroext i1 @failed(i8 zeroext %stateNarrow)
  %stateFails = icmp eq i1 %stateBad, 1
  br i1 %stateFails, label %failure, label %stateCheck
stateCheck:
  %blocked = call i64 @blocked()
  %isBlocked = icmp eq i64 %state, %blocked
  br i1 %isBlocked, label %baseRead, label %failure
baseRead:
  %baseCall = call { i64, i64 } @base(i64 %arg0)
  %baseStatus = extractvalue { i64, i64 } %baseCall, 0
  %baseNarrow = trunc i64 %baseStatus to i8
  %base = extractvalue { i64, i64 } %baseCall, 1
  %baseBad = call zeroext i1 @failed(i8 zeroext %baseNarrow)
  %baseFails = icmp eq i1 %baseBad, 1
  br i1 %baseFails, label %failure, label %rootRead
rootRead:
  %rootAddress = add i64 %base, 64
  %rootCall = call { i64, i64 } @read64(i64 %rootAddress)
  %rootStatus = extractvalue { i64, i64 } %rootCall, 0
  %rootNarrow = trunc i64 %rootStatus to i8
  %root = extractvalue { i64, i64 } %rootCall, 1
  %rootBad = call zeroext i1 @failed(i8 zeroext %rootNarrow)
  %rootFails = icmp eq i1 %rootBad, 1
  br i1 %rootFails, label %failure, label %activeRead
activeRead:
  %activeAddress = call i64 @activeRoot()
  %activeCall = call { i64, i64 } @read64(i64 %activeAddress)
  %activeStatus = extractvalue { i64, i64 } %activeCall, 0
  %activeNarrow = trunc i64 %activeStatus to i8
  %active = extractvalue { i64, i64 } %activeCall, 1
  %activeBad = call zeroext i1 @failed(i8 zeroext %activeNarrow)
  %activeFails = icmp eq i1 %activeBad, 1
  br i1 %activeFails, label %failure, label %activeCheck
activeCheck:
  %isActive = icmp eq i64 %active, %root
  br i1 %isActive, label %failure, label %translationRead
translationRead:
  %translationAddress = add i64 %base, 72
  %translationCall = call { i64, i64 } @read64(i64 %translationAddress)
  %translationStatus = extractvalue { i64, i64 } %translationCall, 0
  %translationNarrow = trunc i64 %translationStatus to i8
  %translation = extractvalue { i64, i64 } %translationCall, 1
  %translationBad = call zeroext i1 @failed(i8 zeroext %translationNarrow)
  %translationFails = icmp eq i1 %translationBad, 1
  br i1 %translationFails, label %failure, label %satpRead
satpRead:
  %offset0 = call i64 @userContextOffset()
  %saved0 = add i64 %base, %offset0
  %satpAddress = add i64 %saved0, 272
  %satpCall = call { i64, i64 } @read64(i64 %satpAddress)
  %satpStatus = extractvalue { i64, i64 } %satpCall, 0
  %satpNarrow = trunc i64 %satpStatus to i8
  %satp = extractvalue { i64, i64 } %satpCall, 1
  %satpBad = call zeroext i1 @failed(i8 zeroext %satpNarrow)
  %satpFails = icmp eq i1 %satpBad, 1
  br i1 %satpFails, label %failure, label %satpCheck
satpCheck:
  %isTranslation = icmp eq i64 %satp, %translation
  br i1 %isTranslation, label %zeroRead, label %failure
zeroRead:
  %offset1 = call i64 @userContextOffset()
  %saved1 = add i64 %base, %offset1
  %zeroCall = call { i64, i64 } @read64(i64 %saved1)
  %zeroStatus = extractvalue { i64, i64 } %zeroCall, 0
  %zeroNarrow = trunc i64 %zeroStatus to i8
  %zero = extractvalue { i64, i64 } %zeroCall, 1
  %zeroBad = call zeroext i1 @failed(i8 zeroext %zeroNarrow)
  %zeroFails = icmp eq i1 %zeroBad, 1
  br i1 %zeroFails, label %failure, label %zeroCheck
zeroCheck:
  %isZero = icmp eq i64 %zero, 0
  br i1 %isZero, label %privilegeRead, label %failure
privilegeRead:
  %offset2 = call i64 @userContextOffset()
  %saved2 = add i64 %base, %offset2
  %privilegeAddress = add i64 %saved2, 264
  %privilegeCall = call { i64, i64 } @read64(i64 %privilegeAddress)
  %privilegeStatus = extractvalue { i64, i64 } %privilegeCall, 0
  %privilegeNarrow = trunc i64 %privilegeStatus to i8
  %privilege = extractvalue { i64, i64 } %privilegeCall, 1
  %privilegeBad = call zeroext i1 @failed(i8 zeroext %privilegeNarrow)
  %privilegeFails = icmp eq i1 %privilegeBad, 1
  br i1 %privilegeFails, label %failure, label %privilegeCheck
privilegeCheck:
  %isPrivilege = icmp eq i64 %privilege, 8589934624
  br i1 %isPrivilege, label %stackRead, label %failure
stackRead:
  %stackCall = call { i64, i64 } @stack(i64 %base)
  %stackStatus = extractvalue { i64, i64 } %stackCall, 0
  %stackNarrow = trunc i64 %stackStatus to i8
  %top = extractvalue { i64, i64 } %stackCall, 1
  %stackBad = call zeroext i1 @failed(i8 zeroext %stackNarrow)
  %stackFails = icmp eq i1 %stackBad, 1
  br i1 %stackFails, label %failure, label %topRead
topRead:
  %offset3 = call i64 @userContextOffset()
  %saved3 = add i64 %base, %offset3
  %topAddress = add i64 %saved3, 280
  %topCall = call { i64, i64 } @read64(i64 %topAddress)
  %topStatus = extractvalue { i64, i64 } %topCall, 0
  %topNarrow = trunc i64 %topStatus to i8
  %storedTop = extractvalue { i64, i64 } %topCall, 1
  %topBad = call zeroext i1 @failed(i8 zeroext %topNarrow)
  %topFails = icmp eq i1 %topBad, 1
  br i1 %topFails, label %failure, label %topCheck
topCheck:
  %isTop = icmp eq i64 %storedTop, %top
  br i1 %isTop, label %success, label %failure
success:
  %offset4 = call i64 @userContextOffset()
  %saved4 = add i64 %base, %offset4
  br label %merge
failure:
  %fatalCall = call { i64, i64 } @fatal()
  %fatalWord = extractvalue { i64, i64 } %fatalCall, 0
  %fatalStatus = trunc i64 %fatalWord to i8
  %fatalValue = extractvalue { i64, i64 } %fatalCall, 1
  br label %merge
merge:
  %status = phi i8 [ 0, %success ], [ %fatalStatus, %failure ]
  %value = phi i64 [ %saved4, %success ], [ %fatalValue, %failure ]
  br label %return
return:
  %wide = zext i8 %status to i64
  %partial = insertvalue { i64, i64 } poison, i64 %wide, 0
  %complete = insertvalue { i64, i64 } %partial, i64 %value, 1
  ret { i64, i64 } %complete
'''


class CurrentSavedContext(unittest.TestCase):
    def check(self, body=BODY):
        return validate_current_ipc_saved_context(body, NAMES, CONSTANTS, FAILED)

    def test_literal_exact_checked_reads_and_success(self):
        value=self.check()
        self.assertEqual(value['context_offset'],2048)
        self.assertEqual(value['descriptor_base'],'%base')
        self.assertEqual(value['saved_pointer'],'%saved4')
        self.assertEqual(len(value['read_addresses']),8)
        self.assertEqual(value['read_addresses'][2],0x80400600)
        self.assertEqual(len(value['checked_read_gates']),11)

    def test_missing_altered_or_unguarded_descriptor_and_helper_rejected(self):
        cases=[BODY.replace('@base(i64 %arg0)','@base(i64 4096)'),
               BODY.replace('@stack(i64 %base)','@stack(i64 %arg0)'),
               BODY.replace('@stack(i64 %base)','@stack(i64 2181038080)'),
               BODY.replace('%baseCall, 1','%baseCall, 0'),
               BODY.replace('%baseFails, label %failure, label %rootRead','%baseFails, label %rootRead, label %failure'),
               BODY.replace('%stackFails, label %failure, label %topRead','%stackFails, label %topRead, label %failure'),
               BODY.replace('%isBlocked, label %baseRead, label %failure','%isBlocked, label %failure, label %baseRead')]
        for body in cases:
            with self.subTest(body=body[:80]),self.assertRaises(Core0Error):self.check(body)

    def test_real_context_field_and_inactive_root_guards_cannot_be_bypassed(self):
        cases=[BODY.replace('add i64 %base, 64','add i64 %base, 56'),
               BODY.replace('add i64 %base, 72','add i64 %base, 80'),
               BODY.replace('%saved0, 272','%saved0, 280'),
               BODY.replace('%saved2, 264','%saved2, 256'),
               BODY.replace('%saved3, 280','%saved3, 272'),
               BODY.replace('%isActive, label %failure, label %translationRead','%isActive, label %translationRead, label %failure'),
               BODY.replace('%satp, %translation','%satp, %root'),
               BODY.replace('%zero, 0','%zero, 1'),
               BODY.replace('%privilege, 8589934624','%privilege, 8589934625'),
               BODY.replace('%storedTop, %top','%storedTop, %base'),
               BODY.replace('%rootFails, label %failure, label %activeRead','%rootFails, label %activeRead, label %failure'),
               BODY.replace('%topFails, label %failure, label %topCheck','%topFails, label %topCheck, label %failure')]
        for body in cases:
            with self.subTest(body=body[:80]),self.assertRaises(Core0Error):self.check(body)

    def test_successful_context_pointer_and_mutation_are_pinned(self):
        for body in (BODY.replace('add i64 %base, %offset4','add i64 %arg0, %offset4'),
                     BODY.replace('[ %saved4, %success ]','[ %top, %success ]'),
                     BODY.replace('[ %fatalStatus, %failure ]','[ 0, %failure ]'),
                     BODY.replace('[ %fatalValue, %failure ]','[ %saved4, %failure ]'),
                     BODY.replace('zext i8 %status to i64','zext i8 0 to i64'),
                     BODY.replace('i64 %value, 1','i64 %top, 1'),
                     BODY.replace('ret { i64, i64 } %complete','ret { i64, i64 } %partial'),
                     BODY.replace('success:\n','success:\n  %changed = call { i64, i64 } @write64(i64 %base, i64 0)\n')):
            with self.assertRaises(Core0Error):self.check(body)


if __name__=='__main__':unittest.main()
