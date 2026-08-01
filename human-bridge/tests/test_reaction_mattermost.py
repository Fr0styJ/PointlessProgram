import importlib.util
import pathlib
import sys
import unittest


MODULE = pathlib.Path(__file__).parents[1] / "reaction_mattermost.py"
spec = importlib.util.spec_from_file_location("reaction_mattermost", MODULE)
reaction_mattermost = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reaction_mattermost
spec.loader.exec_module(reaction_mattermost)

from reaction_mattermost import (
    configured_human_email,
    first_poll_params,
    is_principal_post,
    merge_channels,
    target_employee_id,
)


EMPLOYEE_IDS = {"bob-mm": 7, "alice-mm": 8}
USERNAMES = {"bob_martinez": 7, "alice_chen": 8}


def target(kind, message="", members=()):
    return target_employee_id(
        channel_type=kind,
        message=message,
        principal_id="principal",
        member_ids=members,
        employees_by_mattermost_id=EMPLOYEE_IDS,
        employees_by_username=USERNAMES,
    )


class MattermostDetectionTests(unittest.TestCase):
    def test_human_identity_is_appliance_specific_and_defaults_to_admin(self):
        self.assertEqual(
            configured_human_email("human@example.test", "admin@example.test"),
            "human@example.test",
        )
        self.assertEqual(
            configured_human_email("", "ADMIN@example.test"), "admin@example.test"
        )
        self.assertEqual(configured_human_email("", ""), "")

    def test_dm_targets_the_other_employee_without_a_mention(self):
        self.assertEqual(target("D", "what do you do here bob", ["principal", "bob-mm"]), 7)

    def test_dm_with_no_employee_or_ambiguous_members_is_ignored(self):
        self.assertIsNone(target("D", members=["principal"]))
        self.assertIsNone(target("D", members=["principal", "bob-mm", "alice-mm"]))

    def test_group_and_team_channels_require_an_explicit_mention(self):
        self.assertIsNone(target("G", "hello everyone", ["principal", "bob-mm"]))
        self.assertEqual(target("G", "hello @bob_martinez", ["principal", "bob-mm"]), 7)
        self.assertIsNone(target("O", "hello bob"))
        self.assertEqual(target("P", "hello @alice_chen"), 8)

    def test_each_channel_is_deduplicated_but_retains_an_independent_id(self):
        channels = merge_channels(
            [{"id": "town", "type": "O"}, {"id": "dm-bob", "type": "D"}],
            [{"id": "dm-bob", "type": "D"}, {"id": "dm-alice", "type": "D"}],
        )
        self.assertEqual(
            {channel["id"] for channel in channels}, {"town", "dm-bob", "dm-alice"}
        )

    def test_first_poll_is_bounded_then_cursor_prevents_duplicate_replay(self):
        self.assertEqual(
            first_poll_params(None, now_ms=1_000_000_000, backfill_hours=24, limit=10),
            {"page": 0, "per_page": 10, "since": 913_600_000},
        )
        self.assertEqual(
            first_poll_params("9876", now_ms=1_000_000_000),
            {"page": 0, "per_page": 50, "since": 9876},
        )

    def test_only_principal_posts_are_candidates_excluding_bots_and_self_responses(self):
        self.assertTrue(is_principal_post({"user_id": "principal"}, "principal"))
        self.assertFalse(is_principal_post({"user_id": "bob-mm"}, "principal"))
        self.assertFalse(is_principal_post({"user_id": "bot"}, "principal"))
        self.assertFalse(is_principal_post({"user_id": ""}, "principal"))
