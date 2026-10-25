# Project tracker

The live state of the build: what is done, what is running, what is blocked and what comes next. **If you are a coding agent taking over this repository, from any tool or vendor, start here.** This file is enough to resume without the previous agent's conversation.

Last updated: 2026-10-25 by 00-main (integration session).

---

## 1. How to take over

1. Read, in this order:
   - this file;
   - `CLAUDE.md`, the shared rules for every agent. They apply to any tool, not only Claude;
   - your brief in `spec/worker_briefs/<id>.md`;
   - the files that brief lists.
2. Work out your role:
   - The **integration lead (00-main)** owns this file, `spec/` and the merges.
   - A **worker (01–05)** edits only the paths assigned to it in `spec/ownership.toml`.
   - If no one told you your role, you are 00-main.
3. Check the real state before trusting this file. Git is the source of truth, and this file can lag:
   ```
   git fetch origin
   git status -sb
   git log --oneline -10 origin/claude/financial-modeling-architecture-o2xiwz
   git branch -a --list '*wave1/*'
   git worktree list
   ```
   Every worker branch is pushed to GitHub after each commit, so `origin/wave1/<id>` holds the latest work. Resume from it. Commits newer than the last push can be missing; check the worker's own report.
4. Run the baseline before changing anything:
   ```
   pip install -r requirements.txt
   python -m pytest                      # expect: contract tests SKIPPED with owner named, the rest pass
   python build/generate_workbook.py --test-build
   ```
5. Update this file whenever something in §3–§8 changes. Commit and push it with the change it describes.

**Who edits this file.** Only 00-main edits it, so it never conflicts in merges. Workers report to 00-main in their final message and their `MODULE.md`. 00-main copies the result here.

## 2. Fixed facts

| Item | Value |
|---|---|
| Repository | https://github.com/rish106-hub/test |
| Integration branch | `claude/financial-modeling-architecture-o2xiwz`. Only 00-main pushes here |
| Worker branches | `wave1/<worker-id>`, e.g. `wave1/01-data` |
| Requirement | spec v3.0, `spec/source/Indian_Equity_Valuation_and_MF_NAV_Model_v3.xml` |
| Contract version | v1.1 (`spec/financial_model_contract.md`; changes in `data/canonical/governance_log.csv`) |
| Output | `build/out/Indian_Equity_Valuation_and_MF_NAV_Model.xlsx`, generated and never committed |
| Scope | C001–C007 (HDFC, ICICI, Kotak, Federal, AU SFB, Indian Bank, Max Financial); MF001 Parag Parikh Flexi Cap, MF002 HDFC Mid Cap (Direct Plan, Growth) |

**Standing instructions from the user:**
- Do not create a pull request unless the user asks.
- No model names or identifiers in commits, code or documents.
- Never fabricate data (R001).
- Prove the calculations end to end before adding more companies, charts or workers (D-028).

## 3. Phase board

| Phase | Status | Exit criterion |
|---|---|---|
| 0. Architecture (contract, schemas, interfaces, ownership, contract tests, build, QA harness) | **DONE**: `dc96e9c`, `f752ee1` (v1.1 review applied) | Pushed and verified on GitHub |
| 1. Wave 1, vertical slice: HDFC Bank → its fund (01, 02, 03, 05) | **IN PROGRESS**, launched 2026-10-25 | Gate G1 (§5) |
| 2. Wave 2: other 5 banks, Max Financial SOTP, every material holding, 04-charts | NOT STARTED, blocked on G1 | 00-main brief, "Wave 2" |
| 3. Release (phase 7 checklist) | NOT STARTED | 00-main brief, "Release checklist" |

## 4. Workers

