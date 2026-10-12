#!/usr/bin/env python3
"""decision_list.py - the mechanical half of the weekly audit's PM DECISION LIST.

WHY (12 Oct 2026): the quarterly rule prune of 10 Oct found one POLICY BREACH: the weekly audit's
"PM DECISION LIST" step was added on 10 Oct with neither a test nor a rule it replaced. PM's rule:
"Every new rule must either replace an old one or come with a test." This script is that test's home:
it does the parts that can be code, and --self-test proves it still does them.

What it does (code):
  1. Reads 00_Context/DECISIONS.md and lists every OPEN row (D-numbers) and every ANSWERED row
     (A-numbers) with its question text.
  2. Reads _LOG.md and lists every line, in entries dated within the last N days (default 8), that
     asks something of PM ("PM's call", "needs PM", "Owed by PM", "for PM to decide", "PM decides",
     "open for PM", "waiting on PM"), with its entry date.
What it leaves to the audit (judgement): whether a candidate line is NEW or matches an OPEN or
ANSWERED row by meaning, and routing by type (counsel vs PM vs checkers).

Usage:
  python3 decision_list.py 00_Context/DECISIONS.md _LOG.md --asof 2026-10-12 [--days 8] [--json out.json]
  python3 decision_list.py --self-test
Exit: 0 = ran; 1 = self-test failed; 2 = input error (file missing, no OPEN or ANSWERED table found).
Standard library only.
"""
import argparse, datetime as dt, json, re, sys

TRIGGERS = [r"PM's call", r"\bneeds PM\b", r"\bOwed by PM\b", r"\bfor PM to decide\b", r"\bPM decides\b",
            r"\bopen for PM\b", r"\bwaiting on PM\b"]
TRIG_RE = re.compile("|".join(TRIGGERS), re.I)
ROW_RE = re.compile(r"^\|\s*([DA]\d+)\s*\|\s*([^|]*)\|\s*([^|]*)\|")
ENTRY_RE = re.compile(r"^## \**(20\d\d-\d\d-\d\d)")


def parse_decisions(text):
    """Return (open_rows, answered_rows): lists of {id, date, question}. Rows are read only inside their section."""
    open_rows, answered, section = [], [], None
    for line in text.splitlines():
        if line.startswith("## "):
            h = line.lower()
            section = "open" if h.startswith("## open") else "answered" if h.startswith("## answered") else None
            continue
        m = ROW_RE.match(line)
        if not m or section is None:
            continue
        row = {"id": m.group(1), "date": m.group(2).strip(), "question": m.group(3).strip()}
        if section == "open" and row["id"].startswith("D"):
            open_rows.append(row)
        elif section == "answered" and row["id"].startswith("A"):
            answered.append(row)
    return open_rows, answered


def scan_log(text, asof, days):
    """Return candidate lines [{date, line}] from entries dated asof-days .. asof inclusive."""
    lo = asof - dt.timedelta(days=days)
    out, cur = [], None
    for line in text.splitlines():
        m = ENTRY_RE.match(line)
        if m:
            cur = dt.date.fromisoformat(m.group(1))
            continue
        if cur is None or not (lo <= cur <= asof):
            continue
        if TRIG_RE.search(line):
            out.append({"date": cur.isoformat(), "line": line.strip()[:300]})
    return out


def run(dec_text, log_text, asof, days):
    o, a = parse_decisions(dec_text)
    if not o and not a:
        raise ValueError("no OPEN or ANSWERED rows found in DECISIONS.md")
    return {"open": o, "answered": a, "candidates": scan_log(log_text, asof, days), "asof": asof.isoformat(), "days": days}


def report(r):
    L = [f"OPEN ({len(r['open'])}):"] + [f"  {x['id']} | {x['date']} | {x['question']}" for x in r["open"]]
    L += [f"ANSWERED ({len(r['answered'])}, never re-ask):"] + [f"  {x['id']} | {x['question'][:120]}" for x in r["answered"]]
    L += [f"LOG CANDIDATES, last {r['days']} days to {r['asof']} ({len(r['candidates'])}): match each to an OPEN or ANSWERED row by meaning, else it is NEW"]
    L += [f"  {c['date']} | {c['line']}" for c in r["candidates"]]
    return "\n".join(L)


# ---------------------------------------------------------------- self-test
FIX_DEC = """# Setnova decisions register

## OPEN (for the next Monday slot)

| # | Opened | Question | Why it is PM's | Notes |
|---|---|---|---|---|
| D2 | 10 Oct | Switch the production brief to the slim prompt? | Production change | After 13 Oct |
| D9 | 12 Oct | Test row with a pipe-free question | Money | |

## ANSWERED (never re-ask)

| # | Date | Question | PM's answer | Applied in |
|---|---|---|---|---|
| A1 | 1 Oct | The status sentence | "Keep it" | Site |
| A20 | 12 Oct | D6: LinkedIn Sales Navigator before 23 Oct | "Wait for the 23 Oct review" | Trial review |
| D99 | 1 Oct | A D-row sitting in ANSWERED must not be read as open | x | x |
"""
FIX_LOG = """# Setnova — Log

## 2026-10-12 (Monday): something
- **Still open for PM:** whether white-on-cyan date chips are allowed.
- Ordinary line with no ask.
- Sales Navigator: needs PM before 23 Oct.

## 2026-10-07 (Wednesday): earlier
- The E&O bind date is PM's call.

## 2026-10-01 (Thursday): too old
- Owed by PM: an old question outside the window.
"""


def self_test():
    ok = True
    r = run(FIX_DEC, FIX_LOG, dt.date(2026, 10, 12), 8)
    def chk(cond, what):
        nonlocal ok
        print(("  pass  " if cond else "  FAIL  ") + what)
        ok &= bool(cond)
    chk([x["id"] for x in r["open"]] == ["D2", "D9"], "OPEN rows read: D2, D9 (and no D-row from the ANSWERED section)")
    chk([x["id"] for x in r["answered"]] == ["A1", "A20"], "ANSWERED rows read: A1, A20")
    lines = [c["line"] for c in r["candidates"]]
    chk(any("white-on-cyan" in l for l in lines), "seed NEW candidate found ('Still open for PM' line)")
    chk(any("Sales Navigator" in l for l in lines), "seed already-answered candidate surfaced for matching (A20)")
    chk(any("E&O" in l for l in lines), "line 5 days old inside the 8-day window found")
    chk(not any("old question" in l for l in lines), "line 11 days old excluded")
    chk(not any("Ordinary line" in l for l in lines), "line with no ask excluded")
    try:
        run("# empty\n", FIX_LOG, dt.date(2026, 10, 12), 8)
        chk(False, "empty register raises an input error")
    except ValueError:
        chk(True, "empty register raises an input error")
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("decisions", nargs="?"); ap.add_argument("log", nargs="?")
    ap.add_argument("--asof", default=dt.date.today().isoformat()); ap.add_argument("--days", type=int, default=8)
    ap.add_argument("--json"); ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.decisions or not a.log:
        ap.print_help(); return 2
    try:
        r = run(open(a.decisions, encoding="utf-8").read(), open(a.log, encoding="utf-8").read(),
                dt.date.fromisoformat(a.asof), a.days)
    except (OSError, ValueError) as e:
        print(f"INPUT ERROR: {e}", file=sys.stderr); return 2
    print(report(r))
    if a.json:
        json.dump(r, open(a.json, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
