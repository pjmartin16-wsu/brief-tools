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


# 15 Oct 2026 (outside review CX-08): each must FAIL. json.dump writes NaN and Infinity as bare tokens, which
# Python's json.load reads back as floats, so these reach the check exactly as a hand-edited tape would.
TAPE_SEEDS = [
    ("NaN as a rate level", lambda t: next(r for r in t["rates"] if r["id"] == "effr").__setitem__("v", float("nan")), "must be a number"),
    ("Infinity on the curve", lambda t: t["curve"][0].__setitem__(1, float("inf")), "curve must be"),
    ("an impossible as-of date", lambda t: t["meta"].__setitem__("asof", "2026-99-99garbage"), "meta.asof"),
    ("a real date with junk after it", lambda t: t["meta"].__setitem__("asof", "2026-10-09garbage"), "meta.asof"),
    ("February 30", lambda t: t["meta"].__setitem__("asof", "2026-02-30"), "meta.asof"),
    ("2-year rate 99.9 beside a 4.80 curve point", lambda t: next(r for r in t["rates"] if r["id"] == "t2").__setitem__("v", 99.9), "one level, two values"),
    # adversarial review of the fixes, 15 Oct 2026
    ("NaN in a priced rate path", lambda t: t.__setitem__("paths", {"priced": {"src": "x", "short": [float("nan")] * 4, "long": [1, 2, 3, 4]}}), "paths.priced"),
    ("a rate path of 3 points", lambda t: t.__setitem__("paths", {"priced": {"src": "x", "short": [1, 2, 3], "long": [1, 2, 3, 4]}}), "paths.priced"),
    ("2s10s '+999 bp' against 44 bp", lambda t: next(r for r in t["rates"] if r["id"] == "s210").__setitem__("disp", "+999 bp"), "one spread, two values"),
    ("10-year 5.2451 against a 5.24 curve point (just past the shared tolerance)", lambda t: next(r for r in t["rates"] if r["id"] == "t10").__setitem__("v", 5.2451), "one level, two values"),
    ("t2 disp '99.90%' beside v 4.8 (second re-review)", lambda t: next(r for r in t["rates"] if r["id"] == "t2").__setitem__("disp", "99.90%"), "one level, two values"),
    ("s210 v 44 with disp '+999 bp'", lambda t: next(r for r in t["rates"] if r["id"] == "s210").update({"v": 44, "disp": "+999 bp"}), "one level, two values"),
    ("t2 disp '4.80% (99.90% yesterday)' (third re-review)", lambda t: next(r for r in t["rates"] if r["id"] == "t2").__setitem__("disp", "4.80% (99.90% yesterday)"), "not one level or one range"),
    ("t2 disp '1.00–99.90%' around v", lambda t: next(r for r in t["rates"] if r["id"] == "t2").__setitem__("disp", "1.00\u201399.90%"), "one level, two values"),
    ("t30 as disp only, 99.90%, beside a 5.60 curve point", lambda t: next(r for r in t["rates"] if r["id"] == "t30").update({"disp": "99.90%"}) or next(r for r in t["rates"] if r["id"] == "t30").pop("v"), "one level, two values"),
    ("paths: null", lambda t: t.__setitem__("paths", None), "paths may hold only priced"),
    ("a 400-digit integer", lambda t: next(r for r in t["rates"] if r["id"] == "effr").__setitem__("v", 10 ** 400), "TAPE FAIL"),
]


def releasecheck_missing_case():
    """15 Oct 2026 (outside review CX-07, and the adversarial review of its fix): a requested file that does not exist,
    a folder, an empty file and a binary format must each exit 2 (INPUT ERROR), never 0."""
    d = tempfile.mkdtemp()
    empty = os.path.join(d, "empty.md"); open(empty, "w").close()
    docx = os.path.join(d, "x.docx"); open(docx, "wb").write(b"PK\x03\x04 not text")
    wrong = []
    comment = os.path.join(d, "comment.html"); open(comment, "w").write("<!-- nothing a reader sees -->")
    ziptxt = os.path.join(d, "x.txt"); open(ziptxt, "wb").write(b"PK\x03\x04\x14\x00\x00\x00\x08\x00\xff\xfe")
    nul = os.path.join(d, "bin.md"); open(nul, "wb").write(b"\x00" * 64)
    bom = os.path.join(d, "bom.md"); open(bom, "wb").write(b"\xef\xbb\xbf")
    cases = (("missing file", [os.path.join("test", "no-such-release-file.md")]), ("folder", [d]), ("empty file", [empty]), (".docx", [docx]),
             ("comment-only HTML", [comment]), ("zip bytes as .txt", [ziptxt]), ("NUL-filled .md", [nul]), ("byte-order mark only", [bom]),
             ("--self-test with a file", ["--self-test", empty]))
    for label, args in cases:
        c, o = run(["releasecheck.py", *args])
        if label.startswith("--self-test"):
            if c != 2: wrong.append(f"{label} exit {c}")
            continue
        if not (c == 2 and "MISSING" in o): wrong.append(f"{label} exit {c}")
    return not wrong, f"{len(cases)} zero-coverage inputs (missing, folder, empty, binary, comment-only, self-test misuse): " + ("all exit 2 as required" if not wrong else "WRONG: " + "; ".join(wrong))


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
    hy = json.loads(json.dumps(prod)); hy["week"] = json.loads(json.dumps(Q6_WEEK)); next(r for r in hy["rates"] if r["id"] == "ff")["disp"] = "3.75-4.00%"
    ch, oh = check(hy)
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
    tmissed = []
    for name, mut, words in TAPE_SEEDS:
        t = json.loads(json.dumps(fixed)); mut(t)
        c, o = check(t)
        if not (c == 1 and words in o): tmissed.append(name)
    q6missed = list(missed)
    missed += tmissed
    if ch != 0: missed.append("ff target range with an ASCII hyphen 3.75-4.00% must PASS")
    ok = c0 == 1 and "one event per row" in o0 and c1 == 0 and c2 == 1 and "barred" in o2 and not missed
    return ok, (f"13 Oct production tape: {'FAIL as required (Q6)' if c0 == 1 else last(o0)}; same tape, one event per row: {last(o1)}; "
                f"seeded barred phrase: {'FAIL as required' if c2 == 1 else last(o2)}; CX-08 seeds {len(TAPE_SEEDS) - len(tmissed)}/{len(TAPE_SEEDS)} FAIL; Q6 seeds {len(Q6_SEEDS) - len([m for m in q6missed if m != "--week mode (STEP 5c)"])}/{len(Q6_SEEDS)} FAIL; --week {'FAIL/PASS as required' if cw0 == 1 and cw1 == 0 else 'WRONG'}"
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
    results.append(("releasecheck_missing",) + releasecheck_missing_case())
    results.append(("brief_tape_check",) + tape_case())
    results.append(("layoutaudit",) + layout_case(skip))
    bad = 0
    for name, ok, msg in results:
        tag = "PASS  " if ok else ("NOT RUN" if ok is None else "BROKEN")
        bad += ok is False
        print(f"{tag} {name:17} {msg}")
    # 15 Oct 2026 (outside review, lower priority): a NOT RUN check is named on the summary line, so a skipped layout
    # run can never read as a full pass. The line still begins "ALL SELF-TESTS PASS" when nothing failed.
    notrun = [n for n, ok, _ in results if ok is None]
    ran = len(results) - len(notrun)
    print(f"ALL SELF-TESTS {'PASS' if not bad else 'FAIL'} ({ran - bad}/{ran} ran"
          + (f"; NOT RUN: {', '.join(notrun)}" if notrun else "") + ")")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
