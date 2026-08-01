import importlib.util
import pathlib
import sys
import unittest

import httpx

MODULE = pathlib.Path(__file__).parents[1] / "reaction_zammad.py"
spec = importlib.util.spec_from_file_location("reaction_zammad", MODULE)
rz = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = rz
spec.loader.exec_module(rz)


class FakeConn:
    def __init__(self, row, pto=False):
        self.row, self.pto, self.updates = row, pto, []
    async def fetchval(self, query, *args):
        return True if "advisory" in query else self.pto
    async def fetchrow(self, query, *args): return self.row
    async def execute(self, query, *args):
        self.updates.append((query, args)); return "UPDATE 1"


def row(**changes):
    value = {"reaction_id": 12, "reaction_status": "pending", "source_type": "ticket",
             "source_ref": "zammad:77", "employee_id": 4, "name": "David Chen",
             "email": "david@fakecorp.internal", "department": "Engineering",
             "role": "QA Engineer", "zammad_agent_id": "22", "employee_status": "active",
             "personality_profile": {"communication_style": "Precise and calm"}}
    value.update(changes); return value


class Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = rz.ZammadReactionConfig("http://zammad", "admin", "principal@fakecorp.internal",
                                               "http://litellm", "key")

    def client(self, existing=False, principal=True, owner="22"):
        async def handler(request):
            path = request.url.path
            if path.endswith("/ticket_articles/77"):
                return httpx.Response(200, json={"id": 77, "ticket_id": 9,
                    "created_by_id": 2 if principal else 3, "body": "Please investigate the outage."})
            if path.endswith("/tickets/9"):
                return httpx.Response(200, json={"id": 9, "number": "1009", "title": "Outage", "owner_id": owner})
            if path.endswith("/users/search"):
                return httpx.Response(200, json=[{"id": 2, "email": "principal@fakecorp.internal"}])
            if path.endswith("/ticket_articles/by_ticket/9"):
                articles = [{"id": 88, "body": "<p>done</p>",
                             "preferences": {"fakeco_reaction_id": "fakeco-reaction-12"}}] if existing else []
                return httpx.Response(200, json=articles)
            raise AssertionError(f"unexpected {request.method} {request.url}")
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def test_grounded_personality_reply_and_done_after_delivery(self):
        conn, captured = FakeConn(row()), {}
        async def generate(messages):
            captured["prompt"] = "\n".join(m["content"] for m in messages)
            return "I will investigate with the available evidence."
        async def post(employee, ticket, body, marker):
            captured.update(employee=employee, ticket=ticket, body=body, marker=marker)
            self.assertEqual(conn.updates, [])
            return "91"
        async with self.client() as client:
            result = await rz.process_zammad_reaction(conn, 12, self.config,
                http_client=client, generator=generate, poster=post)
        self.assertEqual(result.article_id, "91")
        self.assertIn("Please investigate the outage", captured["prompt"])
        self.assertIn("Precise and calm", captured["prompt"])
        self.assertEqual(captured["marker"], "fakeco-reaction-12")
        self.assertEqual(len(conn.updates), 1)

    async def test_appliance_marker_prevents_duplicate_and_repairs_db(self):
        conn, generated = FakeConn(row()), False
        async def generate(_):
            nonlocal generated; generated = True; return "no"
        async with self.client(existing=True) as client:
            result = await rz.process_zammad_reaction(conn, 12, self.config,
                http_client=client, generator=generate)
        self.assertFalse(generated)
        self.assertEqual(result.reason, "existing_article")
        self.assertEqual(result.article_id, "88")
        self.assertEqual(len(conn.updates), 1)

    async def test_provider_down_and_pto_stay_pending(self):
        conn = FakeConn(row())
        async def unavailable(_): raise rz.ProviderUnavailable("stopped")
        async with self.client() as client:
            result = await rz.process_zammad_reaction(conn, 12, self.config,
                http_client=client, generator=unavailable)
        self.assertEqual(result.reason, "provider_unavailable")
        self.assertEqual(conn.updates, [])
        conn = FakeConn(row(), pto=True)
        async with self.client() as client:
            result = await rz.process_zammad_reaction(conn, 12, self.config, http_client=client)
        self.assertEqual(result.reason, "employee_on_pto")

    async def test_rejects_non_principal_and_wrong_owner(self):
        for principal, owner, expected in ((False, "22", "not_principal_article"),
                                            (True, "99", "employee_not_ticket_owner")):
            conn = FakeConn(row())
            async with self.client(principal=principal, owner=owner) as client:
                result = await rz.process_zammad_reaction(conn, 12, self.config, http_client=client)
            self.assertEqual(result.reason, expected)
            self.assertEqual(conn.updates, [])

    def test_ref_and_html_marker(self):
        self.assertEqual(rz.parse_source_ref("zammad:42"), 42)
        with self.assertRaises(rz.UnsafeTicketSource): rz.parse_source_ref("zammad:nope")
        rendered = rz._article_html("First <safe>\n\nSecond", "fakeco-reaction-4")
        self.assertIn("&lt;safe&gt;", rendered)
        self.assertIn("<!-- fakeco-reaction-4 -->", rendered)


if __name__ == "__main__": unittest.main()
