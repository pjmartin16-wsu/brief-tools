#!/usr/bin/env python3
"""selftest_all.py - one command for every Setnova checker's self-test (13 Oct 2026, checker-efficiency #5).

Runs, in order, and prints one line each:
  setnova_checks.py --self-test        Morning Brief gate (seeded historic errors must FAIL, clean fixture PASS)
  run_corpus.py                        every archived sent edition gives exactly its expected result
  tally.py --self-test                 per-check score (#7)
  brief_tape_check.py                  the 13 Oct production Desk tape PASSes; a tape with a barred phrase FAILs
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


def tape_case():
    good = os.path.join(HERE, "test", "marketclose_desk_2026-10-13_production.json")
    c1, o1 = run(["brief_tape_check.py", good])
    t = json.load(open(good, encoding="utf-8"))
    t["commentary"]["read"].append("Banks should lock in term funding now.")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(t, f)
    c2, o2 = run(["brief_tape_check.py", f.name])
    os.unlink(f.name)
    ok = c1 == 0 and c2 == 1 and "barred" in o2
    return ok, f"production tape: {last(o1)}; seeded barred phrase: {'FAIL as required' if c2 == 1 else last(o2)}"


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
