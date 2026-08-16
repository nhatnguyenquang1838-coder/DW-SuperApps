import unittest

from taskcontroller.audit.guardrails import (
    check_terminal,
    check_duplicate_root,
    check_authority,
    check_sha_format,
)


class GuardrailTests(unittest.TestCase):
    def test_terminal_blocked(self) -> None:
        for s in ("COMPLETED", "FAILED", "CANCELLED"):
            r = check_terminal(s)
            self.assertTrue(r.blocked)
            self.assertEqual(r.reason, "run_terminal")

    def test_non_terminal_pass(self) -> None:
        for s in ("RUNNING", "PAUSED", "BLOCKED", "CREATED", "PLANNED"):
            r = check_terminal(s)
            self.assertFalse(r.blocked)

    def test_duplicate_root_blocked(self) -> None:
        r = check_duplicate_root("root.A", "root.B")
        self.assertTrue(r.blocked)
        self.assertEqual(r.reason, "duplicate_root")

    def test_same_root_pass(self) -> None:
        r = check_duplicate_root("root.A", "root.A")
        self.assertFalse(r.blocked)

    def test_no_existing_root_pass(self) -> None:
        r = check_duplicate_root(None, "root.A")
        self.assertFalse(r.blocked)

    def test_authority_mismatch(self) -> None:
        r = check_authority("auth-1", "auth-2")
        self.assertTrue(r.blocked)
        self.assertEqual(r.reason, "authority_mismatch")

    def test_authority_match(self) -> None:
        r = check_authority("auth-1", "auth-1")
        self.assertFalse(r.blocked)

    def test_sha_format_valid(self) -> None:
        r = check_sha_format("a" * 40)
        self.assertFalse(r.blocked)
        self.assertEqual(r.reason, "")

    def test_sha_format_invalid_length(self) -> None:
        for v in ("too-short", "a" * 39, "a" * 41, ""):
            r = check_sha_format(v)
            self.assertTrue(r.blocked)
            self.assertIn("invalid_sha_format", r.reason)

    def test_sha_format_invalid_hex(self) -> None:
        r = check_sha_format("g" * 40)
        self.assertTrue(r.blocked)
        self.assertIn("invalid_sha_hex", r.reason)


if __name__ == "__main__":
    unittest.main()
