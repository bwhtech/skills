---
name: go-live-gate
description: Mandatory launch-readiness gate for any system that writes to a money-bearing external system (Amazon pricing/stock, payments, marketplaces). Use whenever the user says "go live", "golive", "cutover", "launch", "ready for production", "switch on the API", or asks to test/verify a system shortly before production use. Runs financial-invariant verification on live data, a pre-mortem, kill-switch and rollback drills, and a canary design — not just system-health checks.
---

# Go-Live Gate

A system-health test ("pages load, jobs run, no errors") is NOT launch readiness. Money-bearing systems fail through **data + missing invariants**, not broken pages. This gate exists because on 2026-06-10 a pricing system passed every smoke test and then pushed prices computed from £0 purchase costs to Amazon — ~500 below-cost orders in 2 hours. Every phase below maps to a cause of that loss or a canonical industry failure.

Never skip a phase because "it looks fine." Knight Capital lost $440M in 45 minutes on a deploy that looked fine (stale flag reuse, no kill switch, no canary, 45 min to find the off button). Phases 4-6 are that lesson.

## Phase 1 — Enumerate the money invariants (write them down first)

Before touching the system, list every rule whose violation loses money. Derive from: domain docs, client statements, past incidents. For each invariant, you must be able to state the live-data query that proves it holds. Examples (pricing system):
- No sellable SKU has purchase cost ≤ 0 or missing
- min_price ≤ our_price ≤ max_price, all > 0; min == max only when explicitly fixed
- Every SKU has a valid, active strategy; auto-selected strategy matches actual stock reality
- Computed price within N% of current live market price (deviation baseline must EXIST)
- External system's own guardrails configured (e.g. Amazon Seller Central per-SKU min/max bounds — deactivates listing instead of selling at a wrong price)

If the user/client can't confirm an invariant, that's a finding, not a pass.

## Phase 2 — Pre-mortem (Klein technique)

Write the post-mortem as if the launch already failed catastrophically: "We lost £50k in the first 2 hours. Here is what happened." Generate ≥5 distinct failure narratives (data hole, race, config wrong, external system behavior, human error during cutover). Then check each narrative against the CURRENT system with code reading + live queries. A narrative you cannot disprove with evidence is an open gate item.

## Phase 3 — Data gates (live queries, zero tolerance)

Run every invariant from Phase 1 as a query/report against production-shaped data. Targets are ZERO violations among the launch set — not "mostly fine". Each violation list goes to the data owner with a deadline. Re-run until clean. Verify also: staleness (when was each critical dataset last updated), completeness (every launch SKU present in every required table), and baselines for any guard that compares to "current" values.

## Phase 4 — Kill switch + rollback drill (actually flip them)

- Identify THE one switch that provably stops all outbound writes — including buttons, scripts, and scheduled jobs, not just the main cron. If bypass paths exist, the gate fails.
- FLIP IT in the test environment and prove writes are blocked (call the transport layer, expect rejection). A kill switch that has never been flipped is a hypothesis.
- Rollback matrix: for each subsystem (code, DB, external prices, external stock, inbound data), the revert method, who executes it, and realistic timing. Take the on-demand backup AT cutover, and verify restore prerequisites (e.g. Frappe: encryption key must travel with the backup or all credentials die silently).
- Pre-write the revert payload (e.g. known-good price CSV) BEFORE pushing anything.

## Phase 5 — Canary design (cover the paths, not the convenient rows)

Canary set is chosen by **failure-mode coverage**, not convenience: every data-source path WITH and WITHOUT backing data (the missing-data case must be BLOCKED, observed), every branch of the routing/strategy logic, every structural special case (bundles, packs, pools, multi-mapping). Per push: pre-gate report clean → dry-run artifact diffed against expectation → push → poll result and parse PER-ITEM errors (an accepted batch can still reject rows) → read back the external system's live state and compare to the penny → loss-detector report empty. Ramp: canaries → 24h soak → 10x → full. Written stop conditions.

## Phase 6 — Monitoring + humans

- A loss-detector report/query that would have caught the worst pre-mortem narrative within minutes, assigned to a named person on a written rota for the first 48h.
- Alerting on: external-submission failure, sync stall, error spike. Silence must be distinguishable from health.
- **Two-person rule**: the switch is flipped only after a second person independently confirms Phase 3 reports are clean. No solo go-lives.

## Verdict format

End with a table: phase → PASS/FAIL → evidence (query result, test output, drill log). Overall verdict only LAUNCH-READY when every phase passes. "Code-ready" and "launch-ready" are different claims — say which one you're making.

## Project notes (navgold_custom)

Reports: Amazon Go-Live Data Readiness, Amazon Pricing Push Readiness, Below Min Price Sales, Supplier Data Readiness, Amazon Pricing Push Monitor, Amazon Order Sync Health. Kill switch: `freeze_amazon_outbound` (Navgold Settings, enforced at Feeds/repricer transport). Full procedure: `docs/go-live-runbook.md`. Config table + rollback matrix inside it. Baselines: `bulk_fetch_selling_prices` before enabling pricing. External net: Seller Central per-SKU min/max bounds (set via Manage Pricing bulk file; cannot be removed later, only widened; exclude shipping).

## Sources distilled here

Klein, "Performing a Project Premortem" (HBR 2007) · Knight Capital SEC post-mortem 2012 (kill switch, config hygiene, canary) · Google SRE book, Launch Readiness Review · Gawande, The Checklist Manifesto · Amazon SP-API Feeds/Listings docs (result-document per-item errors; listing-level pricing-error protections) · navgold June-10 incident analysis (this skill's origin).
