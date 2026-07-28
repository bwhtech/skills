---
name: go-live-gate
description: Go-live gate for any system that writes to a money-bearing external system (pricing, stock, payments, marketplaces). Use when the user asks to go live, cut over, launch, or verify a system shortly before production use.
---

# Go-Live Gate

**Money-bearing** systems fail through data and missing invariants, not broken pages. "Code-ready" and "launch-ready" are different claims — a passing system-health test (pages load, jobs run, no errors) earns the first one only.

Two losses set this gate. On 2026-06-10 a pricing system passed every smoke test, then pushed prices computed from £0 purchase costs to Amazon: ~500 below-cost orders in 2 hours. Knight Capital lost $440M in 45 minutes on a deploy that looked fine — stale flag reuse, no kill switch, no canary, 45 minutes to find the off button.

Every phase below maps to one of those causes. Run all six in order, and carry each to its **Gate** before starting the next.

## Phase 1 — Enumerate the money invariants

Before touching the system, write down every rule whose violation loses money. Derive them from domain docs, client statements, and past incidents. For each, state the live-data query that proves it holds. Examples (pricing system):

- No sellable SKU has purchase cost ≤ 0 or missing
- min_price ≤ our_price ≤ max_price, all > 0; min == max only where explicitly fixed
- Every SKU has a valid, active strategy; an auto-selected strategy matches actual stock reality
- Computed price within N% of current live market price (the deviation baseline must EXIST)
- The external system's own guardrails are configured — e.g. Amazon Seller Central per-SKU min/max bounds deactivate a listing instead of selling at a wrong price

**Gate:** every invariant written down and paired with its proving query, each one confirmed by the data owner. An invariant the client cannot confirm is a finding, not a pass.

## Phase 2 — Pre-mortem (Klein technique)

Write the post-mortem as if the launch already failed catastrophically: "We lost £50k in the first 2 hours. Here is what happened." Generate ≥5 distinct narratives spanning data hole, race, wrong config, external-system behaviour, and human error during cutover. Check each against the CURRENT system by reading code and running live queries.

**Gate:** every narrative either disproved with cited evidence, or carried forward as an open gate item.

## Phase 3 — Data gates (live queries, zero tolerance)

Run every Phase 1 invariant as a query or report against production-shaped data. Send each violation list to its data owner with a deadline, then re-run. Also verify staleness (when each critical dataset was last updated), completeness (every launch item present in every required table), and that every guard comparing against "current" values has a stored baseline.

**Gate:** a clean re-run — zero violations across the whole launch set, every launch item accounted for in every required table, every baseline stored.

## Phase 4 — Kill switch + rollback drill

- Identify THE one switch that provably stops all outbound writes — buttons, scripts, and scheduled jobs included, not just the main cron. A surviving bypass path fails the gate.
- FLIP IT in the test environment and prove writes are blocked: call the transport layer and expect rejection. A kill switch that has never been flipped is a hypothesis.
- Build the rollback matrix: for each subsystem (code, DB, external prices, external stock, inbound data) record the revert method, who executes it, and realistic timing. Take the on-demand backup AT cutover and verify restore prerequisites — e.g. on Frappe the encryption key must travel with the backup, or credentials die silently.
- Pre-write the revert payload (e.g. a known-good price CSV) BEFORE pushing anything.

**Gate:** a blocked write observed at the transport layer with the switch on, a rollback matrix complete for every subsystem with named executors and timings, and the revert payload written.

## Phase 5 — Canary design

Choose the canary set by **failure-mode coverage** rather than convenience: every data-source path WITH and WITHOUT backing data (the missing-data case must be observed BLOCKED), every branch of the routing/strategy logic, every structural special case (bundles, packs, pools, multi-mapping).

Per push: pre-gate report clean → dry-run artifact diffed against expectation → push → poll the result and parse PER-ITEM errors (an accepted batch can still reject rows) → read back the external system's live state and compare to the penny → loss-detector report empty.

Ramp canaries → 24h soak → 10x → full, with stop conditions written before the first push.

**Gate:** every failure-mode path above covered by a canary, one full push carried through all six steps, and the ramp plan plus stop conditions written down.

## Phase 6 — Monitoring + humans

- A loss-detector report or query that would catch the worst pre-mortem narrative within minutes, assigned to a named person on a written rota for the first 48h.
- Alerting on external-submission failure, sync stall, and error spike. Silence must be distinguishable from health.
- **Two-person rule**: the switch is flipped only after a second person independently confirms the Phase 3 reports are clean.

**Gate:** the loss detector demonstrated against the worst narrative, the 48h rota named, all three alerts firing in test, and the second person's confirmation recorded.

## Verdict

End with a table: phase → PASS/FAIL → evidence (query result, test output, drill log). LAUNCH-READY only when all six phases pass; otherwise state which of the two claims you are making.

---

Distilled from: Klein, "Performing a Project Premortem" (HBR 2007) · Knight Capital SEC post-mortem 2012 · Google SRE book, Launch Readiness Review · Gawande, The Checklist Manifesto · Amazon SP-API Feeds/Listings docs · the June-10 pricing incident analysis.
