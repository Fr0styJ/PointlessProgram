import importlib.util
import pathlib
import sys
import unittest

import httpx

MODULE = pathlib.Path(__file__).parents[1] / "reaction_wikijs.py"
spec = importlib.util.spec_from_file_location("reaction_wikijs", MODULE)
wiki = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = wiki
spec.loader.exec_module(wiki)


class FakeConn:
    def __init__(self, row, pto=False): self.row, self.pto, self.updates = row, pto, []
    async def fetchrow(self, *_): return self.row
    async def fetchval(self, query, *_): return self.pto if "pto_calendar" in query else True
    async def execute(self, query, *args): self.updates.append((query, args)); return "UPDATE 1"


def reaction_row(**changes):
    value = {"reaction_id": 8, "reaction_status": "pending", "source_type": "wiki",
             "source_ref": "wikijs:12:2026-08-01T10:00:00.000Z", "short_summary": "Review",
             "employee_id": 2, "name": "Dana Singh", "email": "dana@fakecorp.internal",
             "department": "Operations", "role": "Operations Lead", "wiki_user_id": 22,
             "employee_status": "active", "personality_profile": {"wiki_style": "methodical"}}
    value.update(changes); return value


class WikiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = wiki.WikiReactionConfig("http://wikijs:3000", "token", 1,
                                              "http://litellm:4000", "key")
        self.updated = None

    def client(self, *, content="Principal request", author=1,
               updated="2026-08-01T10:00:00.000Z", update_ok=True):
        async def handler(request):
            payload = request.read().decode()
            import json
            body = json.loads(payload)
            if "query($id" in body["query"]:
                return httpx.Response(200, json={"data": {"pages": {"single": {
                    "id": 12, "path": "ops/review", "title": "Review", "description": "",
                    "content": content, "editor": "markdown", "isPublished": True,
                    "isPrivate": False, "locale": "en", "authorId": author,
                    "updatedAt": updated, "tags": [{"tag": "emp-2"}]}}}})
            if "mutation(" in body["query"]:
                self.updated = body["variables"]
                return httpx.Response(200, json={"data": {"pages": {"update": {
                    "responseResult": {"succeeded": update_ok, "message": "ok"}}}}})
            raise AssertionError(body["query"])
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def test_grounded_publish_and_attribution(self):
        conn, seen = FakeConn(reaction_row()), {}
        async def generate(messages): seen["prompt"] = messages; return "I recommend a staged review."
        async with self.client() as client:
            result = await wiki.process_wikijs_reaction(conn, 8, self.config,
                                                        http_client=client, generator=generate)
        prompt = " ".join(m["content"] for m in seen["prompt"])
        self.assertIn("Principal request", prompt); self.assertIn("methodical", prompt)
        self.assertIn("Follow-up from Dana Singh", self.updated["content"])
        self.assertIn("fakeco-reaction-8", self.updated["content"])
        self.assertEqual(result.status, "done"); self.assertEqual(len(conn.updates), 2)
        self.assertIn("human_bridge_cursors", conn.updates[0][0])

    async def test_existing_marker_is_idempotent(self):
        conn, called = FakeConn(reaction_row()), False
        async def generate(_):
            nonlocal called; called = True; return "no"
        async with self.client(content="x\n<!-- fakeco-reaction-8 -->") as client:
            result = await wiki.process_wikijs_reaction(conn, 8, self.config,
                                                        http_client=client, generator=generate)
        self.assertFalse(called); self.assertEqual(result.reason, "existing_follow_up")
        self.assertEqual(len(conn.updates), 1)

    async def test_provider_down_keeps_pending(self):
        conn = FakeConn(reaction_row())
        async def generate(_): raise wiki.ProviderUnavailable("stopped")
        async with self.client() as client:
            result = await wiki.process_wikijs_reaction(conn, 8, self.config,
                                                        http_client=client, generator=generate)
        self.assertEqual(result.reason, "provider_unavailable"); self.assertFalse(conn.updates)

    async def test_pto_and_changed_revision_defer(self):
        conn = FakeConn(reaction_row(), pto=True)
        async with self.client() as client:
            result = await wiki.process_wikijs_reaction(conn, 8, self.config, http_client=client)
        self.assertEqual(result.reason, "employee_on_pto")
        conn = FakeConn(reaction_row())
        async with self.client(updated="later") as client:
            result = await wiki.process_wikijs_reaction(conn, 8, self.config, http_client=client)
        self.assertEqual(result.reason, "source_revision_changed"); self.assertFalse(conn.updates)

    async def test_non_principal_and_failed_delivery_never_mark_done(self):
        conn = FakeConn(reaction_row())
        async with self.client(author=9) as client:
            result = await wiki.process_wikijs_reaction(conn, 8, self.config, http_client=client)
        self.assertEqual(result.reason, "not_principal_authored"); self.assertFalse(conn.updates)
        conn = FakeConn(reaction_row())
        async def generate(_): return "response"
        async with self.client(update_ok=False) as client:
            with self.assertRaises(RuntimeError):
                await wiki.process_wikijs_reaction(conn, 8, self.config,
                                                   http_client=client, generator=generate)
        self.assertFalse(conn.updates)

    async def test_missing_employee_tag_defers(self):
        conn = FakeConn(reaction_row())
        async def handler(request):
            return httpx.Response(200, json={"data": {"pages": {"single": {
                "id": 12, "path": "ops/review", "title": "Review", "description": "",
                "content": "Principal request", "editor": "markdown", "isPublished": True,
                "isPrivate": False, "locale": "en", "authorId": 1,
                "updatedAt": "2026-08-01T10:00:00.000Z", "tags": []}}}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await wiki.process_wikijs_reaction(conn, 8, self.config, http_client=client)
        self.assertEqual(result.reason, "target_tag_missing"); self.assertFalse(conn.updates)


if __name__ == "__main__": unittest.main()
