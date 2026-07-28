---
name: frappe-wiki-authoring
description: Author and publish Frappe Wiki pages from the CLI using frappectl — open a change request, write markdown pages into a space, review the diff, then submit, approve, and merge it live. Use when the user wants to add, edit, rename, restructure, or delete a wiki page or section; refers to a wiki space by name ("add a page to the Buzz wiki", "update our handbook space", "our docs"); or mentions Wiki Change Request, wiki CR, apply_cr_operations, or publishing/merging wiki changes.
---

# Frappe Wiki authoring via frappectl

Drives Frappe Wiki's change-request flow from the CLI — the same whitelisted APIs the
`/wiki-app` SPA calls. Author content in a change request, then walk it through
submit → approve → merge to publish.

Requires Wiki v3 (the `frappe_wiki` module: Wiki Document, Wiki Change Request, Wiki
Revision). The legacy v2 `Wiki Page` doctypes have no change-request flow.

Every command here was verified end-to-end against a live site. See `reference/api.md` for
complete signatures, all operation fields, the status machine, and the permission model.

## Setup

Site access is preconfigured. Pass `-s <profile>` when the user names a site; with multiple
profiles, never guess — ask. Do not run `frappectl auth` commands or touch `FRAPPE_*` env vars.

```bash
export CR=wiki.frappe_wiki.doctype.wiki_change_request.wiki_change_request
export SITE="<profile>"
```

## Step 1 — Resolve the space (do this first, always)

The user will say "the Buzz wiki" or "our handbook". That is not an identifier. Resolve it:

```bash
frappectl -s "$SITE" doc list "Wiki Space" \
  --fields name,space_name,route,main_revision,root_group,allow_contributions,git_synced \
  --all --json
```

Match the user's phrase case-insensitively: `space_name` first, then `route`, then substring
on both. Then:

- **Exactly one match** → proceed, and **echo the resolution** — "Buzz → `en0gc980kr`, route
  `/buzz`" — so a wrong guess is visible before anything is written.
- **Zero matches** → list every space as `space_name (route)` and ask. **Never create a space**;
  that is a much larger decision than the user asked for.
- **Multiple matches** → ask, showing `space_name`, `route`, and modified date. Never take the first.
- **`git_synced: 1`** → **stop.** The space is GitHub-backed and every write will be refused.
  Tell the user the edit belongs in the repo.
- **`can_contribute: false`** (step 2) → stop. Don't open a CR that can't be written.

Carry the **docname** (`en0gc980kr`) forward. Every API takes it. The route slug is never accepted.

## Step 2 — Confirm access

```bash
frappectl -s "$SITE" method call wiki.api.get_space_capabilities -F space=<SPACE> --json
# {"can_read": true, "can_write": true, "can_contribute": true}
```

`can_contribute` → you can author. `can_write` → you can also approve and merge. If
`can_write` is false, author and submit, then tell the user who needs to approve.

## Step 3 — Open a draft change request

```bash
frappectl -s "$SITE" method call $CR.get_or_create_draft_change_request \
  -F wiki_space=<SPACE> -f title="<what you're doing>" --json
```

Keep `.name`. This **reuses** the user's newest `Draft` / `Changes Requested` CR in that space —
so the title may be ignored, and there may already be unrelated work in it. Check
`diff_change_request` before adding to it; if it contains someone's unfinished work, use
`$CR.create_change_request` for a fresh one instead.

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

Read three fields from every response:

- `ok` — **branch on this, not on exit status** (see Failure modes)
- `current_version` — your next `base_version`
- `temp_key_map` — `{"tmp-1": "487291614eed"}`, the real `doc_key`

Ops: `create_node`, `update_content`, `update_node`, `delete_node`, `move_node`,
`reorder_children`. Field lists in `reference/api.md`. Later ops in the *same* batch may
reference an earlier `temp_key`; a *later call* must use the real `doc_key`.

**Content is raw markdown.** No HTML — it is stored verbatim and renders as literal text.

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

`check_outdated` returning `1` means main moved since this CR started. **Stop and surface it
to the user.** There is no rebase, and conflict resolution clobbers whole pages in one
direction. Do not resolve it autonomously.

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

The live `doc_key` will equal the CR's. Use this rather than fetching the public URL — the
`/<route>.md` endpoint 404s on spaces that aren't Guest-readable even after a clean merge.

## Confirmation gates

Ask the user before these three. Everything else — creating the CR, writing pages,
submitting, approving — is reversible via `withdraw_change_request` / `archive_change_request`,
so just do it.

1. **Before `merge_change_request`.** This publishes live and there is no undo endpoint. Show
   the `diff_change_request` summary — page titles and change types — and the URLs that will
   appear. Then ask.
2. **Before any `delete_node` or `is_deleted` flip.** Deletion cascades to descendants. Run the
   op only after naming every page that will disappear; `deleted_doc_keys` in the response is
   the authoritative cascade list.
3. **Before `resolve_merge_conflict`.** See the warning below. Ask per conflict, showing both
   bodies. Never loop over conflicts picking a side.

## Two rules that do not bend

- **Never send `base_version: null`.** It disables the concurrency check and turns a lost
  update into a silent one.
- **Never run two `apply_cr_operations` concurrently on one CR.** No `&`, no parallel tool
  calls. Writes take a row lock and must be sequential.

## ⚠️ `ours` and `theirs` are inverted

If you ever reach merge-conflict resolution:

> **`ours` = what is already live on main. `theirs` = the change request's work.**

This is backwards from git. `resolve_merge_conflict(name, "ours")` **discards the author's
edits**. When explaining the choice to a user, say it in plain words — "keep your new text"
vs "keep what's already published" — never the bare flag names.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `{"ok": false, "error": "version_conflict"}` **and exit code 0** | stale `base_version` | Re-read `get_cr_tree`, replay. `set -e` will not catch this — check `ok`. |
| Page saved but never appears anywhere | `parent_key: null` | Always pass `get_cr_tree(...)["root_group"]`; it is mandatory |
| `DoesNotExistError` on a `tmp-*` key | temp key reused across calls | Use the real key from `temp_key_map` |
| `There are no changes to submit for review.` | nothing actually changed | Create-then-delete, or pure reordering, can net to empty |
| `PermissionError` on every write | `git_synced: 1` space | Edit the GitHub repo instead |
| `You do not have permission to review…` | `can_write: false` | Submit and hand off to someone with Write on the space |
| `Merge conflicts detected` | main moved since `base_revision` | Surface to the user; read the inversion warning first |
| Page renders as literal markup | HTML sent as `content` | Send markdown |
| A field won't clear | `null` in `update_node.fields` is dropped | Pass `""` |

See `reference/api.md` for full signatures, every operation's fields, the status machine, and
the legacy single-shot RPCs.
