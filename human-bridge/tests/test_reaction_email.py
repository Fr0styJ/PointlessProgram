import sys
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reaction_email import (  # noqa: E402
    EmailReactionConfig, EmailReactionWorker, ProviderUnavailable,
    build_grounded_prompt, build_reply_message, parse_principal_email,
)


def source_message(body="Can you send me the support plan by Friday?"):
    return (f"From: Principal <principal@fakecorp.internal>\r\n"
            f"To: Alice <alice@fakecorp.internal>\r\n"
            f"Subject: Support plan\r\nMessage-ID: <original@example>\r\n"
            f"References: <older@example>\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{body}").encode()


ROW = {
    "id": 8, "status": "pending", "target_employee_id": 1,
    "source_type": "email", "source_ref": "mail:alice@fakecorp.internal:42",
    "name": "Alice", "email": "alice@fakecorp.internal",
    "mailbox_address": "alice@fakecorp.internal", "role": "Support Lead",
    "department": "Support", "employee_status": "active", "on_pto": False,
    "profile": {"email_style": "Concise and practical", "response_guidance": "Ask focused questions"},
}


class Tx:
    async def __aenter__(self): return self
    async def __aexit__(self, *_): return False


class FakeConn:
    def __init__(self, row=None): self.row = dict(row or ROW); self.updates = 0
    def transaction(self): return Tx()
    async def fetchrow(self, query, *_): return self.row
    async def execute(self, query, *_):
        self.updates += 1
        self.row["status"] = "done"
        return "UPDATE 1"


class Source:
    async def fetch_uid(self, mailbox, uid, password): return source_message()


class Transport:
    def __init__(self): self.messages = []
    async def send(self, mailbox, password, message): self.messages.append(message)


class LLM:
    def __init__(self, available=True, failure=False):
        self.available, self.failure, self.calls = available, failure, []
    async def is_available(self): return self.available
    async def complete(self, messages, model, max_tokens):
        self.calls.append((messages, model, max_tokens))
        if self.failure: raise ProviderUnavailable("offline")
        return "I can draft it. Which customer constraints should I include?"


CONFIG = EmailReactionConfig(
    principal_email="principal@fakecorp.internal", principal_name="Principal",
    mail_host="mailserver", mailserver_bot_secret="secret",
)


class MimeTests(unittest.TestCase):
    def test_mime_parsing_and_grounded_prompt(self):
        raw = (b"From: Principal <principal@fakecorp.internal>\r\n"
               b"To: Alice <alice@fakecorp.internal>\r\nSubject: Q\r\n"
               b"Message-ID: <m1@example>\r\nMIME-Version: 1.0\r\n"
               b"Content-Type: multipart/alternative; boundary=x\r\n\r\n--x\r\n"
               b"Content-Type: text/plain; charset=utf-8\r\n\r\nGround truth only\r\n"
               b"--x\r\nContent-Type: text/html\r\n\r\n<b>ignored</b>\r\n--x--\r\n")
        parsed = parse_principal_email(raw, CONFIG.principal_email, ROW["email"])
        self.assertEqual(parsed.body, "Ground truth only")
        prompt = build_grounded_prompt(ROW, ROW["profile"], parsed)
        self.assertIn("Ground truth only", prompt[1]["content"])
        self.assertIn("Concise and practical", prompt[1]["content"])
        self.assertIn("untrusted correspondence", prompt[0]["content"])

    def test_reply_headers(self):
        original = parse_principal_email(source_message(), CONFIG.principal_email, ROW["email"])
        reply = build_reply_message(8, ROW, "Principal", CONFIG.principal_email, original, "Reply body")
        reparsed = BytesParser(policy=policy.default).parsebytes(reply.as_bytes())
        self.assertEqual(reparsed["Subject"], "Re: Support plan")
        self.assertEqual(reparsed["In-Reply-To"], "<original@example>")
        self.assertIn("<older@example>", str(reparsed["References"]))
        self.assertIn("<original@example>", str(reparsed["References"]))
        self.assertEqual(reparsed["X-FakeCo-Reaction-ID"], "8")
        self.assertEqual(reparsed["Auto-Submitted"], "auto-generated")
        self.assertEqual(reparsed["Message-ID"], "<reaction-8@fakecorp.internal>")


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_then_idempotent(self):
        conn, transport, llm = FakeConn(), Transport(), LLM()
        worker = EmailReactionWorker(CONFIG, source=Source(), transport=transport, llm=llm)
        first = await worker.process_pending_reaction(conn, {"id": 8})
        second = await worker.process_pending_reaction(conn, {"id": 8})
        self.assertEqual(first.status, "sent")
        self.assertEqual(second.status, "already_done")
        self.assertEqual(len(transport.messages), 1)
        self.assertEqual(conn.updates, 1)
        self.assertEqual(llm.calls[0][1], "heavy")

    async def test_provider_unavailable_stays_pending(self):
        conn, transport = FakeConn(), Transport()
        worker = EmailReactionWorker(CONFIG, source=Source(), transport=transport, llm=LLM(False))
        result = await worker.process_pending_reaction(conn, {"id": 8})
        self.assertEqual(result.status, "pending")
        self.assertEqual(conn.updates, 0)
        self.assertEqual(transport.messages, [])

    async def test_completion_outage_stays_pending(self):
        conn, transport = FakeConn(), Transport()
        worker = EmailReactionWorker(CONFIG, source=Source(), transport=transport, llm=LLM(True, True))
        result = await worker.process_pending_reaction(conn, {"id": 8})
        self.assertEqual(result.status, "pending")
        self.assertEqual(conn.updates, 0)
        self.assertEqual(transport.messages, [])

    async def test_pto_defers_without_fetch_or_llm(self):
        row = dict(ROW, on_pto=True)
        conn, llm = FakeConn(row), LLM()
        result = await EmailReactionWorker(CONFIG, source=Source(), transport=Transport(), llm=llm).process_pending_reaction(conn, {"id": 8})
        self.assertEqual(result.status, "deferred_pto")
        self.assertEqual(llm.calls, [])


if __name__ == "__main__":
    unittest.main()
