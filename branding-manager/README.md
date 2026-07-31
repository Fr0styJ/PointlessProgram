# branding-manager/

**Populated by:** Phase 30 — Branding & asset manager

This directory will contain the Branding/Asset Manager service: manages employee avatar
images and the Mattermost custom-emoji pack (spec §17).

**Responsibilities:**
- Asset library: maps `employee_id → avatar_asset_id`.
- Per-employee avatar picker, plus bulk actions:
  - Randomize all
  - Apply one set to everyone selected
  - Reset to defaults
- "Apply" action pushes selected images through each appliance's real avatar-upload API.
  Only the selection/bulk-push logic is custom — rendering is entirely the real appliance's.

**Appliance avatar APIs used:**
- Mattermost: profile image upload API
- Zammad: user image/avatar API
- Wiki.js: user avatar API

**First-boot:** uploads themed custom-emoji pack to Mattermost (real built-in feature) and
sets initial employee avatars.

**Dashboard tab:** Branding tab (§25).

**Dependencies:** Phases 5 (Mattermost), 6 (Zammad), 7 (Wiki.js), 14 (roster).