| ID | Role | Model / effort | Branch | Status | Last commit | Pushed? | Next action |
|---|---|---|---|---|---|---|---|
| 00-main | Integration, contract, this file | opus / xhigh | `claude/financial-modeling-architecture-o2xiwz` | Waiting for worker reports | see `git log` | yes | Integrate each worker as it reports (§7) |
| 01-data | Data and source audit | sonnet / high | `wave1/01-data` | RUNNING | none yet (base `f752ee1`) | yes, after each commit | Feasibility report; both fund snapshots; HDFC Bank source trail; prices; NAVs; G-sec yield |
| 02-valuation | Bank valuation | opus / xhigh | `wave1/02-valuation` | RUNNING, fixture phase | none yet | yes, after each commit | Reference functions + bank sheet on fixtures; then real HDFC Bank after 01 merges |
| 03-nav | NAV engine and controls | sonnet / high | `wave1/03-nav` | RUNNING, fixture phase | `88a3998` (reference functions) | yes, after each commit | Engine on fixtures; then the real fund holding HDFC Bank after 01 and 02 merge |
| 04-charts | Charts and peers | sonnet / medium | none | ON HOLD until G1 (D-028) | none | none | none |
| 05-qa | Independent reviewer, clean room | opus / high | `wave1/05-qa` | RUNNING | none yet | yes, after each commit | I and W layers, runner; provenance audit and E-01…E-04 after real data |

The model and effort column is the plan from `CLAUDE.md`. Use the closest equivalent in another tool. What matters is that 02 and 05 get the strongest reasoning.

## 5. Gate G1 (from `spec/worker_briefs/00-main.md`)

Tick an item only when it has been **executed** on a production build. Record the evidence next to it: commit, command and result.

- [ ] E-01: HDFC Bank valued by the full RI path from cited data, with the equity bridge and freshness shown (§3.1a/b)
- [ ] E-02: HDFC Bank confirmed as a holding of an actual Direct Plan Growth scheme, citing that scheme's disclosure
- [ ] E-03: that fund's Fair NAV (M1 and M2), reconciled, with all three data-quality measures (§7.5)
- [ ] E-04: shock, bias and absolute price applied to HDFC Bank move only the expected outputs
- [ ] Both funds: one complete source-backed snapshot each, `Holdings_Coverage_Status = PASS`, every holding that lacks adequate data in `missing_data.csv` and on MF_COVERAGE_AUDIT
- [ ] 05-qa's clean-room implementation agrees with the 02 and 03 reference functions on the real data
- [ ] `tools/check_module_contract.py` accepts 01-data, 02-valuation and 03-nav; no open blocker finding
- [ ] G1 decision recorded in `data/canonical/governance_log.csv`

## 6. Relaunching a worker (any agent tool)

A worker's instructions are its brief plus the Wave 1 additions below. To relaunch, start a fresh agent in a separate worktree or clone of the integration branch, on branch `wave1/<id>`. If the branch exists remotely, check it out and continue from it. Give the agent this prompt:

> You are worker `<id>`. Read `CLAUDE.md`, `tracker.md` and `spec/worker_briefs/<id>.md`, then execute the brief at its Wave 1 scope. Apply the Wave 1 additions in `tracker.md` §6.

With Claude Code: `claude --worktree <id> --model <model> --effort <effort> "<prompt above>"`. Other tools: open the clone, give the same prompt.

**Wave 1 additions, for all workers:**
- Work on `wave1/<id>` and commit in small logical commits.
- Push your own branch after every commit: `git push -u origin wave1/<id>`. Never push the integration branch or another worker's branch. The user approved this on 2026-10-25.
- Never commit an `.xlsx`.
- Run `python tools/check_ownership.py <id> claude/financial-modeling-architecture-o2xiwz` before handing over.
- Don't stop to ask questions. Make the defensible call, record it, and carry on.
- Your final message to 00-main gives:
  - branch name and final commit hash;
  - what you built;
  - the exact output of your checks, where only a check that ran and passed counts as PASS;
  - the change requests you filed;
  - what you need from other workers.

**Per worker:**
- **01-data.** The only worker that fetches real data, and Wave 1 scope only: both fund snapshots, both NAVs, prices on one date, HDFC Bank including every interim quarter after its last annual report, the G-sec yield, and HDFC Bank's corporate actions. Every value comes from a document retrieved in that session, with a SHA256. Raw files over 20 MB: record the URL and hash, don't commit the file. Never bypass a login, paywall or terms of use.
- **02-valuation and 03-nav.** Build and verify on synthetic fixtures first. Never fetch or type real numbers yourselves. Switch to real inputs only after 00-main merges 01-data and tells you.
- **05-qa.** Clean room: write `tests/independent/` from `spec/` and `src/common/` only. Never read other workers' implementations, branches or worktrees. Comparison tests skip with a reason while worker functions still raise `NotImplementedError`.

