import importlib.util
import pathlib
import sys
import unittest

import httpx


MODULE = pathlib.Path(__file__).parents[1] / "reaction_chat.py"
spec = importlib.util.spec_from_file_location("reaction_chat", MODULE)
reaction_chat = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reaction_chat
spec.loader.exec_module(reaction_chat)


class FakeConn:
    def __init__(self, row, *, pto=False, locked=True):
        self.row = row
        self.pto = pto
        self.locked = locked
        self.updates = []

    async def fetchval(self, query, *args):
        if "pg_try_advisory" in query:
            return self.locked
        if "pto_calendar" in query:
            return self.pto
        raise AssertionError(query)

    async def fetchrow(self, query, *args):
        return self.row

    async def execute(self, query, *args):
        self.updates.append((query, args))
        return "UPDATE 1"


def row(**overrides):
    base = {
        "reaction_id": 9, "reaction_status": "pending", "source_type": "chat",
        "source_ref": "mattermost:principal-post", "short_summary": "Please review launch risks",
        "created_at": None, "employee_id": 4, "name": "David Chen",
        "email": "david.chen@fakecorp.internal", "department": "Engineering",
        "role": "QA Engineer", "mattermost_id": "employee-mm-id",
        "employee_status": "active", "personality": "Thorough",
        "personality_profile": {"chat_style": "Direct and evidence-led", "flaws": ["pessimistic"]},
    }
    base.update(overrides)
    return base


class ChatReactionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = reaction_chat.ChatReactionConfig(
            "http://mattermost", "admin-token", "http://litellm", "llm-key"
        )

    def client(self, *, existing=None):
        async def handler(request):
            if request.method == "GET" and request.url.path == "/api/v4/posts/principal-post":
                return httpx.Response(200, json={"id": "principal-post", "root_id": "",
                    "channel_id": "channel-1", "user_id": "principal-id",
                    "message": "Please review launch risks before Friday."})
            if request.method == "GET" and request.url.path.endswith("/thread"):
                posts = {} if not existing else {existing["id"]: existing}
                return httpx.Response(200, json={"posts": posts, "order": list(posts)})
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def test_prompt_is_grounded_and_persona_rich(self):
        conn = FakeConn(row())
        captured = {}
        async def generate(messages):
            captured["messages"] = messages
            return "I’ll review the risks and report back."
        async def post(employee, original, message, marker):
            captured.update(employee=employee, original=original, message=message, marker=marker)
            return "reply-1"
        async with self.client() as client:
            result = await reaction_chat.process_chat_reaction(
                conn, 9, self.config, http_client=client, generator=generate, poster=post)
        prompt = "\n".join(x["content"] for x in captured["messages"])
        self.assertIn("Please review launch risks before Friday.", prompt)
        self.assertIn("Direct and evidence-led", prompt)
        self.assertIn("do not invent", prompt)
        self.assertEqual(captured["original"]["id"], "principal-post")
        self.assertEqual(captured["marker"], "fakeco-reaction-9")
        self.assertEqual(result.post_id, "reply-1")

    async def test_thread_marker_makes_retry_idempotent(self):
        existing = {"id": "reply-existing", "props": {"fakeco_reaction_id": "fakeco-reaction-9"}}
        called = False
        async def generate(_):
            nonlocal called
            called = True
            return "must not run"
        conn = FakeConn(row())
        async with self.client(existing=existing) as client:
            result = await reaction_chat.process_chat_reaction(
                conn, 9, self.config, http_client=client, generator=generate)
        self.assertFalse(called)
        self.assertEqual(result.post_id, "reply-existing")
        self.assertEqual(result.reason, "existing_post")
        self.assertEqual(len(conn.updates), 1)

    async def test_done_only_after_successful_post(self):
        conn = FakeConn(row())
        async def generate(_): return "Grounded response"
        async def post(*_): return "reply-2"
        async with self.client() as client:
            result = await reaction_chat.process_chat_reaction(
                conn, 9, self.config, http_client=client, generator=generate, poster=post)
        self.assertEqual(result.status, "done")
        self.assertEqual(len(conn.updates), 1)
        self.assertIn("status = 'done'", conn.updates[0][0])

    async def test_provider_unavailable_keeps_pending(self):
        conn = FakeConn(row())
        async def generate(_):
            raise reaction_chat.ProviderUnavailable("proxy stopped")
        async with self.client() as client:
            result = await reaction_chat.process_chat_reaction(
                conn, 9, self.config, http_client=client, generator=generate)
        self.assertEqual(result.status, "pending")
        self.assertEqual(result.reason, "provider_unavailable")
        self.assertEqual(conn.updates, [])

    async def test_employee_own_post_and_pto_stay_pending(self):
        conn = FakeConn(row(), pto=True)
        async with self.client() as client:
            result = await reaction_chat.process_chat_reaction(conn, 9, self.config, http_client=client)
        self.assertEqual(result.reason, "employee_on_pto")
        self.assertEqual(conn.updates, [])


if __name__ == "__main__":
    unittest.main()
