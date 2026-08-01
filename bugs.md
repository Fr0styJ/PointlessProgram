# bugs.md — Outstanding issues

Tracks currently-open bugs and gaps as of 2026-08-01. Fixed issues are NOT listed here — see
`BUILD_LOG.md`'s "## LOG (newest first)" section for the full history of what's already been
found and resolved. This file is for what's still actually broken or unbuilt.

---

## Bugs (confirmed, reproducible)

### 1. Nextcloud deliverable fulfillment fails for any department without a pre-existing folder

**Where**: `human-bridge/main.py`, `_NextcloudClient.put_file()` (added alongside the
WordPress/Nextcloud narrative-driven content feature, migration `012_deliverable_action_items.sql`).

**Symptom**: The client's docstring claims "Nextcloud WebDAV auto-creates missing parents on
PUT" — this is false. A real `PUT` to `FakeCo-Docs/Sales/...` failed with a genuine `404 Not
Found` because that department subfolder doesn't exist yet (confirmed live,
`action_item.id=156`). The one successful test case (`FakeCo-Docs/Engineering/...`) only worked
because that folder happened to already exist from earlier manual testing — not because the code
creates it.

**Impact**: any department other than the ones with a pre-existing `FakeCo-Docs/{department}/`
folder will permanently fail every Nextcloud deliverable. The fulfillment loop has no backoff or
give-up limit (see bug 3 below), so a stuck item will retry every 30 seconds forever, spamming
`ERROR` log lines indefinitely.

**Fix direction**: before the `PUT`, issue a WebDAV `MKCOL` for each path segment that doesn't
exist yet (Nextcloud requires each directory in the path to be explicitly created — it will not
auto-create a nested path from a single `PUT`), or use Nextcloud's OCS API to ensure the
department folder exists once at startup / on first use per department.

### 2. Deliverable content sometimes comes back empty (title/metadata present, body empty)

**Where**: `human-bridge/main.py`, `_generate_content_for_action_item()` /
`_fulfill_one_deliverable()`.

**Symptom**: both of the two deliverables created during the original build-and-verify pass for
this feature (`action_item.id=153` → WordPress post id 6, and `id=154` → the Nextcloud file) came
back with a real title and correct metadata, but a **completely empty body** — an empty post, and
a file containing only its YAML front matter with nothing after it. A fresh, independently-run
test (`action_item.id=155`) worked correctly with real multi-paragraph generated content, so this
isn't a fundamental code bug — but 2 of 2 of the original samples had this problem, which is a
higher failure rate than ordinary LLM flakiness would suggest.

**Impact**: deliverables can silently "succeed" (marked `done`, `deliverable_url` populated) while
containing no actual content — worse than failing loudly, since there's no automatic signal that
something's wrong.

**Fix direction**: add a post-generation sanity check in `_generate_content_for_action_item()` —
if `content` comes back empty or under some minimum length, treat it the same as a JSON parse
failure (retry once, matching the pattern already used elsewhere in this codebase for LLM
truncation issues — see `meeting-simulator/main.py`'s `_try_parse()`/retry logic from the
2026-08-01T04:12 fix) rather than accepting and publishing an empty result.

### 3. Deliverable fulfillment loop has no backoff or give-up limit on repeated failure

**Where**: `human-bridge/main.py`, `_deliverable_fulfillment_loop()`.

**Symptom**: on any failure (LLM error, appliance call error), the action_item row is left
`status='open'` with `deliverable_url` still `NULL`, and the loop retries it again on the very
next 30-second poll — forever, with no cap on attempts and no increasing delay.

**Impact**: a permanently-broken item (e.g. bug 1 above, a department whose folder will never
exist without a code fix) retries indefinitely, continuously spamming `ERROR` log lines and
wasting an LLM call every 30 seconds.

**Fix direction**: add an `attempts` counter (or reuse the shape of Phase 27's `pending_actions`
retry-queue pattern in `orchestrator/main.py`, which already solves this exact problem — wall-clock
`next_retry_at`, capped attempts, a `failed` terminal status) rather than retrying unconditionally
forever.

---

## Known feature gaps (not bugs — deliberately unbuilt or deferred)

### 4. Phase 24 — pay negotiation / performance-review-driven pay cuts

Not started. `meeting-simulator` has a `pay_negotiation` meeting-type schema/attendee-selection
stub (spec §6.4) but nothing anywhere actually calls it. The dashboard's Payroll tab deliberately
blocks the pay-cut path (both client- and server-side) with a "Phase 24 not yet built" message
rather than applying a cut directly, which would violate the spec's requirement that cuts always
go through a negotiation meeting.

### 5. Phase 32 — simulation speed slider, full integration

Deliberately DEFERRED per explicit user sign-off (2026-07-31). Full design preserved in
`Future_Plans.md` for whenever it's picked back up. The dashboard's Simulation tab ships the
slider UI visibly present but disabled, labeled "Coming Soon."

### 6. Phase 38 — hardening (in progress, several items still open)

- Top-level `README.md` does not exist yet (deployment steps, resource footprint, troubleshooting,
  a tab-by-tab dashboard walkthrough).
- `.env.example` completeness hasn't had a full audit pass against every service's actual required
  vars (spot gaps have been found and fixed reactively — e.g. the Zammad/WordPress credential gap
  — rather than via one systematic pass).
- Dashboard-wide graceful error-state handling (what each tab shows when its backing service is
  down) hasn't been explicitly built/tested — only implicitly covered by whatever each tab's fetch
  code already does on a failed request.
- First-boot automation (unattended roster/Principal provisioning, Akaunting chart-of-accounts,
  initial branding pass all running without manual steps) not yet built/verified end-to-end.

---

## Notes on content policy for the WordPress/Nextcloud feature

Per explicit user requirement, deliverables must only ever be created when a specific narrative
trigger calls for one (a flagged `action_items.deliverable_type`, set by the LLM during a real
meeting outcome) — never on a periodic or random schedule. This is correctly implemented: the
30-second poll loop only processes rows that already have `deliverable_type` set by
meeting-simulator; it does not generate new triggers itself. This design constraint is satisfied
even though bugs 1-3 above remain open.
