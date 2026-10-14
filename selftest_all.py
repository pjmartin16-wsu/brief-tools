#!/usr/bin/env python3
"""selftest_all.py - one command for every Setnova checker's self-test (13 Oct 2026, checker-efficiency #5).

Runs, in order, and prints one line each:
  setnova_checks.py --self-test        Morning Brief gate (seeded historic errors must FAIL, clean fixture PASS)
  run_corpus.py                        every archived sent edition gives exactly its expected result
  tally.py --self-test                 per-check score (#7)
  brief_tape_check.py                  the 13 Oct production Desk tape FAILs one-event-per-row (Q6) and PASSes once split;
                                       a barred phrase and six calendar seeds FAIL
  decision_list.py --self-test         the weekly audit's PM decision list
  releasecheck.py --self-test          the outbound-document gate (15 content checks, 25 verb-gate patterns)
  claims_review_by.py --self-test      review-by dates on CLAIMS.md and the terms file
  layoutaudit.py test/fixture-bad.html must report CLIP, GUTTER, IMBAL, OFLOW and OVERLAP (needs Playwright + Chromium)
All of them read their wording lists from setnova_rules.json, each pinning its SHA-256.
Exit 0 only if every line is PASS. A checker that could not run is BROKEN, never a pass.
    python3 selftest_all.py [--skip-layout]   (--skip-layout only where no browser exists; it prints NOT RUN)
"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def run(args, **kw):
    p = subprocess.run([PY] + args, cwd=HERE, capture_output=True, text=True, **kw)
    return p.returncode, (p.stdout + p.stderr).strip()


def last(out):
    return out.splitlines()[-1] if out else ""


# The 13 Oct production tape's calendar split one event per row (RELEASE-QUEUE Q6, 14 Oct 2026): the same events,
# times moved out of the text into t, same-day rows in time order. The production bytes themselves now FAIL.
Q6_WEEK = [
    {"d": "MON 12", "it": "Columbus Day federal holiday (no Treasury curve published)", "t": ""},
    {"d": "TUE 13", "it": "Gov. Waller discussion on AI, Bloomberg New Economy Forum", "t": "3:45 a.m. ET"},
    {"d": "WED 14", "it": "VCS Bowman discussion", "t": "5:40 a.m. ET"},
    {"d": "WED 14", "it": "September CPI and Real Earnings", "t": "8:30 ET", "mq": True},
    {"d": "WED 14", "it": "Beige Book", "t": "2:00 p.m. ET"},
    {"d": "THU 15", "it": "September PPI", "t": "8:30 ET"},
    {"d": "THU 15", "it": "Chairman Warsh fireside chat with IMF MD Georgieva", "t": "11:30 p.m. ET"},
    {"d": "FRI 16", "it": "September import and export prices", "t": "8:30 ET"},
    {"d": "FRI 16", "it": "industrial production (G.17)", "t": "9:15 ET"},
]
# Each seed must FAIL the tape check with the quoted words in its output.
Q6_SEEDS = [
    ("14 Oct production rows: two events under one time", lambda w: w.__setitem__(slice(None), [
        {"d": "WED 14", "it": "Beige Book; 17-week bill auction", "t": "2:00 ET"},
        {"d": "THU 15", "it": "September PPI; 4- and 8-week bill auctions", "t": "8:30 ET"}]), "one event per row"),
    ("a middle dot joining two events", lambda w: w[5].__setitem__("it", "September PPI \u00b7 jobless claims"), "one event per row"),
    ("a time inside the event text", lambda w: w[4].__setitem__("it", "Beige Book 2:00 p.m. ET"), "time goes in t only"),
    ("same-day rows out of time order", lambda w: w.insert(3, w.pop(4)), "order same-day rows by time"),
    ("a day that reappears", lambda w: w.append({"d": "WED 14", "it": "17-week bill auction", "t": ""}), "must be adjacent"),
    ("a time not in H:MM ET form", lambda w: w[5].__setitem__("t", "8.30am"), "is not 'H:MM ET'"),
    # Review of 14 Oct (fresh context): the cases below each slipped past, or split the two engines, before the fix.
    ("a bare 7:00 (a.m. or p.m.?)", lambda w: w.insert(5, {"d": "WED 14", "it": "Evening remarks", "t": "7:00 ET"}), "is not 'H:MM ET'"),
    ("an impossible time", lambda w: w[5].__setitem__("t", "99:99 ET"), "is not 'H:MM ET'"),
    ("a fullwidth digit in t", lambda w: w[5].__setitem__("t", "\uff18:30 ET"), "is not 'H:MM ET'"),
    ("a trailing newline in t", lambda w: w[5].__setitem__("t", "8:30 ET\n"), "is not 'H:MM ET'"),
    ("a clock time after a non-ASCII letter", lambda w: w[5].__setitem__("it", "\u00e912:30 remarks"), "time goes in t only"),
    ("a row with no t", lambda w: w[5].pop("t"), "needs t"),
    ("' + ' joining two events", lambda w: w[3].__setitem__("it", "September CPI + Real Earnings"), "one event per row"),
    ("' + ' between no-break spaces", lambda w: w[3].__setitem__("it", "September CPI\u00a0+\u00a0Real Earnings"), "one event per row"),
]


def tape_case():
    good = os.path.join(HERE, "test", "marketclose_desk_2026-10-13_production.json")
    prod = json.load(open(good, encoding="utf-8"))

    def check(t):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(t, f)
        c, o = run(["brief_tape_check.py", f.name])
        os.unlink(f.name)
        return c, o

    c0, o0 = check(prod)
    fixed = json.loads(json.dumps(prod)); fixed["week"] = json.loads(json.dumps(Q6_WEEK))
    c1, o1 = check(fixed)
    barred = json.loads(json.dumps(fixed)); barred["commentary"]["read"].append("Banks should lock in term funding now.")
    c2, o2 = check(barred)
    missed = []
    for name, mut, words in Q6_SEEDS:
        t = json.loads(json.dumps(fixed)); mut(t["week"])
        c, o = check(t)
        if not (c == 1 and words in o): missed.append(name)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(prod["week"], f)
    cw0, ow0 = run(["brief_tape_check.py", "--week", f.name]); os.unlink(f.name)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(Q6_WEEK, f)
    cw1, ow1 = run(["brief_tape_check.py", "--week", f.name]); os.unlink(f.name)
    if not (cw0 == 1 and "one event per row" in ow0 and cw1 == 0): missed.append("--week mode (STEP 5c)")
    ok = c0 == 1 and "one event per row" in o0 and c1 == 0 and c2 == 1 and "barred" in o2 and not missed
    return ok, (f"13 Oct production tape: {'FAIL as required (Q6)' if c0 == 1 else last(o0)}; same tape, one event per row: {last(o1)}; "
                f"seeded barred phrase: {'FAIL as required' if c2 == 1 else last(o2)}; Q6 seeds {len(Q6_SEEDS) - len(missed)}/{len(Q6_SEEDS)} FAIL; --week {'FAIL/PASS as required' if cw0 == 1 and cw1 == 0 else 'WRONG'}"
                + (f" (missed: {', '.join(missed)})" if missed else ""))


def layout_case(skip):
    if skip:
        return None, "NOT RUN (--skip-layout)"
    c, o = run(["layoutaudit.py", os.path.join("test", "fixture-bad.html")])
    kinds = {k for k in ("CLIP", "GUTTER", "IMBAL", "OFLOW", "OVERLAP") if f"[{k}]" in o}
    return kinds == {"CLIP", "GUTTER", "IMBAL", "OFLOW", "OVERLAP"}, f"{len(kinds)}/5 classes on the bad fixture ({', '.join(sorted(kinds)) or last(o)[:120]})"


def main():
    skip = "--skip-layout" in sys.argv
    results = []
    for name, args, want in (("setnova_checks", ["setnova_checks.py", "--self-test"], "SELF-TEST PASS"),
                             ("corpus", ["run_corpus.py"], "CORPUS PASS"),
                             ("tally", ["tally.py", "--self-test"], "SELF-TEST PASS"),
                             ("decision_list", ["decision_list.py", "--self-test"], "SELF-TEST PASS"),
                             ("releasecheck", ["releasecheck.py", "--self-test"], "SELF-TEST PASSED"),
                             ("claims_review_by", ["claims_review_by.py", "--self-test"], "SELF-TEST PASS")):
        c, o = run(args)
        ok = c == 0 and last(o).startswith(want)
        results.append((name, ok, last(o)[:160]))
    results.append(("brief_tape_check",) + tape_case())
    results.append(("layoutaudit",) + layout_case(skip))
    bad = 0
    for name, ok, msg in results:
        tag = "PASS  " if ok else ("NOT RUN" if ok is None else "BROKEN")
        bad += ok is False
        print(f"{tag} {name:17} {msg}")
    print(f"ALL SELF-TESTS {'PASS' if not bad else 'FAIL'} ({len(results) - bad}/{len(results)})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
