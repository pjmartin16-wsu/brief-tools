"""Brief-side check of marketclose_desk.json (setnova-marketclose-3.0), 7 Oct 2026.
The Morning Brief run has no copy of the Desk, so it runs this (standard library only) before attaching the tape.
It mirrors src/schema/market.ts and tools/marketclose-check.ts; tests/engine/bridge.test.ts runs both on the same
files and requires the same verdict. Both read the barred wording from setnova_rules.json (13 Oct 2026), and both refuse
unknown top-level keys (the Desk ignored them until 13 Oct), and both hold the calendar to one event per row (14 Oct, Q6). Usage: python3 brief_tape_check.py marketclose_desk.json  -> exit 0 = PASS.
       python3 brief_tape_check.py --week rows.json         -> the calendar rows alone, before rendering (STEP 5c)."""
import hashlib, json, os, re, sys

RATE_IDS = {"ff", "effr", "sofr", "t2", "t5", "t10", "s210", "t30", "mtg30", "fhlb3", "cd12", "hysa"}
CLASSES = {"pol", "ref", "tsy", "mtg", "dep", "whl"}
NEEDED = ["t2", "t5", "t10", "cd12"]
# Barred commentary wording comes from setnova_rules.json, the one rule file shared with setnova_checks.py, the Desk's
# tools/marketclose-check.ts and releasecheck.py (13 Oct 2026). Its hash is pinned here, so this script's pin pins the rules.
RULES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "setnova_rules.json")
RULES_SHA256 = "b57c578cff621bfe45d466a97bb7bbff1ced94703ba0bd29decb13133afe6dbe"


def barred_patterns(path=RULES_FILE, want=RULES_SHA256):
    raw = open(path, "rb").read()
    if hashlib.sha256(raw).hexdigest() != want:
        raise ValueError(f"{os.path.basename(path)} does not match the pinned sha256 {want}")
    rules = json.loads(raw.decode("utf-8"))
    out = []
    for ref in rules["tape"]["commentary_barred_from"]:
        sec, key = ref.split(".", 1)
        out += [re.escape(x) if key.endswith("_literal") else x for x in rules[sec][key]]
    return out


# One event per calendar row (RELEASE-QUEUE Q6, 14 Oct 2026). On 13 and 14 Oct the tape's week[] rows joined events
# ("September PPI; 4- and 8-week bill auctions" under "8:30 ET"), so one time read as both events' time; the 13 Oct
# row also carried times inside the text, out of order. Each row now holds ONE event, its time only in "t" (from that
# event's own source, "" when the source gives none), same-day rows adjacent and in time order. A note on the same
# event goes in parentheses or after a comma, never after ";" or "·".
EVENT_JOIN = re.compile(r"\s*[;|\u00b7]\s*")
CLOCK_IN_TEXT = re.compile(r"\b\d{1,2}:\d{2}\b")
T_FORMAT = re.compile(r"^(\d{1,2}):(\d{2})(?: ([ap])\.m\.)? ET$")


def et_minutes(t):
    """Minutes after midnight ET for a week[] time. A bare H:MM with H from 1 to 6 is p.m. (auction closes, the
    Beige Book): the calendar carries no 1-6 a.m. event without writing "a.m."."""
    m = T_FORMAT.match(t)
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if ap == "a": h = 0 if h == 12 else h
    elif ap == "p": h = h if h == 12 else h + 12
    elif 1 <= h <= 6: h += 12
    return h * 60 + mi


def week_errors(week):
    e, seen, prev = [], [], None
    for i, w in enumerate(week):
        if not (isinstance(w, dict) and isinstance(w.get("it"), str) and isinstance(w.get("d"), str) and isinstance(w.get("t", ""), str)):
            continue
        it, d, t = w["it"], w["d"], w.get("t", "")
        if EVENT_JOIN.search(it): e.append(f"week[{i}] joins more than one event (';', '|' or a middle dot): one event per row")
        if CLOCK_IN_TEXT.search(it): e.append(f"week[{i}] carries a time inside the event text: the time goes in t only")
        if t and not T_FORMAT.match(t): e.append(f"week[{i}].t {t!r} is not 'H:MM ET', 'H:MM a.m. ET' or 'H:MM p.m. ET'")
        if d != (seen[-1] if seen else None):
            if d in seen: e.append(f"week[{i}] {d!r} reappears after another day: same-day rows must be adjacent")
            seen.append(d); prev = None
        if t and T_FORMAT.match(t):
            now = et_minutes(t)
            if prev is not None and now < prev: e.append(f"week[{i}] {d} {t} comes after a later time the same day: order same-day rows by time")
            prev = now
    return e


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
    if isinstance(t.get("week"), list): e += week_errors(t["week"])
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
                for pat in barred_patterns():
                    if re.search(pat, text, re.I): e.append(f"commentary: retired or barred wording /{pat}/")
                if re.search(r"<[a-z/][^>]*>", text, re.I): e.append("commentary: carries markup; the tape holds plain text")
    extra = set(t) - {"meta", "classes", "rates", "curve", "week", "news", "reg", "paths", "commentary"}
    if extra: e.append("unknown top-level keys: " + ", ".join(sorted(extra)))
    return e


def week_main(path):
    """--week ROWS.json: the calendar rows alone ([{"d","it","t"}, ...]), checked BEFORE rendering (STEP 5c), so a joined
    row is fixed in the data object before either edition prints it, not found on the tape after the send."""
    try:
        rows = json.load(open(path, encoding="utf-8"))
    except Exception as x:
        print(f"WEEK FAIL: not JSON: {x}"); return 1
    if not (isinstance(rows, list) and rows and all(isinstance(w, dict) and all(isinstance(w.get(k), str) and w.get(k) for k in ("d", "it")) for w in rows)):
        print('WEEK FAIL: expected a non-empty list of {"d","it","t"} rows'); return 1
    errs = week_errors(rows)
    if errs:
        print("WEEK FAIL:\n  " + "\n  ".join(errs)); return 1
    print(f"WEEK PASS ({len(rows)} rows, one event each)"); return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--week":
        sys.exit(week_main(sys.argv[2]))
    try:
        tape = json.load(open(sys.argv[1], encoding="utf-8"))
    except Exception as x:
        print(f"TAPE FAIL: not JSON: {x}"); sys.exit(1)
    try:
        errs = check(tape)
    except (OSError, ValueError) as x:
        print(f"TAPE FAIL: rules file: {x}"); sys.exit(1)
    if errs:
        print("TAPE FAIL:\n  " + "\n  ".join(errs)); sys.exit(1)
    print("TAPE PASS"); sys.exit(0)
