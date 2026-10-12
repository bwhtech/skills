---
name: raise-pr
description: Lint, commit, push and open a PR with screenshots and an at-a-glance description; merge only when asked. Use when the user asks to raise, open or ship a PR for the current work, optionally naming a base branch and whether to merge.
---

Raise a pull request for the current work. Take the base branch, whether to merge, and a line on what the
change is for from the user's request.

1. **Branch.** If on the base branch, create `type/short-slug` first. Base = the branch named in the
   request, else the repo default (`gh repo view --json defaultBranchRef`). Confirm the base exists on
   `origin` — a local-only `main` is not a valid base.
2. **Strip comments.** Remove every comment and docstring the branch adds (`git diff <base>...` plus
   uncommitted changes): Python `#` comments and docstrings, JS `//` and `/* */`, CSS `/* */`, HTML/Jinja
   comments. Keep licence headers, shebangs and lint pragmas (`# noqa`, `# type:`, `// eslint-disable`).
   No exceptions without the user's explicit approval of that specific comment.
3. **Lint like CI.** If `.pre-commit-config.yaml` exists, run `pre-commit run --all-files` until a run is
   clean. CI runs `--all-files` with the hook-pinned ruff, which can disagree with local ruff. Exclude
   vendored/minified files (`public/js/vendor/`, `*.min.js`) from formatters instead of reformatting them.
4. **Commit.** Stage explicit paths only. Conventional one-line message: `type(scope): subject`.
5. **Screenshots.** If the diff changes what renders (`.html`, `.vue`, `.jinja`, templates, CSS, frontend
   JS), follow the `pr-screenshots` skill steps 1–4: capture, crop + annotate, visual review, commit
   the images under `docs/implementation/media/`.
6. **Push and open the PR** with this body and nothing else:

   ```markdown
   1. <the problem, in user terms>
   2. <what you can do now>

   You can visit <route / screen> to see it.

   <img src="https://github.com/<owner>/<repo>/blob/<branch>/docs/implementation/media/<name>.png?raw=1" width="700">
   ```

   No "Verified:" line, no implementation notes, no "Generated with Claude Code" or session-link footer.
   Set the body with `gh api -X PATCH repos/<owner>/<repo>/pulls/<n> -f body=...`, read it back, and
   `curl -sL -o /dev/null -w "%{http_code} %{content_type}"` every image URL (must be `200 image/png`).
7. **CI.** `gh pr checks <n> --watch`. Fix failures and push again; never merge a red PR.
8. **Merge only if the request asks for it.** `gh pr merge <n> --merge` once checks are green. Keep the
   branch: the screenshot URLs point at it and die when it is deleted.

Report the PR URL, the checks result, and whether it was merged.
