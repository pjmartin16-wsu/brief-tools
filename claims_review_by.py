#!/usr/bin/env python3
"""Review-by dates for the register (CLAIMS.md and the confirmed-terms file).

Setnova Advisory, 2 Oct 2026. Implements part A of the facts-freshness proposal PM agreed on 29 Sep 2026
(`_tools/PM_Facts-Freshness-Proposal_2026-09-29.md`): every register row carries `verified` and `review-by`.
Shelf lives (PM, 29 Sep): market and rate figures 90 days; regulatory, firm, offer and biography facts 1 year;
entity facts (name, UBI, EIN, formation date) permanent.

  add    One-time. Appends the two columns to every table in the file. `verified` is the LATEST date written
         in the row's own text (the row's last dated entry, not a new check; nothing is invented). A row with
         no date gets "not recorded" and review-by one week out, so the next weekly audit lists it.
  check  Lists every row whose review-by is on or before --asof (default today), as RE-VERIFY lines for the
         weekly audit email. Exit 1 if any are stale.
         Since 10 Oct 2026 it also fails a row that has NO review-by date (a row added after 2 Oct without the
         two columns used to pass silently), and a table that has no review-by column at all. A register that
         cannot be checked is reported, never counted as clean.
  --self-test  Seeded rows that must be flagged; run by the weekly audit before trusting a clean result.

Usage:
  python claims_review_by.py add   CLAIMS.md --out CLAIMS.md
  python claims_review_by.py check CLAIMS.md [--asof 2026-10-05]
"""
import argparse, datetime as dt, re, sys
from pathlib import Path

MON = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
PIPE = re.compile(r"(?<!\\)\|")
PERMANENT = re.compile(r"Setnova Advisory LLC exists|\bUBI\b|\bEIN\b|formation date", re.I)
SHORT = re.compile(r"\(proposed\)|CR-102|\bmarket level\b|\bas of the close\b", re.I)


def dates_in(text, today):
    out = []
    for d, m, y in re.findall(r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?(?:\s+(20\d\d))?\b", text, re.I):
        out.append((int(y) if y else today.year, MON[m[:3].lower()], int(d)))
    for m, d, y in re.findall(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(20\d\d)\b", text, re.I):
        out.append((int(y), MON[m[:3].lower()], int(d)))
    for y, m, d in re.findall(r"\b(20\d\d)-(\d\d)-(\d\d)\b", text):
        out.append((int(y), int(m), int(d)))
    good = []
    for y, m, d in out:
        try:
            x = dt.date(y, m, d)
        except ValueError:
            continue
        if x <= today:
            good.append(x)
    return good


def shelf(row):
    if PERMANENT.search(row):
        return None, "permanent (entity fact)"
    if SHORT.search(row):
        return 90, "90 days (market/rate or proposed rule)"
    return 365, "1 year (regulatory/firm/offer/biography)"


def cmd_add(a):
    today = dt.date.fromisoformat(a.asof) if a.asof else dt.date.today()
    lines = Path(a.file).read_text(encoding="utf-8").split("\n")
    out, ncols, added = [], None, 0
    for k, l in enumerate(lines):
        if not l.startswith("|"):
            ncols = None
            out.append(l)
            continue
        n = len(PIPE.findall(l))
        nxt = lines[k + 1] if k + 1 < len(lines) else ""
        if ncols is None and re.fullmatch(r"\|(\s*:?-+:?\s*\|)+", nxt.strip()):   # header row
            ncols = n
            if "review-by" in l:
                sys.exit("already has review-by columns")
            out.append(l + " verified | review-by |")
            continue
        if re.fullmatch(r"\|(\s*:?-+:?\s*\|)+", l.strip()):
            out.append(l + "---|---|")
            continue
        ncols = ncols or n
        ds = dates_in(l, today)
        days, why = shelf(l)
        if ds:
            v = max(ds)
            ver = f"{v.isoformat()} (last dated entry)"
            rb = "permanent" if days is None else f"{(v + dt.timedelta(days=days)).isoformat()} · {why}"
        else:
            ver = "not recorded"
            rb = "permanent" if days is None else f"{(today + dt.timedelta(days=7)).isoformat()} · RE-VERIFY (no date on file)"
        out.append(l + f" {ver} | {rb} |")
        added += 1
    Path(a.out or a.file).write_text("\n".join(out), encoding="utf-8")
    print(f"{added} rows dated")


SEP = re.compile(r"\|(\s*:?-+:?\s*\|)+")


def check_lines(lines, asof):
    stale, in_table, has_rb = [], False, False
    for i, l in enumerate(lines, 1):
        if not l.startswith("|"):
            in_table = False
            continue
        if SEP.fullmatch(l.strip()):
            continue
        cells = [c.strip() for c in PIPE.split(l)[1:-1]]
        nxt = lines[i] if i < len(lines) else ""
        if not in_table and SEP.fullmatch(nxt.strip()):          # header row starts a table
            in_table, has_rb = True, "review-by" in l
            if not has_rb:
                stale.append(f"RE-VERIFY line {i}: table has no review-by column: {l[:90]}")
            continue
        if not has_rb or len(cells) < 2:
            continue
        label = re.sub(r"[*`⛔⭐⚠✅]", "", cells[0])[:110].strip()
        last = cells[-1]
        m = re.match(r"(20\d\d-\d\d-\d\d)", last)
        if m:
            if dt.date.fromisoformat(m.group(1)) <= asof:
                stale.append(f"RE-VERIFY line {i}: {label} (review-by {m.group(1)}; verified {cells[-2]})")
        elif not last.lower().startswith("permanent"):
            stale.append(f"RE-VERIFY line {i}: {label} (no review-by date on the row; last cell '{last[:40]}')")
    return stale


def cmd_check(a):
    asof = dt.date.fromisoformat(a.asof) if a.asof else dt.date.today()
    stale = check_lines(Path(a.file).read_text(encoding="utf-8").split("\n"), asof)
    print(f"{len(stale)} rows due on or before {asof.isoformat()} in {Path(a.file).name}")
    for s in stale:
        print(s)
    return 1 if stale else 0


def self_test():
    asof = dt.date(2026, 10, 10)
    good = ["| Claim | Status | verified | review-by |", "|---|---|---|---|",
            "| Fresh fact | EXECUTED | 2026-09-01 (source) | 2027-09-01 · 1 year |",
            "| Entity fact | EXECUTED | 2026-09-04 | permanent |"]
    seeds = [("past review-by", good + ["| Old rate | EXECUTED | 2026-06-01 | 2026-08-30 · 90 days |"]),
             ("row added without the columns", good + ["| New claim added later | MADE |"]),
             ("table with no review-by column", good + ["", "| Term | Value |", "|---|---|", "| Fee | $5,000 |"])]
    ok = not check_lines(good, asof)
    print(f"clean table: {'0 flagged' if ok else 'FLAGGED (false positive)'}")
    for why, lines in seeds:
        hit = bool(check_lines(lines, asof))
        print(f"  {'caught' if hit else 'MISSED'}  {why}")
        ok &= hit
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    x = sp.add_parser("add"); x.add_argument("file"); x.add_argument("--out"); x.add_argument("--asof")
    c = sp.add_parser("check"); c.add_argument("file"); c.add_argument("--asof")
    if argv is None and sys.argv[1:] == ["--self-test"]:
        sys.exit(self_test())
    a = p.parse_args(argv)
    if a.cmd == "add":
        cmd_add(a)
    else:
        sys.exit(cmd_check(a))


if __name__ == "__main__":
    main()
