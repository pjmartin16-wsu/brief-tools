#!/usr/bin/env python3
"""tally.py - per-check score: real catches against false alarms (13 Oct 2026, checker-efficiency #7).

WHY. The quarterly rule prune used to re-read every edition to learn which checks fire. This keeps the score as data:
  * ESCAPES: what each check fails on the archived SENT editions in corpus/ (EXPECTED.json, whose "why" says
    "real defect: ..." or "false positive: ..." for each check id);
  * PRE-SEND: what each check caught on the brief run's FIRST checker pass, before anything was sent, from the
    "Checker first-pass: exit N; G4c x4, 9a x1" lines the run puts in its same-morning check email. Those lines are
    kept, one per run, in corpus/FIRST-PASS.txt ("YYYY-MM-DD <tab> exit N; <hits or none>").
    A count followed by "fp" ("G8 x4 fp") is a FALSE ALARM the run classed as such in STEP 5c(4): it is scored as a
    false alarm, not a catch (14 Oct 2026, RELEASE-QUEUE Q8: the 14 Oct G8 x4 were false alarms and scored as catches).
A check that keeps crying wolf, or that never fires anywhere, stands out before the quarterly pass.

    python3 tally.py                      # corpus + corpus/FIRST-PASS.txt
    python3 tally.py --first-pass FILE    # add more first-pass lines (the weekly audit passes the week's)
    python3 tally.py --json out.json
    python3 tally.py --self-test
Standard library only. Exit 0 = tally printed, 1 = self-test failed, 2 = input error.
"""
import argparse, json, os, re, sys, tempfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "corpus")
FP_LINE = re.compile(r"^(20\d\d-\d\d-\d\d)\S*\s+(?:Checker first-pass:\s*)?exit\s+(\d)\s*;\s*(.*)$")
HIT = re.compile(r"([0-9A-Za-z]+)\s*[x×]\s*(\d+)(\s*\(?(?:fp|false alarms?|false positives?)\)?)?", re.I)


def check_ids():
    sys.path.insert(0, HERE)
    import setnova_checks as sc  # noqa: E402  (reads setnova_rules.json and checks its pin)
    return [c[0] for c in sc.CHECKS] + ["G8", "G2b"]


def read_first_pass(paths):
    runs, bad = [], []
    for p in paths:
        if not os.path.exists(p):
            continue
        for n, line in enumerate(open(p, encoding="utf-8"), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = FP_LINE.match(line)
            if not m:
                bad.append(f"{os.path.basename(p)}:{n}: {line[:80]}")
                continue
            hits = {}
            if m.group(3).strip().lower() not in ("none", ""):
                for k, v, fp in HIT.findall(m.group(3)):
                    key = (k, "fp") if fp.strip() else k
                    hits[key] = hits.get(key, 0) + int(v)
            runs.append((m.group(1), int(m.group(2)), hits))
    return runs, bad


def tally(expected, runs, ids):
    t = {c: defaultdict(int) for c in ids}
    for day, e in expected.items():
        why = e.get("why", {}) if isinstance(e, dict) else {}
        for f in (e.get("fails", []) if isinstance(e, dict) else []):
            cid = f.split("/")[0]
            row = t.setdefault(cid, defaultdict(int))
            w = str(why.get(cid, ""))
            row["escape_real" if w.startswith("real defect") else "escape_fp" if w.startswith("false positive") else "escape_unlabelled"] += 1
    for day, code, hits in runs:
        for cid, n in hits.items():
            if isinstance(cid, tuple):
                t.setdefault(cid[0], defaultdict(int))["presend_fp"] += n
            else:
                t.setdefault(cid, defaultdict(int))["presend"] += n
    out = []
    for cid, r in t.items():
        fired = r["escape_real"] + r["escape_fp"] + r["escape_unlabelled"] + r["presend"] + r["presend_fp"]
        wolf, real = r["escape_fp"] + r["presend_fp"], r["escape_real"] + r["presend"]
        flag = ""
        if wolf >= 2 and wolf > real:
            flag = "CRYING WOLF"
        elif r["escape_unlabelled"]:
            flag = "LABEL IT (EXPECTED.json why)"
        elif fired == 0:
            flag = "silent (prune: KEEP-SAFETY or RETIRE?)"
        out.append({"check": cid, "presend": r["presend"], "presend_fp": r["presend_fp"], "escape_real": r["escape_real"], "escape_fp": r["escape_fp"],
                    "escape_unlabelled": r["escape_unlabelled"], "flag": flag})
    return out


def render(rows, ndays, nruns):
    lines = [f"TALLY over {ndays} archived sent-edition day(s) and {nruns} first-pass run line(s)",
             f"{'check':9} {'pre-send':>8} {'pre-send fp':>11} {'escape real':>11} {'escape fp':>9}  flag"]
    for r in sorted(rows, key=lambda r: r["check"]):
        lines.append(f"{r['check']:9} {r['presend']:8} {r['presend_fp']:11} {r['escape_real']:11} {r['escape_fp'] + r['escape_unlabelled']:9}  {r['flag']}")
    return "\n".join(lines)


def self_test():
    ids = ["9a", "G4c", "src", "brand", "G8"]
    exp = {"d1": {"fails": ["src/full", "src/generic", "brand/full"], "why": {"src": "real defect: x", "brand": "false positive: y"}},
           "d2": {"fails": ["brand/generic"], "why": {"brand": "false positive: z"}},
           "d3": {"fails": ["9a/full"], "why": {}}}
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "fp.txt")
        open(f, "w").write("# comment\n2026-10-13\texit 1; G4c×4, 9a x1\n2026-10-14  Checker first-pass: exit 0; none\nnot a line\n"
                           "2026-10-15\texit 1; G8 x4 fp, 9a x1\n")
        runs, bad = read_first_pass([f])
    rows = {r["check"]: r for r in tally(exp, runs, ids)}
    want = [(len(runs) == 3, "three first-pass lines read"), (len(bad) == 1, "the malformed line reported, not skipped"),
            (rows["G4c"]["presend"] == 4, "G4c x4 counted"), (rows["9a"]["presend"] == 2, "'x1' counted on both lines"),
            (rows["G8"]["presend"] == 0 and rows["G8"]["presend_fp"] == 4, "'G8 x4 fp' scored as 4 false alarms, not catches (Q8)"),
            (rows["G8"]["flag"] == "CRYING WOLF", "pre-send false alarms with no real catch flagged"),
            (rows["src"]["escape_real"] == 2, "real escapes counted per edition"),
            (rows["brand"]["flag"] == "CRYING WOLF", "two false positives over no real catch flagged"),
            (rows["9a"]["flag"].startswith("LABEL"), "an unlabelled escape asks for a label")]
    ok = True
    for good, why in want:
        print(f"  {'ok    ' if good else 'FAILED'} {why}")
        ok &= good
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--first-pass", action="append", default=[])
    ap.add_argument("--json")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    try:
        expected = json.load(open(os.path.join(CORPUS, "EXPECTED.json"), encoding="utf-8"))
    except (OSError, ValueError) as ex:
        print(f"INPUT ERROR: {ex}", file=sys.stderr)
        return 2
    runs, bad = read_first_pass([os.path.join(CORPUS, "FIRST-PASS.txt")] + a.first_pass)
    rows = tally(expected, runs, check_ids())
    print(render(rows, len(expected), len(runs)))
    for b in bad:
        print(f"UNREADABLE first-pass line (fix it; it was not counted): {b}")
    if a.json:
        json.dump({"rows": rows, "days": len(expected), "runs": len(runs), "unreadable": bad}, open(a.json, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
