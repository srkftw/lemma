#!/usr/bin/env python3
"""Host-only byte reference for observed User Buffer replies.

This shadow state cannot implement a guest operation or certify its allocation.
The runtime checker separately binds authenticated callers, page syscalls,
epochs and lease releases to actual compiled guests before updating this model.
"""
from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy

from core0_common import Core0Error

MASK = (1 << 64) - 1
PUBLIC_TRANSPORT_STATUSES = frozenset((0, 12, 16, 17, 22, 33, 38, 71, 72, 73, 74,
                                      80, 81, 83, 89, 90, 91, 92, 93, 94, 96, 97,
                                      98, 99, 100, 101))
PUBLIC_ALLOCATION_ERRORS = frozenset((16, 33, 38, 71, 72, 73, 74))


@dataclass(frozen=True)
class Request:
    operation: int
    epoch: int
    handle: int = 0
    offset: int = 0
    length: int = 0
    data: bytes = b""

    def validate(self):
        if (any(type(v) is not int or not 0 <= v <= MASK for v in
                (self.operation, self.epoch, self.handle, self.offset, self.length))
                or not 1 <= self.operation <= 6 or not isinstance(self.data, bytes)
                or (len(self.data) != self.length if self.operation in (2, 4) else bool(self.data))
                or self.operation in (2, 3, 4) and self.length > 128):
            raise Core0Error("reference request has no exact bounded command shape")


class BufferReference:
    """One full caller's expected bytes; foreign handles need real witnesses."""
    def __init__(self, epoch: int):
        if type(epoch) is not int or not 0 < epoch <= MASK:
            raise Core0Error("reference requires an observed nonzero service epoch")
        self.epoch = epoch
        self.buffers = {}
        self.foreign = set()
        self.generations = {}
        self.operations = 0

    def snapshot(self):
        return deepcopy((self.epoch, self.buffers, self.foreign, self.generations))

    def foreign_created(self, handle: int):
        self._new_handle(handle)
        self.foreign.add(handle)
        self.generations[handle & 3] = handle >> 2

    def released(self, handle: int):
        """Call only after separately verified destroy/actual lease-release evidence."""
        if handle in self.buffers:
            del self.buffers[handle]
        elif handle in self.foreign:
            self.foreign.remove(handle)
        else:
            raise Core0Error("reference release has no live witnessed buffer")

    def restarted(self, epoch: int):
        if type(epoch) is not int or not self.epoch < epoch <= MASK:
            raise Core0Error("reference restart lacks a strictly larger observed epoch")
        self.epoch = epoch
        self.buffers.clear()
        self.foreign.clear()
        self.generations.clear()

    def _new_handle(self, handle: int):
        if (type(handle) is not int or not 4 <= handle <= MASK
                or handle >> 2 <= self.generations.get(handle & 3, 0)
                or any((live & 3) == (handle & 3) for live in (*self.buffers, *self.foreign))):
            raise Core0Error("new buffer reused a live slot or stale generation")

    def expected_status(self, request: Request):
        request.validate()
        if (request.operation == 1 and (request.handle or request.offset)
                or request.operation == 4 and request.offset
                or request.operation in (5, 6) and (request.offset or request.length)):
            return 206
        if request.epoch != self.epoch:
            return 200
        if request.operation == 1:
            if not 1 <= request.length <= 4096:
                return 205
            if len(self.buffers) >= 2:
                return 203
            if len(self.buffers) + len(self.foreign) >= 4:
                return 204
            return 0
        if request.handle in self.foreign:
            return 202
        if request.handle not in self.buffers:
            return 201
        row = self.buffers[request.handle]
        old, capacity = row["data"], row["capacity"]
        if request.operation == 2:
            return 205 if request.offset > len(old) or request.length > capacity - request.offset else 0
        if request.operation == 3:
            return 205 if request.offset > len(old) or request.length > len(old) - request.offset else 0
        if request.operation == 4:
            return 205 if request.length > capacity - len(old) else 0
        return 0

    def accept(self, request: Request, response: dict, *, allocation_failure=False,
               generation_exhausted=False, transport_status=0):
        """Validate the response before publishing any shadow byte change.

        A transport error leaves the shadow uncommitted; this does not establish
        guest rollback. The external observer must settle the operation or
        witness an epoch restart before treating the old shadow as authoritative.
        """
        request.validate()
        if (type(allocation_failure) is not bool or type(generation_exhausted) is not bool
                or type(transport_status) is not int or transport_status not in PUBLIC_TRANSPORT_STATUSES
                or transport_status and (allocation_failure or generation_exhausted)):
            raise Core0Error("reference failure witnesses have inconsistent public ABI types/statuses")
        status = self.expected_status(request)
        if allocation_failure or generation_exhausted:
            if status or request.operation != 1 or allocation_failure and generation_exhausted:
                raise Core0Error("reference resource failure bypassed an earlier checked error")
            status = 208 if allocation_failure else 207
        fields = ("operation", "epoch", "handle", "length", "count", "detail",
                  "application_status", "transport_status", "data_hex")
        if not isinstance(response, dict) or any(key not in response for key in fields):
            raise Core0Error("actual response lacks checked reference fields")
        if (any(type(response[key]) is not int or not 0 <= response[key] <= MASK for key in fields[:-1])
                or response["application_status"] not in (0, *range(200, 209))
                or response["transport_status"] not in PUBLIC_TRANSPORT_STATUSES
                or not isinstance(response["data_hex"], str)):
            raise Core0Error("actual response fields are not declared unsigned ABI values")
        if (response["operation"], response["epoch"], response["transport_status"]) != (
                request.operation, self.epoch, transport_status):
            raise Core0Error("actual operation/epoch/transport differs from the request")
        if transport_status:
            expected = (0, 0, 0, 0, 0, "")
        elif status:
            detail = response["detail"] if status == 208 else 0
            if status == 208 and detail not in PUBLIC_ALLOCATION_ERRORS:
                raise Core0Error("allocation failure lacks its actual public allocator status")
            expected = (0, 0, 0, detail, status, "")
        elif request.operation == 1:
            self._new_handle(response["handle"])
            expected = (response["handle"], 0, 0, request.length, 0, "")
        elif request.operation == 6:
            expected = (0, 0, 0, 0, 0, "")
        else:
            row = self.buffers[request.handle]
            old = row["data"]
            length = (max(len(old), request.offset + request.length) if request.operation == 2
                      else len(old) + request.length if request.operation == 4 else len(old))
            data = old[request.offset:request.offset + request.length] if request.operation == 3 else b""
            count = request.length if request.operation in (2, 3, 4) else 0
            expected = (request.handle, length, count, row["capacity"], 0, data.hex())
        actual = tuple(response[key] for key in fields[2:7]) + (response["data_hex"],)
        if actual != expected:
            raise Core0Error("actual response bytes/length/bounds/ownership differ from independent reference")
        if not transport_status and not status:
            if request.operation == 1:
                handle = response["handle"]
                self.buffers[handle] = {"capacity": request.length, "data": b""}
                self.generations[handle & 3] = handle >> 2
            elif request.operation == 6:
                self.released(request.handle)
            elif request.operation in (2, 4):
                row = self.buffers[request.handle]
                offset = request.offset if request.operation == 2 else len(row["data"])
                row["data"] = row["data"][:offset] + request.data + row["data"][offset + request.length:]
        self.operations += 1
        return status