## 7. Integration procedure (00-main)

For each worker that reports ready, in merge order 01 → 02 → 04 → 03:

```
git checkout wave1/<id>
python tools/check_ownership.py <id> claude/financial-modeling-architecture-o2xiwz
python build/generate_workbook.py --test-build --only <id>
python tools/check_module_contract.py <id> --manifest build/out/manifest.json --run-tests
git checkout claude/financial-modeling-architecture-o2xiwz && git merge --no-ff wave1/<id>
```

Then:
1. Run the gates in `spec/worker_briefs/00-main.md`, steps 4–6.
2. Add a row to `governance_log.csv`.
3. Update this file.
4. `git push -u origin claude/financial-modeling-architecture-o2xiwz`.
5. Tell the other workers to merge the integration branch.

Reject a worker on any `REJECT` line and send it the list.

After 01-data merges, 00-main must also:
- set `in_Price_Date`, `in_Valuation_Date` and `in_Risk_Free_Rate` in `data/reference/global_inputs.csv`, based on 01-data's report;
- send 02 and 03 to the real-data phase;
- send 05-qa to the provenance audit and E-01…E-04.

## 8. Open issues and risks

| # | Issue | Impact | Owner | Status |
|---|---|---|---|---|
| R-1 | Worker branches were local only | Unmerged work would be lost if the container were reclaimed | 00-main | MITIGATED 2026-10-25: all `wave1/*` pushed. Workers push after every commit; uncommitted edits are still at risk |
| R-2 | www.nseindia.com and www.hdfcfund.com returned HTTP 403 to a plain request on 2026-10-25 (BSE, AMFI, PPFAS, RBI, SEBI, Nifty Indices returned 200) | NSE prices and the HDFC Mid Cap disclosure may need alternative sources, or be marked unavailable | 01-data | OPEN |
| R-3 | `in_Valuation_Date`, `in_Price_Date` and `in_Risk_Free_Rate` are blank | A production valuation can't run until they are set from 01-data's sourced data | 00-main | OPEN, waiting on 01-data |

## 9. Change requests and findings

| ID | From | Subject | Status |
|---|---|---|---|
| none yet | | | |

Change requests live in `spec/change_requests/`, findings in `qa/findings/`.

## 10. Log

Newest first. One line per event: what changed, the commit, the evidence.

- **2026-10-25.** With the user's approval, all four `wave1/*` branches were pushed and verified with `git ls-remote`: 01, 02 and 05 at `f752ee1`, 03 at `88a3998`. Workers were told to push their own branch after every commit.
- **2026-10-25.** `tracker.md` and `AGENTS.md` added (handover for any agent tool); both registered to 00-main in `spec/ownership.toml`.
- **2026-10-25.** `.claude/worktrees/` (agent worktrees) added to `.gitignore`; `d60f7b6` pushed.
- **2026-10-25.** Wave 1 launched: 01-data, 02-valuation, 03-nav and 05-qa, each in its own worktree on `wave1/<id>`, from `f752ee1`. Network probe: see R-2.
- **2026-10-25.** GitHub access fixed. `dc96e9c` and `f752ee1` pushed, and the remote head was verified equal to local (`f752ee1`).
- **2026-10-25.** Contract v1.1 (`f752ee1`) applies the pre-launch review:
  - one TPP (D-023);
  - shock composition and precedence (D-024);
  - the five dates and the equity bridge (D-025);
  - three data-quality measures (D-026), which also fixed the H_COVERAGE_STATUS gap;
  - the module contract checker (D-027);
  - phased launch and gate G1 (D-028).
  Tests at that commit: 35 passed, 75 contract tests skipped (owners named). All 75 passed under `--strict-impl` against a throwaway implementation that was not committed.
- **Earlier.** Architecture contract `dc96e9c`: contract, schemas, interfaces, ownership, contract tests, build pipeline and QA harness.
