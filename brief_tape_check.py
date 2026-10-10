"""Brief-side check of marketclose_desk.json (setnova-marketclose-3.0), 7 Oct 2026.
The Morning Brief run has no copy of the Desk, so it runs this (standard library only) before attaching the tape.
It mirrors src/schema/market.ts and tools/marketclose-check.ts; tests/engine/bridge.test.ts runs both on the same
files and requires the same verdict. Usage: python3 brief_tape_check.py marketclose_desk.json  -> exit 0 = PASS."""
import json, re, sys

RATE_IDS = {"ff", "effr", "sofr", "t2", "t5", "t10", "s210", "t30", "mtg30", "fhlb3", "cd12", "hysa"}
CLASSES = {"pol", "ref", "tsy", "mtg", "dep", "whl"}
NEEDED = ["t2", "t5", "t10", "cd12"]
RETIRED = [r"dot plot clusters", r"nationally available", r"top online", r"top posted", r"\bDXY\b", r"market pricing", r"markets price",
           r"priced in", r"pricing leans", r"leans toward", r"markets expect", r"\b(extend|extending|shorten|shortening) duration\b",
           r"\b(add|reduce) duration\b", r"\bladder(ing)?\b", r"\block in\b", r"\bwe recommend\b", r"\byou should\b"]
CASE_SENSITIVE = {r"\bDXY\b"}


def check(t):
    e = []
    ne = lambda x: isinstance(x, str) and len(x) > 0
    num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)
    if not isinstance(t, dict):
        return ["not a JSON object"]
    m = t.get("meta")
    if not isinstance(m, dict) or m.get("schema") != "setnova-marketclose-3.0":
        e.append("meta.schema must be setnova-marketclose-3.0")
    else:
        for k in ("label", "built"):
            if not ne(m.get(k)): e.append(f"meta.{k} missing")
        if not (isinstance(m.get("asof"), str) and re.match(r"^\d{4}-\d{2}-\d{2}", m["asof"])): e.append("meta.asof must start YYYY-MM-DD")
        if "pass" in m and not isinstance(m["pass"], str): e.append("meta.pass must be text")
        if "sample" in m and not isinstance(m["sample"], bool): e.append("meta.sample must be true/false")
    c = t.get("classes")
    if not isinstance(c, dict) or set(c) != CLASSES:
        e.append("classes must have exactly pol, ref, tsy, mtg, dep, whl")
    else:
        for k, v in c.items():
            if not (isinstance(v, dict) and all(ne(v.get(x)) for x in ("n", "asof", "src"))): e.append(f"classes.{k} needs n, asof, src")
    rates = t.get("rates")
    if not isinstance(rates, list) or not rates:
        e.append("rates missing")
        rates = []
    ids = [r.get("id") for r in rates if isinstance(r, dict)]
    if len(set(ids)) != len(ids): e.append("duplicate rate id")
    for i, r in enumerate(rates):
        if not isinstance(r, dict): e.append(f"rates[{i}] not an object"); continue
        if r.get("id") not in RATE_IDS: e.append(f"rates[{i}].id {r.get('id')!r} is not a Desk rate id")
        if r.get("cls") not in CLASSES: e.append(f"rates[{i}].cls invalid")
        if not ne(r.get("lbl")): e.append(f"rates[{i}].lbl missing")
        if "note" in r and not isinstance(r["note"], str): e.append(f"rates[{i}].note must be text")
        if "v" in r and not num(r["v"]): e.append(f"rates[{i}].v must be a number")
        if "disp" in r and not isinstance(r["disp"], str): e.append(f"rates[{i}].disp must be text")
        if "v" not in r and "disp" not in r: e.append(f"rates[{i}] needs v or disp")
    for need in NEEDED:
        r = next((x for x in rates if isinstance(x, dict) and x.get("id") == need), None)
        if not r or not num(r.get("v")): e.append(f"rate {need}: no numeric level")
    cv = t.get("curve")
    if not (isinstance(cv, list) and len(cv) >= 3 and all(isinstance(p, list) and len(p) == 2 and num(p[0]) and num(p[1]) and p[0] > 0 for p in cv)):
        e.append("curve must be at least 3 [tenor_years, yield] pairs")
    else:
        if any(cv[i][0] <= cv[i - 1][0] for i in range(1, len(cv))): e.append("curve tenors must ascend")
        for ten in (2, 10):
            if not any(p[0] == ten for p in cv): e.append(f"curve: no {ten}-year point")
    for k, need in (("week", ("d", "it")), ("news", ("d", "t")), ("reg", ("d", "ag", "t"))):
        v = t.get(k, [])
        if not isinstance(v, list): e.append(f"{k} must be a list"); continue
        for i, it in enumerate(v):
            if not (isinstance(it, dict) and all(ne(it.get(x)) for x in need)): e.append(f"{k}[{i}] needs {', '.join(need)}")
            elif k == "week" and ("t" in it and not isinstance(it["t"], str) or "mq" in it and not isinstance(it["mq"], bool)): e.append(f"week[{i}] t/mq types")
    co = t.get("commentary")
    if co is not None:
        if not (isinstance(co, dict) and ne(co.get("byline")) and isinstance(co.get("note"), str)):
            e.append("commentary needs byline and note")
        else:
            rd, pn = co.get("read", []), co.get("panels", [])
            if "edition" in co and not ne(co["edition"]): e.append("commentary.edition empty")
            if not (isinstance(rd, list) and len(rd) <= 6 and all(ne(p) for p in rd)): e.append("commentary.read: up to 6 non-empty paragraphs")
            if not (isinstance(pn, list) and len(pn) <= 4 and all(isinstance(p, dict) and ne(p.get("t")) and ne(p.get("p")) for p in pn)): e.append("commentary.panels: up to 4 {t, p}")
            if not e:
                text = "\n".join([co["note"], *rd, *[x for p in pn for x in (p["t"], p["p"])]])
                for pat in RETIRED:
                    if re.search(pat, text, 0 if pat in CASE_SENSITIVE else re.I): e.append(f"commentary: retired or barred wording /{pat}/")
                if re.search(r"<[a-z/][^>]*>", text, re.I): e.append("commentary: carries markup; the tape holds plain text")
    extra = set(t) - {"meta", "classes", "rates", "curve", "week", "news", "reg", "paths", "commentary"}
    if extra: e.append("unknown top-level keys: " + ", ".join(sorted(extra)))
    return e


if __name__ == "__main__":
    try:
        tape = json.load(open(sys.argv[1], encoding="utf-8"))
    except Exception as x:
        print(f"TAPE FAIL: not JSON: {x}"); sys.exit(1)
    errs = check(tape)
    if errs:
        print("TAPE FAIL:\n  " + "\n  ".join(errs)); sys.exit(1)
    print("TAPE PASS"); sys.exit(0)
