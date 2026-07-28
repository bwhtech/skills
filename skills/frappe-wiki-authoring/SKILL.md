---
name: frappe-wiki-authoring
description: Frappe Wiki authoring and publishing through frappectl change requests. Use when the user wants to add, edit, restructure, or delete a wiki page; names a wiki space ("the Buzz wiki", "our handbook", "our docs"); or mentions Wiki Change Request, wiki CR, or apply_cr_operations.
---

# Frappe Wiki authoring via frappectl

A change request is a **branch**: author content into it, then walk it through
submit → approve → merge to publish. These are the whitelisted APIs the `/wiki-app` SPA calls.

Git intuition carries almost everywhere here — with one inversion, flagged at
[Merge conflicts](#merge-conflicts).

Requires Wiki v3 (the `frappe_wiki` module: Wiki Document, Wiki Change Request, Wiki
Revision). The legacy v2 `Wiki Page` doctypes have no change-request flow.

`reference/api.md` holds full signatures, every operation's fields, the status machine, and
the permission model.

## Setup

Site access is preconfigured — pass `-s <profile>` and nothing else. When the user names a
site, use that profile; with several profiles and no name, ask. An auth error is the user's
to fix: surface it rather than re-authenticating or editing `FRAPPE_*` env vars.

```bash
export CR=wiki.frappe_wiki.doctype.wiki_change_request.wiki_change_request
export SITE="<profile>"
```

## Step 1 — Resolve the space

"The Buzz wiki" is not an identifier. Turn it into a **docname** before anything else:

```bash
frappectl -s "$SITE" doc list "Wiki Space" \
  --fields name,space_name,route,main_revision,root_group,allow_contributions,git_synced \
  --all --json
```

Match the user's phrase case-insensitively: `space_name` first, then `route`, then substring
on both. Then:

- **Exactly one match** → **echo the resolution** — "Buzz → `en0gc980kr`, route `/buzz`" —
  so a wrong guess is visible before anything is written.
- **Zero matches** → list every space as `space_name (route)` and ask. Creating a space is a
  far larger decision than the user asked for; leave it to them.
- **Several matches** → ask, showing `space_name`, `route`, and modified date.
- **`git_synced: 1`** → **stop.** The space is GitHub-backed and every write is refused. The
  edit belongs in the repo.

Done when you hold the docname (`en0gc980kr`). Every API takes it; the route slug is never
accepted.

## Step 2 — Confirm access

```bash
frappectl -s "$SITE" method call wiki.api.get_space_capabilities -F space=<SPACE> --json
# {"can_read": true, "can_write": true, "can_contribute": true}
```

`can_contribute` → you can author. `can_write` → you can also approve and merge. With
`can_write: false`, author and submit, then name who has to approve. With
`can_contribute: false`, stop — the CR would be unwritable.

## Step 3 — Open a draft change request

```bash
frappectl -s "$SITE" method call $CR.get_or_create_draft_change_request \
  -F wiki_space=<SPACE> -f title="<what you're doing>" --json
```

Keep `.name`. This **reuses** the user's newest `Draft` / `Changes Requested` CR in that space,
so the title may be ignored and unrelated work may already sit in it. Check
`diff_change_request` first; if it holds someone's unfinished work, take a fresh branch with
`$CR.create_change_request`.

## Step 4 — Get the tree, root key, and version

```bash
frappectl -s "$SITE" method call $CR.get_cr_tree -F name=<CR_NAME> --json
# {"children": [...], "root_group": "3629fdc59867", "operation_version": 3}
```

Keep both values. `root_group` here is **already a doc_key** — use it verbatim as `parent_key`
for top-level pages. `operation_version` is your first `base_version`.

## Step 5 — Write content

`frappectl method call` has no `--input`, so markdown goes through `frappectl api` via stdin:

```bash
cat <<'JSON' | frappectl -s "$SITE" api method/$CR.apply_cr_operations --input - -X POST
{
  "name": "<CR_NAME>",
  "base_version": 3,
  "operations": [
    {"id": "m_1", "type": "create_node", "temp_key": "tmp-1",
     "parent_key": "3629fdc59867", "title": "Onboarding",
     "is_group": false, "is_published": true,
     "content": "# Onboarding\n\nRaw **markdown**.\n"}
  ]
}
JSON
```

Ops: `create_node`, `update_content`, `update_node`, `delete_node`, `move_node`,
`reorder_children` — field lists in `reference/api.md`. Later ops in the *same* batch may
reference an earlier `temp_key`; a *later call* must use the real `doc_key`.

**Content is raw markdown.** HTML is stored verbatim and renders as literal text.

Every write obeys two rules:

- **Send the `current_version` you last read as `base_version`.** A `null` there disables the
  concurrency check and turns a lost update into a silent one.
- **Run `apply_cr_operations` one at a time**, each after the previous response lands. No `&`,
  no parallel tool calls — writes take a row lock and must be serial.

Read three fields from every response:

- `ok` — **success lives here, not in the exit code.** A `version_conflict` exits 0.
- `current_version` — your next `base_version`
- `temp_key_map` — `{"tmp-1": "487291614eed"}`, the real `doc_key`

Done when every page the user named holds a real `doc_key` — from `temp_key_map` for creates,
echoed in `items[]` for edits.

### One-field edits

For a pure title or publish-flag change, skip the batch machinery:

```bash
frappectl -s "$SITE" method call $CR.update_cr_page -F name=<CR_NAME> -F doc_key=<KEY> \
  -F 'fields:={"is_published": 0}'
```

No version bookkeeping. Real markdown still needs the stdin channel.

## Step 6 — Review before submitting

```bash
frappectl -s "$SITE" method call $CR.diff_change_request -F name=<CR_NAME> -f scope=summary --json
frappectl -s "$SITE" method call $CR.check_outdated -F name=<CR_NAME> --json   # must be 0
```

`check_outdated` returning `1` means main moved since this branch started. **Stop and surface
it to the user** — see [Merge conflicts](#merge-conflicts).

## Steps 7–9 — Submit, approve, merge

```bash
frappectl -s "$SITE" method call $CR.submit_change_request  -F name=<CR_NAME>
frappectl -s "$SITE" method call $CR.approve_change_request -F name=<CR_NAME>
frappectl -s "$SITE" method call $CR.merge_change_request   -F name=<CR_NAME> --json
```

Three separate calls even when the author approves their own work — the state machine has no
shortcut. Merge returns the new revision name and publishes immediately.

## Step 10 — Verify

```bash
frappectl -s "$SITE" doc list "Wiki Document" -f route=<space-route>/<slug> \
  --fields name,title,route,is_published,doc_key --json
```

Done when the live `doc_key` equals the CR's, for every page written. Use this rather than the
public `/<route>.md` endpoint, which 404s on spaces that aren't Guest-readable even after a
clean merge.

## One-way doors

Three actions have no undo. Ask the user first; everything else — creating the branch, writing
pages, submitting, approving — reverses via `withdraw_change_request` /
`archive_change_request`, so just do it.

1. **`merge_change_request`** publishes live. Show the `diff_change_request` summary — page
   titles and change types — and the URLs that will appear. Then ask.
2. **`delete_node` / an `is_deleted` flip** cascades to descendants. Name every page that will
   disappear before running the op; `deleted_doc_keys` in the response is the authoritative
   cascade list.
3. **`resolve_merge_conflict`** discards one whole side. See below.

## Merge conflicts

Resolution is whole-item, there is no rebase, and the orientation is **backwards from git**:

> **`ours` = what is already live on main. `theirs` = the change request's work.**

So `resolve_merge_conflict(name, "ours")` **throws away the author's edits.** Hand conflicts
to the user: ask per conflict, showing both bodies, and phrase the choice in plain words —
"keep your new text" vs "keep what's already published". Read
`reference/api.md` § Merge conflicts before calling anything here.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `{"ok": false, "error": "version_conflict"}` **and exit code 0** | stale `base_version` | Re-read `get_cr_tree`, replay. `set -e` will not catch this — check `ok` |
| Page saved but never appears anywhere | `parent_key: null` | Pass the tree's `root_group`; it is mandatory |
| `DoesNotExistError` on a `tmp-*` key | temp key reused across calls | Use the real key from `temp_key_map` |
| `There are no changes to submit for review.` | nothing net-changed | Create-then-delete, or pure reordering, can cancel out |
| `PermissionError` on every write | `git_synced: 1` space | Edit the GitHub repo instead |
| `You do not have permission to review…` | `can_write: false` | Submit and hand off to someone with Write on the space |
| `Merge conflicts detected` | main moved since `base_revision` | Hand to the user; read the inversion above first |
| Page renders as literal markup | HTML sent as `content` | Send markdown |
| A field won't clear | `null` in `fields` is dropped | Pass `""` |
