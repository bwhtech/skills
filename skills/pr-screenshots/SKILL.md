---
name: pr-screenshots
description: Attach before/after screenshots to a pull request for any frontend/UI change - cropped to the region of interest, marked with red boxes and arrows, and reviewed by a visual-reviewer agent before the PR goes up. Use whenever raising or updating a PR that touches .vue/.html/.jinja/templates/CSS/Tailwind/theme files, or when asked to "add screenshots to the PR", "show before and after", "crop to ROI", or "review how it looks".
---

# PR screenshots

A frontend PR without pictures cannot be reviewed. Reference style: frappe/frappe#35626.

## When this applies

The diff touches any of: `*.vue`, `*.html`, `*.jinja`, `templates/`, `themes/`,
`*.css`, Tailwind classes, or frontend `*.js`/`*.ts` that changes what renders.
Pure backend / test / config diffs skip this entirely.

## 1. Run the app and capture the pair

Use the `run` skill (or the project's own run instructions) to get the app up, and
`agent-browser` to drive it. Capture the **same route, same viewport, same data** for
both states — only the code differs.

```bash
# after (current branch)
agent-browser --session pr open "<url>" && agent-browser --session pr wait 3000 \
  && agent-browser --session pr screenshot <scratchpad>/<view>-after-full.png

# before — temporarily restore the base version of just the changed files
git checkout <base-branch> -- <changed files>
# wait for HMR/rebuild, then re-open the same url
agent-browser --session pr screenshot <scratchpad>/<view>-before-full.png
git checkout <this-branch> -- <changed files>     # ALWAYS restore
```

Rules:
- One pair per distinct view the change touches (list page + detail page + mobile
  width if the change affects narrow layouts).
- Seed or navigate to **real data** — an empty state proves nothing.
- Restore the working tree before doing anything else; verify with `git status`. This
  matters most on a shared server checkout, where another session may commit leftovers.
- A pure-addition change has no "before" — ship a single "after" image instead of
  faking one.
- The `-full.png` captures stay in the scratchpad; only the annotated crops (step 2) ship.
- Toasts and error pop-ups do not render in a headless capture. Assert the message from
  the DOM instead, skip that image, and quote the error text in the body. Never fake it.
- Alpine `x-show` looks frozen headless (rAF never drains): shim
  `window.requestAnimationFrame = cb => setTimeout(() => cb(performance.now()), 0)`
  before driving the page.

## 2. Crop and annotate

Crop each capture to the region that changed, scale it 2x, and mark the change with a
red rounded box, plus an arrow when the eye needs leading (e.g. "click this → that opens").
An arrow must run through empty space; if it would cross another field or text, use the box alone.
Use the same crop box for the before and after pair so they line up.

```bash
# needs Pillow; without it: uv run --with pillow python ...
python3 <this skill's folder>/annotate.py <scratchpad>/header-after-full.png \
  docs/implementation/media/header-after.png \
  --crop 900,0,1280,130 --box 1142,18,1178,62 --arrow 1070,118,1142,58
```

Coordinates are source-screenshot pixels: measure them with
`getBoundingClientRect()` in `agent-browser eval` rather than guessing. **Read the
annotated image** before using it — a box that misses its target is worse than none.

## 3. Get the screenshots reviewed

Run the `visual-reviewer` skill (visual/UX judgement, reads the images), plus a code reviewer for the
frontend diff, **before** the PR body is written. Give
the reviewer the image paths, the intent of the change, and the running URL, and tell
it explicitly not to launch or modify anything.

Act on REQUEST CHANGES first, then re-capture the "after" images. Do not publish a
PR carrying screenshots the reviewer rejected, or one that shows an unrelated bug
(a wrong total, a stray error) the PR does not fix — crop it out or drop the image.

## 4. Publish the images

GitHub's drag-and-drop upload host (`github.com/user-attachments/assets/<uuid>`) is
browser-session-only — there is no API for it and `gh` cannot use it. Relative repo
paths do **not** render in PR/issue bodies either.

**Use the house convention:** commit the screenshots into the PR branch under
`docs/implementation/media/` and link them as blob URLs with `?raw=1`:

```
https://github.com/<owner>/<repo>/blob/<branch>/docs/implementation/media/<name>.png?raw=1
```

Name files after the change, not the PR number: `<view>-before.png` / `<view>-after.png`. The URL dies with the branch after merge; that is accepted.

Only when images must outlive the branch: with a GitHub session in `agent-browser`, upload
into the PR comment box's hidden `input[type=file]` and use the `user-attachments` URL it inserts.

## 5. Put them in the PR body

The intent must be clear at a glance: the problem in user terms, what you can do now,
where to see it, then the images. Nothing else — no "Verified:" line, no implementation
notes (file names, routes, mechanisms), no test logs, no "Generated with Claude Code" /
session-link footer. Those are noise; reasoning belongs in code comments or the review thread.

**One image per row, never a side-by-side table.** A capture squeezed into half a
table column is unreadable.

```markdown
1. <the problem, in user terms>
2. <what you can do now>

You can visit <route / screen> to see it.

## Before

<img src="<url>/<view>-before.png?raw=1" width="760">

## After

<img src="<url>/<view>-after.png?raw=1" width="760">

```

Set `width` to the annotated image's pixel width, capped at 900. The 2x scale then keeps
it sharp without rendering as a giant column.

Then **verify**: `curl -sL -o /dev/null -w "%{http_code} %{content_type}" <raw-url>` must
print `200 image/png` for every image (`?raw=1` redirects, hence `-L`), and the body must
come back changed when read again —
`gh pr edit` fails silently on repos with Projects (GraphQL scope), so patch with
`gh api -X PATCH repos/<owner>/<repo>/pulls/<n> -f body="$(cat body.md)"` and read the
body back.

## Checklist before you say it's done

- [ ] before + after captured at the same route/viewport/data
- [ ] working tree restored (`git status` clean of the temporary checkout)
- [ ] each image cropped to its ROI, change boxed in red, annotated image looked at
- [ ] visual reviewer ran; its blocking findings are fixed and re-captured
- [ ] every image URL returns 200 with `content_type: image/png`
- [ ] PR body read back: problem / what you can do now / where to see it, images render, no Verified line or footer
