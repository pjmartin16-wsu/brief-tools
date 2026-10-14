# setnova-tools

Deterministic release checks for the Setnova Advisory Treasury Morning Brief.

`setnova_checks.py` runs every mechanical gate of the brief's production prompt as code (standard library only):
wording scans, change-basis arithmetic against Treasury's own table, plain-text vs HTML figures, prose vs grid,
cross-edition consistency, dashes and branding. Exit 0 = pass, 1 = at least one failure, 2 = input error.

    python3 setnova_checks.py --self-test

Every rule has a seeded fixture that must make it fail. Add the fixture before adding the rule.
The production run uses a copy only if its SHA-256 matches the one pinned in the run's prompt,
so a change here takes effect only when the prompt's pin is updated too.

## Rule-change policy (PM, 10 Oct 2026)

A new rule must either replace an old one or come with a test: a seeded fixture in `SEEDS` that makes it FAIL.
A quarterly pass (the "Setnova quarterly rule prune" scheduled task) lists the rules that no longer fire, and PM decides which to delete.
A change here takes effect in the brief only when the hash pinned in the brief prompt is updated.

## Regression corpus (added 12 Oct 2026)

`corpus/<date>/` holds sent editions exactly as emailed (email HTML and plain text), and `corpus/EXPECTED.json`
records which checks each one fails and why. `python3 run_corpus.py` runs the self-test and then every archived
edition; GitHub Actions runs the same on every push (`.github/workflows/checks.yml`). A checker change may move the
pin in the brief prompt only when that run is green. To accept a changed result on purpose, run
`python3 run_corpus.py --update`, review the diff, and explain it in the commit message.
Add each new sent edition (or any edition that exposed a false positive or a miss) as a new dated folder.

## Prompts (added 12 Oct 2026)

`prompts/PROMPT_LIVE.md` is the production brief prompt; `prompts/PROMPT_SLIM.md` is the slim candidate (D2), with
the checker run on the drafts before anything is rendered. A scheduled task loads one of them by commit and SHA-256,
so a change here takes effect only when the task's pin moves. Recipient addresses are supplied by the task prompt and
are never stored in this public repo.

## decision_list.py (added 12 Oct 2026)

The mechanical half of the weekly audit's "PM DECISION LIST": the OPEN and ANSWERED rows of `00_Context/DECISIONS.md`,
and the `_LOG.md` lines from the last 8 days that ask something of PM. The audit only matches those lines to rows by meaning.
It closes the one POLICY BREACH in the 10 Oct rule prune (a rule added with no test). `python3 decision_list.py --self-test`.

## One rule file, one command (13 Oct 2026, checker-efficiency #5 and #7)

- **`setnova_rules.json`** holds every wording list: the brief's (retired wording, advice, expectations, producer and offer
  wording, captions, the Sources-line families, the dateline, the FRED same-close series) and the release gate's (Shelf B,
  verdict and verb gates, never-say, superseded prices, real institutions, retired figures). It is read by
  `setnova_checks.py`, `brief_tape_check.py`, `releasecheck.py` and the Desk's `tools/marketclose-check.ts` (which carries a
  byte copy, tested against the pin). Each consumer pins the file's SHA-256, so pinning a script pins its rules.
  Before 13 Oct the brief, the Desk tape check and the release gate each kept their own copy, and they had drifted.
- **`selftest_all.py`** runs every checker's self-test, the regression corpus, the tally self-test, the tape check on the
  13 Oct production tape and `layoutaudit.py` on its bad fixture. CI runs it on every push. `releasecheck.py`,
  `layoutaudit.py` and `claims_review_by.py` moved here from the workspace's `06_Projects/_tools/` (fixtures in `test/`).
- **`tally.py`** (#7) keeps score per check: real catches and false alarms on archived sent editions (from the
  "real defect" / "false positive" reasons in `corpus/EXPECTED.json`), plus pre-send catches from the brief run's
  "Checker first-pass" lines, kept in `corpus/FIRST-PASS.txt`. The quarterly prune reads this instead of re-reading editions.
