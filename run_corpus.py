#!/usr/bin/env python3
"""Regression corpus: run setnova_checks.py on every sent edition archived in corpus/ and compare
the failing (check, edition) pairs with corpus/EXPECTED.json.

A change to the checker passes only if (1) the self-test passes and (2) every archived edition gives
exactly its expected result: no new failure (a false positive on a brief that was fine) and no lost
failure (a real defect the checker used to catch). To accept a new result on purpose, edit EXPECTED.json
in the same commit and say why in the commit message.

    python3 run_corpus.py            # check
    python3 run_corpus.py --update   # rewrite EXPECTED.json from the current checker (review the diff!)
Standard library only. Exit 0 = all match, 1 = mismatch, 2 = setup error.
"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKER = os.path.join(HERE, "setnova_checks.py")
CORPUS = os.path.join(HERE, "corpus")
EXPECTED = os.path.join(CORPUS, "EXPECTED.json")


def run_case(date):
    d = os.path.join(CORPUS, date)
    args = [sys.executable, CHECKER, "--today", date]
    for ed in ("full", "generic"):
        for part, flag in (("_file.html", "file"), ("_email.html", "email"), (".txt", "text")):
            p = os.path.join(d, ed + part)
            if os.path.exists(p):
                args += [f"--{ed}-{flag}", p]
    mc = os.path.join(d, "marketclose.json")
    if os.path.exists(mc):
        args += ["--mc", mc]
    with tempfile.TemporaryDirectory() as t:
        out = os.path.join(t, "r.json")
        p = subprocess.run(args + ["--json", out], capture_output=True, text=True)
        if p.returncode not in (0, 1) or not os.path.exists(out):
            raise RuntimeError(f"{date}: checker exit {p.returncode}\n{p.stdout}\n{p.stderr}")
        rows = json.load(open(out))["rows"]
    fails = sorted(f"{r['check']}/{r['edition']}" for r in rows if r["status"] == "FAIL")
    hits = {f"{r['check']}/{r['edition']}": r["hits"] for r in rows if r["status"] == "FAIL"}
    return fails, hits


def main():
    st = subprocess.run([sys.executable, CHECKER, "--self-test"], capture_output=True, text=True)
    last = st.stdout.strip().splitlines()[-1] if st.stdout.strip() else ""
    print(f"self-test: {last}")
    if last != "SELF-TEST PASS":
        print(st.stdout[-3000:], st.stderr[-2000:])
        return 1
    cases = sorted(x for x in os.listdir(CORPUS) if os.path.isdir(os.path.join(CORPUS, x)))
    if not cases:
        print("no corpus cases"); return 2
    expected = json.load(open(EXPECTED)) if os.path.exists(EXPECTED) else {}
    got, bad = {}, 0
    for c in cases:
        fails, hits = run_case(c)
        got[c] = fails
        exp = expected.get(c, {}).get("fails") if isinstance(expected.get(c), dict) else None
        if "--update" in sys.argv:
            print(f"{c}: {fails or 'PASS'}"); continue
        if exp is None:
            print(f"MISMATCH {c}: no EXPECTED entry (got {fails})"); bad += 1; continue
        new, lost = sorted(set(fails) - set(exp)), sorted(set(exp) - set(fails))
        if new or lost:
            bad += 1
            print(f"MISMATCH {c}: new failures {new}, lost failures {lost}")
            for k in new:
                for h in hits[k][:5]:
                    print(f"    + {k}: {h}")
        else:
            print(f"ok       {c}: {', '.join(fails) if fails else 'PASS'}")
    if "--update" in sys.argv:
        keep = {c: expected.get(c, {}).get("why", {}) if isinstance(expected.get(c), dict) else {} for c in cases}
        json.dump({c: {"fails": got[c], "why": keep[c]} for c in cases}, open(EXPECTED, "w"), indent=1)
        print("EXPECTED.json rewritten; review the diff before committing"); return 0
    print(f"CORPUS {'PASS' if not bad else 'FAIL'}: {len(cases)} sent-edition day(s), {bad} mismatch(es)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
