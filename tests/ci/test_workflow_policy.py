#!/usr/bin/env python3
"""Exercise the checked-in workflow policy without target builds or dependencies.

These tests inspect a deliberately narrow YAML layout; actionlint separately
validates the complete YAML and GitHub expression syntax. The expression helper
supports only the operators and format function used by the concurrency policy,
and rejects every unknown token or context field rather than guessing a result.
"""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
FULL = ROOT / ".github/workflows/core0.yml"
PREFLIGHT = ROOT / ".github/workflows/preflight.yml"


def section(source: str, key: str, indent: int = 0) -> str:
    """Read exactly one mapping block, retaining nested lines for inspection."""
    lines = source.splitlines()
    selected = [i for i, line in enumerate(lines)
                if re.fullmatch(" " * indent + re.escape(key) + r":\s*", line)]
    if len(selected) != 1:
        raise ValueError("missing or duplicate mapping: " + key)
    start = selected[0] + 1
    end = start
    while end < len(lines):
        line = lines[end]
        if line.strip() and not line.lstrip().startswith("#"):
            if len(line) - len(line.lstrip()) <= indent:
                break
        end += 1
    return "\n".join(lines[start:end])


def scalar(source: str, key: str, indent: int) -> str:
    values = re.findall(r"^" + " " * indent + re.escape(key) + r":\s*(\S.*)$", source, re.M)
    if len(values) != 1:
        raise ValueError("missing or duplicate scalar: " + key)
    return values[0]


def event_blocks(source: str) -> dict[str, str]:
    block = section(source, "on")
    events = re.findall(r"^  ([a-z_]+):\s*$", block, re.M)
    if len(set(events)) != len(events):
        raise ValueError("duplicate workflow event")
    return {event: section(block, event, 2) for event in events}


def push_branches(block: str) -> list[str]:
    values = section(block, "branches", 4)
    branches = []
    for line in values.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"      - (?:\"([^\"]+)\"|'([^']+)'|([^\s]+))", line)
        if not match:
            raise ValueError("unsupported branch filter: " + line)
        branches.append(next(value for value in match.groups() if value is not None))
    if not branches:
        raise ValueError("empty branch filter")
    return branches


class Expression:
    """Evaluate the actual policy's small GitHub expression subset."""

    TOKEN = re.compile(r"\s*(==|&&|\|\||[(),]|'(?:[^']|'')*'|[A-Za-z_][A-Za-z_0-9.]*)")

    def __init__(self, text: str, context: dict[str, object]):
        self.tokens = []
        self.context = context
        position = 0
        while position < len(text):
            if not text[position:].strip():
                break
            token = self.TOKEN.match(text, position)
            if token is None:
                raise ValueError("unsupported expression at " + text[position:])
            self.tokens.append(token[1])
            position = token.end()
        self.index = 0

    def take(self, expected: str | None = None) -> str:
        if self.index == len(self.tokens):
            raise ValueError("truncated expression")
        token = self.tokens[self.index]
        if expected is not None and token != expected:
            raise ValueError("expected " + expected + ", got " + token)
        self.index += 1
        return token

    def next_is(self, token: str) -> bool:
        return self.index < len(self.tokens) and self.tokens[self.index] == token

    def primary(self):
        token = self.take()
        if token == "(":
            result = self.disjunction()
            self.take(")")
            return result
        if token.startswith("'"):
            return token[1:-1].replace("''", "'")
        if token in ("true", "false", "null"):
            return {"true": True, "false": False, "null": None}[token]
        if token == "format":
            self.take("(")
            arguments = [self.disjunction()]
            while self.next_is(","):
                self.take(",")
                arguments.append(self.disjunction())
            self.take(")")
            return arguments[0].format(*arguments[1:])
        if token not in self.context:
            raise ValueError("unknown expression field: " + token)
        return self.context[token]

    def equality(self):
        result = self.primary()
        while self.next_is("=="):
            self.take("==")
            result = result == self.primary()
        return result

    def conjunction(self):
        result = self.equality()
        while self.next_is("&&"):
            self.take("&&")
            operand = self.equality()
            result = operand if bool(result) else result
        return result

    def disjunction(self):
        result = self.conjunction()
        while self.next_is("||"):
            self.take("||")
            operand = self.conjunction()
            result = result if bool(result) else operand
        return result

    def evaluate(self):
        result = self.disjunction()
        if self.index != len(self.tokens):
            raise ValueError("unexpected trailing expression")
        return result


def expression(value: str, context: dict[str, object]):
    match = re.fullmatch(r"\$\{\{(.*?)\}\}", value)
    if match is None:
        if value in ("true", "false"):
            return value == "true"
        raise ValueError("expected GitHub expression")
    return Expression(match[1], context).evaluate()


def expand(value: str, context: dict[str, object]) -> str:
    return re.sub(r"\$\{\{(.*?)\}\}",
                  lambda match: str(Expression(match[1], context).evaluate()), value)


def context(event: str, *, run: int = 101, pr: int = 5, ref: str = "refs/heads/task/example",
            workflow: str = "Lemma pinned acceptance") -> dict[str, object]:
    return {"github.event_name": event, "github.run_id": run,
            "github.event.pull_request.number": pr if event == "pull_request" else None,
            "github.ref": ref, "github.workflow": workflow}


class WorkflowPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full = FULL.read_text()
        cls.preflight = PREFLIGHT.read_text()
        full_concurrency = section(cls.full, "concurrency")
        cls.group = scalar(full_concurrency, "group", 2)
        cls.cancel = scalar(full_concurrency, "cancel-in-progress", 2)
        preflight_concurrency = section(cls.preflight, "concurrency")
        cls.preflight_group = scalar(preflight_concurrency, "group", 2)
        cls.preflight_cancel = scalar(preflight_concurrency, "cancel-in-progress", 2)

    def test_full_campaign_only_main_push_unfiltered_pr_and_manual(self):
        events = event_blocks(self.full)
        self.assertEqual(set(events), {"push", "pull_request", "workflow_dispatch"})
        self.assertEqual(push_branches(events["push"]), ["main"])
        self.assertEqual(re.findall(r"^    ([a-z_-]+):", events["push"], re.M), ["branches"])
        self.assertEqual(events["pull_request"].strip(), "")
        self.assertEqual(events["workflow_dispatch"].strip(), "")
        for forbidden in ("paths:", "paths-ignore:", "branches-ignore:", "pull_request_target:", "merge_group:"):
            self.assertNotIn(forbidden, section(self.full, "on"))

    def test_pr_updates_cancel_only_the_same_pr_acceptance(self):
        first = context("pull_request", run=101, pr=5, ref="refs/pull/5/merge")
        next_update = context("pull_request", run=102, pr=5, ref="refs/pull/5/merge")
        different_pr = context("pull_request", run=103, pr=6, ref="refs/pull/6/merge")
        self.assertEqual(expand(self.group, first), expand(self.group, next_update))
        self.assertNotEqual(expand(self.group, first), expand(self.group, different_pr))
        self.assertIs(expression(self.cancel, first), True)
        self.assertIs(expression(self.cancel, different_pr), True)

    def test_main_manual_and_preflight_do_not_cancel_acceptance_or_each_other(self):
        cases = [context("push", run=201, ref="refs/heads/main"),
                 context("push", run=202, ref="refs/heads/main"),
                 context("workflow_dispatch", run=301, ref="refs/heads/task/example"),
                 context("workflow_dispatch", run=302, ref="refs/heads/task/example"),
                 context("workflow_dispatch", run=303, ref="refs/heads/main"),
                 context("pull_request", run=401, ref="refs/pull/5/merge")]
        groups = [expand(self.group, case) for case in cases]
        self.assertEqual(len(groups), len(set(groups)))
        for case in cases[:-1]:
            self.assertIs(expression(self.cancel, case), False)
        branch = context("push", workflow="Lemma task branch preflight")
        preflight_group = expand(self.preflight_group, branch)
        self.assertNotIn(preflight_group, groups)
        self.assertIs(expression(self.preflight_cancel, branch), True)
        self.assertEqual(preflight_group, expand(self.preflight_group,
                         context("push", run=999, workflow="Lemma task branch preflight")))
        self.assertNotEqual(preflight_group, expand(self.preflight_group,
                            context("push", ref="refs/heads/task/another", workflow="Lemma task branch preflight")))

    def test_task_branch_preflight_is_bounded_host_only_feedback(self):
        events = event_blocks(self.preflight)
        self.assertEqual(set(events), {"push"})
        self.assertEqual(push_branches(events["push"]), ["task/**"])
        self.assertEqual(re.findall(r"^    ([a-z_-]+):", events["push"], re.M), ["branches"])
        self.assertEqual(re.findall(r"^  ([a-z0-9-]+):$", section(self.preflight, "jobs"), re.M), ["preflight"])
        job = section(section(self.preflight, "jobs"), "preflight", 2)
        self.assertEqual(scalar(job, "name", 4), "Task branch preflight")
        self.assertEqual(scalar(job, "runs-on", 4), "ubuntu-24.04")
        self.assertEqual(scalar(job, "timeout-minutes", 4), "5")
        self.assertIn("scripts/ci_preflight.py", job)
        self.assertIn("scripts/ci_source.py", job)
        self.assertIn("build/ci/preflight", job)
        self.assertIn("ref: ${{ github.sha }}", job)
        self.assertIn("persist-credentials: false", job)
        self.assertIn("if: ${{ always() }}", job)
        self.assertIn("if-no-files-found: error", job)
        self.assertEqual(re.findall(r"retention-days: (\d+)", job), ["14"])
        for forbidden in ("nix develop", "lake build", "qemu", "check-core0.sh", "check-foundation.sh"):
            self.assertNotIn(forbidden, job.lower())

    def test_no_cache_or_bypass_can_turn_old_or_missing_evidence_into_success(self):
        for source in (self.full, self.preflight):
            self.assertEqual(section(source, "permissions").strip(), "contents: read")
            self.assertNotRegex(source, re.compile(r"^    (?:needs|if):", re.M))
            for forbidden in ("continue-on-error", "secrets.", "actions/cache@", "magic-nix-cache",
                              "cachix/cachix-action", "download-artifact@", "|| true", "|| echo"):
                self.assertNotIn(forbidden, source)
            for action in re.findall(r"^\s+uses:\s+([^\s#]+)", source, re.M):
                self.assertRegex(action, r"^[^@\s]+@[0-9a-f]{40}$")

    def test_policy_parser_and_expression_evaluation_fail_closed(self):
        for malformed in ("on:\n  push:\non:\n  pull_request:\n", "name: no-events\n"):
            with self.assertRaises(ValueError):
                event_blocks(malformed)
        for malformed in ("${{ github.unknown }}", "${{ github.ref != 'x' }}",
                          "${{ github.ref || }}", "${{ contains(github.ref, 'main') }}"):
            with self.subTest(expression=malformed), self.assertRaises(ValueError):
                expression(malformed, context("push"))
        with self.assertRaises(ValueError):
            push_branches("    branches:\n")


if __name__ == "__main__":
    unittest.main()
