#!/usr/bin/env python3
"""Run the shared failed-course-Save workflow on the exact canonical RTL.

The shared observer and failure model are unchanged. This adapter selects RTL
phase budgets before launch; it never replaces guest storage or recovery.
"""
import argparse
from pathlib import Path
import resource

from check_course_failed_save import FailedCourse, require


class RTLFailedCourse(FailedCourse):
    def until(self, session, name, cap, host, predicate):
        if name in ("independent-cold-input", "cold-after-failed-FLUSH"):
            host = 7200
        elif name in ("actual-course-body", "cold-original-complete-course-and-acknowledged-ink"):
            host = 3600
        elif name == "expected-failed-FLUSH-visible-course":
            host = 1800
        else:
            raise ValueError("Undeclared RTL failure phase: " + name)
        return super().until(session, name, cap, host, predicate)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("disk", "package", "work-dir", "guest-source-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("native-bundle", "guest-build"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    args.disk = args.disk.resolve()
    args.package = args.package.resolve()
    args.backend = "rtl"
    args.timeout = 120
    args.deadline = 21600
    args.durable_suffix_from = None
    args.checkpoint_relation = "independent cold only"
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    actor = RTLFailedCourse(args)
    actor.report.update(scope=__doc__, rtl_phase_host_limits={
        "cold_each": 7200, "course_each": 3600, "failed_save": 1800},
        claims="Actual RTL clocks; shared independent complete-pixel observer; "
               "injected fail-before-writeback FLUSH only; no OS rollback claim")
    try:
        actor.execute()
    except BaseException as error:
        actor.report.update(status="FAIL", error=repr(error))
        raise
    finally:
        actor.finish()
    require(actor.report["status"] == "PASS_REAL_FAILED_FLUSH_COURSE_INK_COLD",
            "RTL failed-course workflow did not complete")


if __name__ == "__main__":
    main()
