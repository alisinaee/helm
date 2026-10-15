"""Secret scrubbing vectors (HEAD-SPEC H2): every rule masks its sample, and task ids, refs, shas and ordinary words pass."""

import unittest

from roadmap.core.secrets import scrub

# (input, expected output). Each row exercises one rule of section 7.
MASKED = (
    ("sk-ant-api03-AbCdEf0123456789xyz", "[secret]"),
    ("key sk-proj-abcdef1234567890ABCD here", "key [secret] here"),
    ("ghp_1234567890abcdefghijklmnopqrstuvwxyz", "[secret]"),
    ("github_pat_11ABCDEFG0123456789_abcdefghij", "[secret]"),
    ("xoxb-1234567890-abcdefghij", "[secret]"),
    ("AKIAIOSFODNN7EXAMPLE", "[secret]"),
    ("AIzaSyD-abcdefghijklmnopqrstuvwxyz12345", "[secret]"),
    ("jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.abc123DEF done", "jwt [secret] done"),
    ("-----BEGIN RSA PRIVATE KEY-----\nMIIB\n-----END RSA PRIVATE KEY-----", "[secret]"),
    ("-----BEGIN PRIVATE KEY-----\nMIIBVQIBADANBgkq", "[secret]"),
    ("Authorization: Bearer abc.def-123_xyz", "Authorization: Bearer [secret]"),
    ("bearer abc123token", "bearer [secret]"),
    ("password=hunter2 next", "password=[secret] next"),
    ('api_key: "abc123"', 'api_key: "[secret]"'),
    ("secret=s3cr3tvalue&x=1", "secret=[secret]&x=1"),
    ("token=abc123 and TOKEN: xyz", "token=[secret] and TOKEN: [secret]"),
    ("https://ali:hunter2@github.com/x/y", "https://[secret]@github.com/x/y"),
    ("http://h/?k=abcdef12 ok", "http://h/?k=[secret] ok"),
    ("mail ali.b@example.com now", "mail [email] now"),
    ("card 4111 1111 1111 1111 ok", "card [number] ok"),
    ("card 4111111111111111 ok", "card [number] ok"),
    ("/Users/ali/Works/roadmap-board/docs/x.md", "~/Works/roadmap-board/docs/x.md"),
    ("0123456789abcdef0123456789abcdef", "[secret]"),
    ("Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MGFiY2RlZg==", "[secret]"),
    ("ok sk-abcdefghijklmnopqrstu and ali@x.io", "ok [secret] and [email]"),
    ("key sk-abcdefghijklmnopqrstu", "key [secret]"),
    ("ab12cd34ef56gh78ij90kl12mn34op56 ok", "[secret] ok"),
    ("", ""),
    (None, ""),
)

# Text that must come back unchanged: task ids, refs, shas, timestamps, paths and ordinary words.
UNCHANGED = (
    "R7.31",
    "P1.2 done, H2 in progress",
    "Task: R7.31",
    "Job: j104 started",
    "ids: P1.12, R7.31.2, j104, H2",
    "commit fb4eff3 and 0a1b2c3d",
    "e4d66ae1f0c2b3a4d5e6f708192a3b4c5d6e7f80",
    '"sha": "e4d66ae1f0c2b3a4d5e6f708192a3b4c5d6e7f80"',
    '"tokensK": 40',
    "keyboard shortcut",
    "monkey=3",
    "ask=yes",
    "2026-10-15T12:00:00Z",
    "fixtures/demo/alpha/docs/activity.jsonl",
    "docs/HEAD-SPEC.md#h2",
    "roadmap-board",
    "internationalization",
    "1760000000",
    "8000 chars, 100 summary, 160 note",
    "rb:roadmap-board/task/P1.2",
)


class ScrubVectorTests(unittest.TestCase):
    def test_masked_vectors(self):
        for text, expected in MASKED:
            with self.subTest(text=text):
                self.assertEqual(scrub(text), expected)

    def test_no_false_hits(self):
        for text in UNCHANGED:
            with self.subTest(text=text):
                self.assertEqual(scrub(text), text)

    def test_vector_count(self):
        self.assertGreaterEqual(len(MASKED) + len(UNCHANGED), 30)

    def test_idempotent(self):
        for text, _ in MASKED:
            once = scrub(text)
            with self.subTest(text=text):
                self.assertEqual(scrub(once), once)

    def test_non_string_input(self):
        self.assertEqual(scrub(42), "42")


if __name__ == "__main__":
    unittest.main()
