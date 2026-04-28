from __future__ import annotations

import unittest

from zcore.utils.privacy import redact_text, sanitize_transcript


class PrivacyTests(unittest.TestCase):
    def test_redact_text_redacts_api_key(self):
        text = "api_key=sk-abc123def456ghi789xyz"

        self.assertEqual(redact_text(text), "[REDACTED]")

    def test_redact_text_redacts_ipv4_address(self):
        self.assertEqual(redact_text("connect 192.168.1.10 now"), "connect [REDACTED] now")

    def test_redact_text_redacts_email_address(self):
        self.assertEqual(redact_text("send to user@example.com"), "send to [REDACTED]")

    def test_redact_text_redacts_chinese_mobile_number(self):
        self.assertEqual(redact_text("call 13800138000"), "call [REDACTED]")

    def test_redact_text_redacts_bearer_token(self):
        self.assertEqual(redact_text("auth Bearer abc-123._~+/=="), "auth [REDACTED]")

    def test_redact_text_redacts_mixed_secret_and_email(self):
        text = "Send to sk-abc123def456ghi789 at user@example.com"

        self.assertEqual(redact_text(text), "Send to [REDACTED] at [REDACTED]")

    def test_sanitize_transcript_redacts_message_contents(self):
        messages = [
            {"role": "user", "content": "email user@example.com"},
            {"role": "assistant", "content": "ip 10.0.0.1"},
        ]

        sanitized = sanitize_transcript(messages)

        self.assertEqual(sanitized[0]["content"], "email [REDACTED]")
        self.assertEqual(sanitized[1]["content"], "ip [REDACTED]")

    def test_sanitize_transcript_does_not_mutate_original_input(self):
        messages = [{"role": "user", "content": "phone 13800138000"}]

        sanitized = sanitize_transcript(messages)

        self.assertIsNot(sanitized, messages)
        self.assertIsNot(sanitized[0], messages[0])
        self.assertEqual(messages[0]["content"], "phone 13800138000")
        self.assertEqual(sanitized[0]["content"], "phone [REDACTED]")