- **New checks (13 Oct):** `src` (the Sources line names every source family used), `dateline` (no single
  "Market data as of" over figures with other dates; RELEASE-QUEUE Q4) and `G2b` (every FRED figure is as fresh as
  FRED's own data file; FX had no check before).

## 14 Oct 2026: the verifier becomes a gate; reopenings; false alarms scored as such

- **`auct`** (RELEASE-QUEUE Q7): an auction is called a "reopening" only when marketclose.json records `"reopening": true`
  for that security, taken from TreasuryDirect's tentative auction schedule ("R"). Seeded with the 14 Oct case, an
  original-issue 5-year TIPS printed as a reopening (Number Verifier HOLD). The 13 Oct shadow edition now fails it too
  (a 20-year reopening printed with no schedule record); EXPECTED.json says why.
- **G8 window** (Q8): a rate's figure may not be read across another rate label. On 14 Oct the first pass read
  "SOFR ... for Oct 9 · IORB 3.90%" as SOFR 3.90% (4 false alarms); a regression case keeps it out, and a new seed
  proves a real SOFR mismatch is still caught.
- **`tally.py`**: a first-pass count followed by `fp` ("G8 x4 fp") is scored as a false alarm, not a catch, and counts
  toward CRYING WOLF. `corpus/FIRST-PASS.txt` now marks the 14 Oct line that way.
- **`prompts/PROMPT_SLIM.md`** (PM decision A25, "Gate with one fix loop"): the Number Verifier runs in STEP 5e, BEFORE
  any send. HOLD = one fix loop and a fresh second round; still HOLD = nothing sent and a "Setnova Brief HELD" email.
  No verdict by 5:30 AM PT = sent unverified with a DEGRADED RUN alert (PM is the only recipient).

## 14 Oct 2026 (evening): one event per calendar row (RELEASE-QUEUE Q6)

- **`brief_tape_check.py`**: `week[]` rows hold ONE event. No `;`, `|` or `·` joining events, no clock time inside the
  event text (the time goes in `t`, from that event's own source, `""` when it has none), `t` in `H:MM ET` /
  `H:MM a.m. ET` / `H:MM p.m. ET` form, same-day rows adjacent and in time order. On 13 and 14 Oct the tape (and both
  editions) printed "September PPI; 4- and 8-week bill auctions 8:30 ET", one time read as both events'.
  New `--week rows.json` mode checks the calendar rows alone, so the brief run catches a joined row in STEP 5c(3a),
  BEFORE rendering, instead of on the tape after the send.
- **Tests:** the real 13 Oct production tape now FAILS (it is the case that motivated the rule); the same tape split one
  event per row PASSES; six seeds (two events under one time from the 14 Oct rows, a middle dot, a time in the text,
  same-day rows out of order, a day that reappears, a malformed time) each FAIL, and each PASSED the previous code.
  `selftest_all.py` runs them. The Desk's `tools/marketclose-check.ts` mirrors the rule (`weekErrors`), and
  `tests/engine/bridge.test.ts` requires both engines to agree on all of these cases.
- **`prompts/PROMPT_SLIM.md`**: G6a gains the one-event-per-row rule; STEP 5c gains (3a), the `--week` run; STEP 6c's
  `week[]` comes from that file; the pinned SHA-256 of `brief_tape_check.py` moves. `prompts/PROMPT_LIVE.md` is not
  loaded since D2 (13 Oct) and keeps the old pin unchanged.
- **Tightened after a fresh-context review the same evening:** `t` is required (a string, `""` allowed); hours 1-12 and
  minutes 00-59; a bare hour only from 8 to 12 or 1 to 6 (a bare 7 is ambiguous, so 7:00 and other off-hours times
  say "a.m." or "p.m."); `" + "` outside parentheses counts as a join ("PMIs (mfg + services)" stays legal; "GDP+PCE"
  with no spaces is not caught, accepted); ASCII digits only and no trailing newline in `t`, so the Python and
  TypeScript engines agree on every reviewed input. `--week` exits 2 on an input or usage error. 14 seeds in all.
