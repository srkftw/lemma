"""Host reference failures only: no guest/allocator result is manufactured."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from buffer_reference import BufferReference, Request, MASK
from core0_common import Core0Error


def reply(op, *, epoch=1, handle=0, length=0, count=0, capacity=0, status=0,
          transport=0, data=b''):
    return dict(operation=op, epoch=epoch, handle=handle, length=length,
                count=count, detail=capacity, application_status=status,
                transport_status=transport, data_hex=data.hex())


class BufferReferenceFailures(unittest.TestCase):
    def create(self, model, handle, capacity, epoch=1):
        model.accept(Request(1, epoch, length=capacity),
                     reply(1, epoch=epoch, handle=handle, capacity=capacity))

    def test_binary_exact_read_and_wrong_byte_rejection(self):
        m = BufferReference(1)
        self.create(m, 4, 128)
        data = (b'\0\xffK1LMO1' + 'λ界'.encode() + bytes(range(128)))[:128]
        m.accept(Request(2, 1, 4, length=128, data=data),
                 reply(2, handle=4, length=128, count=128, capacity=128))
        m.accept(Request(3, 1, 4, length=128),
                 reply(3, handle=4, length=128, count=128, capacity=128, data=data))
        before = m.snapshot()
        with self.assertRaises(Core0Error):
            m.accept(Request(3, 1, 4, length=128),
                     reply(3, handle=4, length=128, count=128, capacity=128,
                           data=data[:-1] + bytes([data[-1] ^ 1])))
        self.assertEqual(m.snapshot(), before)

    def test_failed_append_and_maximum_offset_preserve_bytes(self):
        m = BufferReference(1)
        self.create(m, 4, 4)
        m.accept(Request(4, 1, 4, length=3, data=b'\0\xffx'),
                 reply(4, handle=4, length=3, count=3, capacity=4))
        before = m.snapshot()
        m.accept(Request(4, 1, 4, length=2, data=b'yz'), reply(4, status=205))
        m.accept(Request(2, 1, 4, offset=MASK, length=1, data=b'x'), reply(2, status=205))
        self.assertEqual(m.snapshot(), before)
        m.accept(Request(3, 1, 4, length=3),
                 reply(3, handle=4, length=3, count=3, capacity=4, data=b'\0\xffx'))

    def test_foreign_stale_and_wrong_epoch_errors_do_not_expose_fields(self):
        m = BufferReference(1)
        m.foreign_created(5)
        m.accept(Request(5, 1, 5), reply(5, status=202))
        m.accept(Request(5, 1, 4), reply(5, status=201))
        m.accept(Request(5, 9, 5), reply(5, status=200))
        before = m.snapshot()
        with self.assertRaises(Core0Error):
            m.accept(Request(5, 1, 5), reply(5, status=202, capacity=128))
        self.assertEqual(m.snapshot(), before)

    def test_per_client_and_global_quotas_require_unchanged_inventory(self):
        m = BufferReference(1)
        self.create(m, 4, 8)
        self.create(m, 5, 8)
        before = m.snapshot()
        m.accept(Request(1, 1, length=8), reply(1, status=203))
        self.assertEqual(m.snapshot(), before)
        m.accept(Request(6, 1, 5), reply(6))
        m.foreign_created(9)
        m.foreign_created(6)
        m.foreign_created(7)
        before = m.snapshot()
        m.accept(Request(1, 1, length=8), reply(1, status=204))
        self.assertEqual(m.snapshot(), before)

    def test_stale_generation_rejected_before_shadow_publication(self):
        m = BufferReference(1)
        self.create(m, 4, 8)
        m.accept(Request(6, 1, 4), reply(6))
        before = m.snapshot()
        with self.assertRaises(Core0Error):
            self.create(m, 4, 8)
        self.assertEqual(m.snapshot(), before)
        self.create(m, 8, 8)
        m.accept(Request(5, 1, 4), reply(5, status=201))

    def test_malformed_shape_precedes_epoch_and_handle_checks(self):
        m = BufferReference(1)
        self.assertEqual(m.expected_status(Request(1, 9, handle=5, length=8)), 206)
        self.assertEqual(m.expected_status(Request(4, 9, handle=5, offset=1)), 206)
        self.assertEqual(m.expected_status(Request(5, 9, handle=5, length=1)), 206)

    def test_restart_requires_observed_epoch_advance_and_discards_shadow(self):
        m = BufferReference(1)
        self.create(m, 4, 8)
        with self.assertRaises(Core0Error):
            m.restarted(1)
        m.restarted(2)
        m.accept(Request(5, 1, 4), reply(5, epoch=2, status=200))
        self.create(m, 4, 8, epoch=2)
        self.assertEqual(m.buffers[4]['data'], b'')

    def test_wrong_response_cannot_publish_a_write(self):
        m = BufferReference(1)
        self.create(m, 4, 8)
        before = m.snapshot()
        with self.assertRaises(Core0Error):
            m.accept(Request(2, 1, 4, length=2, data=b'xy'),
                     reply(2, handle=4, length=1, count=2, capacity=8))
        self.assertEqual(m.snapshot(), before)
        m.accept(Request(2, 1, 4, length=2, data=b'xy'), reply(2, transport=96),
                 transport_status=96)
        self.assertEqual(m.snapshot(), before)

    def test_malformed_response_types_and_private_statuses_cannot_publish(self):
        m = BufferReference(1)
        before = m.snapshot()
        valid = reply(1, handle=4, capacity=8)
        for field in ("operation", "epoch", "handle", "length", "count", "detail",
                      "application_status", "transport_status", "data_hex"):
            malformed = {**valid, field: False}
            with self.subTest(field=field), self.assertRaises(Core0Error):
                m.accept(Request(1, 1, length=8), malformed)
            self.assertEqual(m.snapshot(), before)
        for status in (95, 254, 255):
            with self.subTest(status=status), self.assertRaises(Core0Error):
                m.accept(Request(1, 1, length=8), reply(1, transport=status), transport_status=status)
            self.assertEqual(m.snapshot(), before)

    def test_allocation_error_requires_a_public_page_status_and_unchanged_shadow(self):
        m = BufferReference(1)
        before = m.snapshot()
        m.accept(Request(1, 1, length=8), reply(1, status=208, capacity=38), allocation_failure=True)
        self.assertEqual(m.snapshot(), before)
        for detail in (0, 11, 254, 255):
            with self.subTest(detail=detail), self.assertRaises(Core0Error):
                m.accept(Request(1, 1, length=8), reply(1, status=208, capacity=detail), allocation_failure=True)
            self.assertEqual(m.snapshot(), before)
        with self.assertRaises(Core0Error):
            m.accept(Request(1, 1, length=8), reply(1, status=208, capacity=38), allocation_failure="yes")
        self.assertEqual(m.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
