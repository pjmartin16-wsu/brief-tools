#!/usr/bin/env python3
"""
releasecheck.py — mechanical pre-flight for anything leaving this workspace.

WHY THIS EXISTS
---------------
Built 2026-08-28, after an insurance submission went out in draft carrying two
false statements about the firm's own controls and one legal proposition that
the firm's counsel brief had already identified and corrected. None of them were
caught by a gate; all of them were caught by a human who happened to ask for one
more review. That is the same shape as the layout defects that produced
layoutaudit.py: the eye slides over a sentence that reads well.

Sibling to 06_Projects/_tools/layoutaudit.py. Same discipline:
  * every check encodes a defect that actually shipped or nearly shipped
  * the fixture at test/fixture-bad-release.md must FAIL on every check
  * a check that stops firing on the fixture has silently broken

WHAT IT CANNOT DO
-----------------
It cannot tell you whether a legal proposition is TRUE. Nothing mechanical can.
What it does instead is detect that a document makes statutory or regulatory
claims at all, and refuse to pass silently — forcing the primary-source re-read
that would have caught the $100mm error. Same for absolute claims: it cannot
know whether "no PII, at any point" is true, only that it is the kind of sentence
that has been wrong before and must be checked against the claims register.

USAGE
-----
    python3 releasecheck.py <file> [<file> ...]
    python3 releasecheck.py --self-test          # run the fixture

Accepts .md, .html, .txt. HTML is READ FROM A RENDERED BROWSER DOM (Playwright,
same engine layoutaudit.py uses) and falls back to a static strip only if no
browser is available — in which case it raises a COVER finding rather than
passing silently. Earned 2026-08-31: the static strip read 310 of 225,200
characters of the Treasury Desk (0.138%) and printed PASS.

2026-08-31 additions, all from defects that were live on disk that night:
  RETRACT  withdrawn formulations, CHECK — they may appear inside a correction.
           Two action lists were still ORDERING a retracted construction.
  NEVER    the literal do-not-say strings from CLAIMS.md, five of which had
           been prose-only since adoption.
  PRICE    superseded prices and the ladder rungs killed 26 Aug — the one
           recurring outbound defect class this gate had no check for.
  VERSION  a self-identifying version string disagreeing with the filename.
  COVER    the scanner read almost none of this file.
2026-09-16 additions:
  BRACKET  square-bracketed placeholder or drafting note on an outbound surface.
           The 10 Sep broker reply shipped with two of them in the body.
  TENOR    a named tenor used as a reference point. The 10 Sep sample board
           pack named "the five-year par level" as THE reference and passed.
2026-09-16 (evening) additions:
  VERB     the rest of the Stage 7 verb list of the onboarding process (thirteen
           words; the dry run found half were read by eye). BLOCK on a client
           surface; CHECK on a line that negates it or in a document that frames
           withholding — the letter's own reservations must not block the letter.
           The self-test now proves EVERY VERDICT and SHELF pattern fires on the
           fixture, and that test/fixture-clean-release.md — the firm's own
           scope reservations and referral lines — raises NO blocking finding.
The RELEASECHECK: INTERNAL marker now suppresses only the OUTBOUND-SURFACE
checks and reports SKIPPED, not PASS; the integrity checks still run, because
"internal" is where the truncated SR 26-2 quote got into the claims register.

EXIT CODES
    0  clean — SCANNED and no findings
    1  findings present, OR the file was SKIPPED for the INTERNAL marker
       (a skip is not a pass; see scan())
    2  bad invocation / self-test failed
"""

import html
import os
import re
import sys

# --------------------------------------------------------------------------
# Terms. Kept as data so the list is auditable at a glance and cheap to extend
# when the next defect ships.
# --------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 13 Oct 2026 (checker-efficiency #5): the pattern lists below now live in
# setnova_rules.json, the ONE rule file this gate shares with the Morning Brief's
# setnova_checks.py, brief_tape_check.py and the Desk's tape check. The file is
# looked for beside this script, then in setnova-tools/ beside it (the OneDrive
# mirror of github.com/pjmartin16-wsu/setnova-tools). Its SHA-256 is pinned here:
# a rules change takes effect only when this pin moves, and a mismatch is an
# error, never a silent pass. The comments above each list still say why it exists.
import hashlib as _hashlib, json as _json
RULES_SHA256 = "b57c578cff621bfe45d466a97bb7bbff1ced94703ba0bd29decb13133afe6dbe"


def _load_rules():
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "setnova_rules.json"), os.path.join(here, "setnova-tools", "setnova_rules.json")):
        if os.path.exists(cand):
            raw = open(cand, "rb").read()
            got = _hashlib.sha256(raw).hexdigest()
            if got != RULES_SHA256:
                sys.exit(f"RULES ERROR — {cand} sha256 {got} != pinned {RULES_SHA256}")
            return _json.loads(raw.decode("utf-8"))["release"]
    sys.exit("RULES ERROR — setnova_rules.json not found beside releasecheck.py or in setnova-tools/")


_RL = _load_rules()

REAL_INSTITUTIONS = _RL["real_institutions_literal"]

# Figures from the retired ~$2.1B sample book, plus the second book found on 26 Aug.
RETIRED_FIGURES = _RL["retired_figures_re"]

BANNED_VOCAB = _RL["banned_vocab_re"]

# Conclusions. The tool rules put numbers in front of the client, never verdicts.
VERDICT = _RL["verdict_re"]

# Shelf B — withheld entirely pending the RCW 21.20 opinion.
SHELF_B = _RL["shelf_b_re"]

# VERB — the rest of the Stage 7 verb gate (onboarding process v0.1, Stage 7:
# "recommend, should buy, should sell, appropriate security, optimal, best
# maturity, target investment, extend, shorten, replace, hedge with, reinvest,
# duration strategy"). Added 2026-09-16 (evening) after the onboarding dry run
# found the process listed thirteen words and this gate mechanised about half;
# the other half were read by eye. These words appear legitimately in the
# firm's OWN scope reservations ("we do not recommend"), in Schedule 3's list of
# the questions it will not answer, and in a withheld finding — so, unlike
# VERDICT, a VERB hit is downgraded to CHECK on a LINE that negates or frames
# it (NEGATED_CONTEXT). Deliberately NOT the document-level downgrade SHELF
# uses: a delivery memo with three withheld lines still contains the sentence
# "the bank should reinvest into the two-year", and that sentence must BLOCK.
# The first run on the letter (v0.2) was the calibration: three BLOCKs, all
# three the firm describing what it does not do; each now carries a line
# marker (a reservation, a question list, an authority-matrix "No").
VERB = _RL["verb_re"]
# A line that negates or frames the verb is the reservation, not the offence.
NEGATED_CONTEXT = re.compile(
    r"\b(?:do|does|did|will|would|shall|can|cannot|could|must|may)\s+not\b|\bn't\b|"
    r"\bnever\b|\bno recommendation|\bnot (?:a |an )?recommend|\bwithout\b|"
    r"\bwithheld|\bwithhold|\boutside (?:the )?(?:scope|services)|\bnot make\b|"
    r"\bany question that asks|\bquestions? (?:that|which) asks?|\bdescribe any option as|"
    r"\brank options|\breserved (?:matters?|to)|\|\s*No\s*\||"
    r"\basked (?:us |me )?(?:what|where|whether|how|if|which)\b|"
    r"\b(?:are|is) the (?:committee|institution|board)'?s\b|\bremains? with\b|\bmanagement determines\b", re.I)

# Absolute claims. Not wrong by nature — wrong when unscoped. Both false control
# statements in the 28 Aug insurance draft were sentences of exactly this shape.
ABSOLUTE = _RL["absolute_re"]

# Provenance that belongs in the data object, not on a reader-facing page.
PROVENANCE = _RL["provenance_re"]

# Statutory / regulatory citation shapes. Presence is not a defect — it is a
# REQUIREMENT TO RE-READ THE PRIMARY SOURCE, which is the control that was
# missing when a corrected error was restated from memory.
CITATIONS = _RL["citations_re"]

# Contexts in which Shelf B vocabulary is CORRECT rather than a defect: a
# document that names what the practice withholds must be able to name it.
# Tuned in 2026-08-28 after the first run flagged the insurance submission's
# "withheld pending counsel" column as a BLOCK. A checker that cries wolf on
# correct content teaches its reader to skip blocking findings, which is worse
# than not having the check — the same lesson layoutaudit.py learned when it
# flagged 26 correctly-behaving tables.
# Formulations that have been RETRACTED. They may legitimately appear inside a
# correction ("this previously read X — it is withdrawn"), so this is a CHECK,
# not a BLOCK: the instruction is to confirm the phrase appears only in a
# corrective context.
#
# ⛔ THE LIST LIVES OUTSIDE THIS FILE, AND THAT IS A WALL REQUIREMENT.
# Added 2026-08-31; moved out the same night. Every entry originally hard-coded
# here was a Setnova CAPITAL formulation with zero occurrences anywhere on the
# Advisory side — so this shared gate, which runs on Advisory client
# deliverables and is the operational substance behind the sellable
# "Confidence in the Numbers" capability, carried Capital's private retracted
# claims in plain text. The wall policy requires the separation to be
# "technical, not just procedural."
#
# So: the tool ships with NO retracted phrases. It loads them from the nearest
# `retracted.txt` found by walking UP from the scanned file's own directory —
# which means a Capital document is checked against Capital's list, an Advisory
# document against Advisory's, and neither list is ever loaded for the other.
# One phrase per line; blank lines and lines starting with # are ignored.
RETRACTED_FILENAME = "retracted.txt"


def load_retracted(path):
    """Nearest retracted.txt at or above the scanned file. Returns [] if none."""
    d = os.path.dirname(os.path.abspath(path))
    seen = []
    while True:
        cand = os.path.join(d, RETRACTED_FILENAME)
        if os.path.exists(cand):
            for line in open(cand, encoding="utf-8", errors="ignore"):
                line = line.strip()
                if line and not line.startswith("#"):
                    seen.append(line)
            return seen
        parent = os.path.dirname(d)
        if parent == d:
            return seen
        d = parent


# Literal do-not-say strings from CLAIMS.md. Each was live in a shipped or
# nearly-shipped document. Mechanized 2026-08-31 — five of the six had been
# prose-only since they were adopted, and the NCUA one had sat as "added to the
# release scanner's to-do" since 30 Aug.
NEVER_SAY = _RL["never_say_re"]

# Prices superseded by the 25/26 Aug corrections, plus the rungs of the ladder
# the 26 Aug pricing sheet explicitly killed ("A ladder invites a buyer to shop
# down it, and the cheapest rung sets the price of everything above"). Added
# 2026-08-31: superseded PRICES were the one recurring outbound defect class the
# gate had no check for, and the document project memory calls the highest-risk
# stale doc in the workspace passed with 0 blocking findings because of it.
SUPERSEDED_PRICE = _RL["superseded_price_re"]

# A bracket in text that is about to leave. Added 2026-09-16, earned 2026-09-10:
# the reply to the firm's insurance broker went out with two bracketed
# drafting notes still in the body ("[Delete any that are not yet enforced
# and say ...]", "[If Business Premium: ...]") and the broker answered "Thanks
# this is helpful." A DRAFT'S BRACKETS ARE NOT INVISIBLE TO THE RECIPIENT.
# Markdown links "[text](url)" and bare numeric references "[3]" are excluded;
# everything else in square brackets is a placeholder or a note to self.
# BLOCK on an outbound surface. A document that declares itself a template
# (see TEMPLATE_CONTEXT) is downgraded to CHECK: the brackets are the
# placeholders, and the rule there is that every one is resolved before the
# instance is sent — which is exactly what the CHECK asks the reader to confirm.
BRACKET = re.compile(r"\[(?!\d{1,3}\])[^\[\]\n]{1,160}\](?!\()")
TEMPLATE_CONTEXT = re.compile(
    r"bracketed text is completed|completed per engagement|template placeholder|"
    r"placeholders? (?:is|are) (?:completed|resolved|filled)|this template", re.I)

# A named tenor used as a reference point. Added 2026-09-16, earned 2026-09-10:
# the sample board pack in the counsel package described "the five-year par
# level of 3.71%" as the reference, and this gate did not see it. Reading a
# public number is measurement; naming it THE reference, drawing the eye to
# it, or grading the book against it is advice — the reason the live Desk has
# no default view and no verdict colours. Two shapes: tenor then reference
# word, and reference word then tenor, within one sentence.
_TENOR = r"(?:\d{1,2}|one|two|three|five|seven|ten|twenty|thirty)[- ]?(?:year|yr|month|mo|Y)\b"
_REFWORD = (r"(?:reference(?: point| rate| level)?|benchmark|anchor|par level|"
            r"the level to (?:watch|beat)|pivot|target(?: level)?|watch level|"
            r"the number that matters|hurdle)")
TENOR_REFERENCE = [
    r"\b" + _TENOR + r"[^.\n]{0,60}\b" + _REFWORD + r"\b",
    r"\b" + _REFWORD + r"[^.\n]{0,60}\b" + _TENOR,
]

WITHHELD_CONTEXT = re.compile(
    r"withheld|not sold|does not sell|excluded|expressly not|no securities|"
    r"pending (?:a )?(?:securities[- ])?counsel|Shelf B|out of scope|never sold|"
    r"absent from the (?:software|price list)|outside (?:the )?scope|outside the services|"
    r"not make (?:that |any )?recommendations?|do not make recommendations|"
    r"contains no recommendation|management determines", re.I)

# A LINE that is about a past defect legitimately contains the defect. Same
# principle as WITHHELD_CONTEXT, applied per line rather than per document, and
# added 2026-08-31 when reading the RENDERED DOM (rather than 0.138% of the
# source) surfaced the Treasury Desk's own build notes — "On the old $2.1B book
# it FAILED", "from the prototype ('in the zone', 'recommended:') is
# deliberately [excluded]". Those are correct discipline, not defects, and
# blocking on them is exactly how a checker teaches its reader to skip BLOCK.
# Downgrades to CHECK; never suppresses, because the reader still has to look.
CORRECTIVE_CONTEXT = re.compile(
    r"supersed|retired|the old |previously|corrected|deliberately|excluded|"
    r"draft figure|no longer|used to |former|withdrawn|withheld|withhold|FAILED|stale|"
    r"do not (?:say|write|use)|never (?:say|write)|must not", re.I)
DOWNGRADABLE = {"FIG", "VERDICT", "NEVER", "PRICE", "VOCAB", "TENOR", "BRACKET", "SHELF"}

SEVERITY = {
    "INST": "BLOCK", "FIG": "BLOCK", "SHELF": "BLOCK", "VERDICT": "BLOCK",
    "NEVER": "BLOCK", "COVER": "BLOCK", "BRACKET": "BLOCK", "TENOR": "BLOCK",
    "VERB": "BLOCK",
    "VOCAB": "WARN", "ABS": "WARN", "PROV": "WARN", "BRAND": "WARN",
    "PRICE": "WARN", "VERSION": "WARN",
    "CITE": "CHECK", "RETRACT": "CHECK",
}

EXPLAIN = {
    "INST": "real institution named — confirm this document may carry it (Geri rule: written approval)",
    "FIG": "figure from a retired sample book — the canonical book is ~$2.75B",
    "VOCAB": "banned vocabulary — use CD maturity schedule / tranche / laddering / maturity concentration",
    "VERDICT": "verdict language — the tool rules give numbers, not conclusions",
    "SHELF": "Shelf B language — withheld pending the RCW 21.20 opinion",
    "VERB": ("a Stage 7 verb-gate word (recommend / should buy or sell / appropriate "
             "security / optimal / best maturity / target investment / reinvest / "
             "hedge with / duration strategy / extend, shorten, replace a security or "
             "maturity) — rewrite as a finding or a management question, or cut"),
    "ABS": "unscoped absolute claim — verify against CLAIMS.md, or scope it",
    "PROV": "provenance leaking onto a reader-facing surface",
    "BRAND": 'bare masterbrand as text branding — always "Setnova Advisory"',
    "CITE": "statutory citation — RE-READ THE PRIMARY SOURCE before this ships",
    "RETRACT": ("RETRACTED formulation — confirm it appears ONLY inside a correction. "
                "An action list that ORDERS a retracted construction is the failure "
                "this check exists for (31 Aug)"),
    "NEVER": "do-not-say string from CLAIMS.md — this exact wording has been ruled out",
    "PRICE": "superseded price or a rung of the ladder killed 26 Aug — check against current pricing",
    "VERSION": "version string disagrees with the filename — v2 and v2.1 were indistinguishable in a browser tab",
    "BRACKET": ("square-bracketed text on an outbound surface — a placeholder or a "
                "drafting note. Resolve it; the 10 Sep broker reply went out with two "
                "of these in the body"),
    "TENOR": ("a named tenor used as a reference point — reading a public number is "
              "measurement, naming it THE reference or grading against it is advice "
              "(the 10 Sep sample pack's 'five-year par level' defect)"),
    "COVER": ("the scanner read almost none of this file — it generates its text at "
              "runtime, so a PASS here would certify a document that was never read"),
}


def rendered_text(path):
    """Read what the READER sees, from a real browser, not from the static source.

    Earned 2026-08-31. visible_text() strips <script>, and the Treasury Desk is a
    single-file application that builds ~88KB of reader-facing text at runtime
    from 195KB of script — so the scanner was reading 310 of 225,200 characters
    (0.138%) and printing PASS. That is G9 — "a gate that inspects a different
    artifact than the one delivered proves nothing" — instantiated inside the
    release gate itself. Returns None if a browser is unavailable, and the caller
    then raises a COVER finding rather than passing silently."""
    if not path.lower().endswith((".html", ".htm")):
        return None
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    for exe in ("/opt/pw-browsers/chromium", None):
        try:
            with sync_playwright() as p:
                b = (p.chromium.launch(executable_path=exe) if exe
                     else p.chromium.launch())
                try:
                    pg = b.new_page()
                    pg.goto("file://" + os.path.abspath(path), wait_until="networkidle")
                    # textContent, not innerText: the Desk renders six tabs and
                    # only one is visible on arrival, so innerText misses five
                    # sixths of the document — including the footer that still
                    # said "v2.2". A reader can reach every tab; the gate must
                    # see everything the DOM holds, not only what is on screen.
                    return pg.evaluate(
                        "document.body ? document.body.textContent : ''")
                finally:
                    b.close()
        except Exception:
            continue
    return None


def visible_text(path):
    """Return only what a reader sees. HTML comments, scripts, styles and
    attribute values are stripped, so a term inside a class name or a source
    comment is not a finding — that false-positive class is what made the
    layout audit untrustworthy until it was tuned out."""
    raw = open(path, encoding="utf-8", errors="ignore").read()
    if path.lower().endswith((".html", ".htm")):
        raw = re.sub(r"(?is)<!--.*?-->", " ", raw)
        raw = re.sub(r"(?is)<(script|style|svg)[^>]*>.*?</\1>", " ", raw)
        raw = re.sub(r"(?s)<[^>]+>", "\n", raw)
        raw = html.unescape(raw)
    return raw


# A document that is ABOUT the banned terms — the claims register, a boundary
# schedule, a post-mortem — legitimately contains them. It declares itself with
# the marker below in its first 40 lines. Made explicit and self-declaring
# rather than a hidden filename list, so the exemption is visible to anyone
# reading the file and cannot be inherited silently by a copy. The fixture is
# deliberately NOT exempt.
INTERNAL_MARKER = re.compile(r"RELEASECHECK\s*:\s*INTERNAL", re.I)


LAST_COVERAGE = (0, "")   # (characters of reader-facing text scanned, how) for the file just scanned


def scan(path):
    # The marker is checked against the RAW file, not the stripped text. In HTML
    # the natural place to put it is a comment — and visible_text() strips
    # comments, so checking the stripped copy silently never found it. Caught
    # 2026-08-28 by running this tool on the first internal HTML document
    # written after it shipped. A check whose own precondition is unreachable
    # fails exactly the way a silent skip does.
    raw = open(path, encoding="utf-8", errors="ignore").read()
    # Earned 2026-08-31, two ways. (a) This path used to return no findings,
    # which printed "PASS — no findings", byte-identical to a document that was
    # actually scanned and actually clean; ten live files declare the marker and
    # a verification sweep read their PASSes as a clean bill of health. (b) More
    # importantly, a blanket exemption is the wrong shape. The marker exists
    # because a register or a post-mortem legitimately NAMES the restricted
    # terms — it does not make a RETRACTED formulation or a stale version string
    # acceptable there. "Internal" is exactly where the truncated SR 26-2 quote
    # got into the register that outbound documents are written FROM, and the
    # two action lists still ordering a retracted construction are both marked
    # INTERNAL. So the marker now suppresses the OUTBOUND-SURFACE checks only;
    # the integrity checks (RETRACT, VERSION, COVER) still run, at CHECK/WARN.
    internal = bool(INTERNAL_MARKER.search(raw[:4000]))

    # Prefer the rendered DOM; fall back to the static strip and say so loudly.
    text = rendered_text(path)
    rendered = text is not None
    if not rendered:
        text = visible_text(path)
    # Third re-review, 15 Oct 2026: the <title> shows in the browser tab and the print header but was never scanned
    # ("We guarantee you will earn 12%" passed). It is reader-facing text; it is checked with the body.
    if path.lower().endswith((".html", ".htm")):
        tm_ = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
        if tm_ and tm_.group(1).strip():
            text = html.unescape(re.sub(r"\s+", " ", tm_.group(1)).strip()) + "\n" + text
    text = text.replace("\ufeff", "")   # a byte-order mark is not text (a BOM-only file read as 1 character)
    global LAST_COVERAGE
    LAST_COVERAGE = (len(text.strip()), "rendered" if rendered else "static strip")
    lines = text.split("\n")
    found = []
    # Coverage. An HTML file whose reader-facing text is a rounding error of its
    # source is a file this scanner did not read.
    if path.lower().endswith((".html", ".htm")) and not rendered and len(raw) > 50000:
        if len(text) < 0.05 * len(raw):
            found.append(("COVER", f"{len(text)} of {len(raw)} chars "
                                   f"({100.0 * len(text) / len(raw):.3f}%)", 1,
                          "static strip only — no browser available to render this file"))

    def add(kind, pattern, flags=0, label=None):
        for i, line in enumerate(lines, 1):
            m = re.search(pattern, line, flags)
            if m:
                snippet = line.strip()
                if len(snippet) > 110:
                    start = max(0, m.start() - 40)
                    snippet = "…" + snippet[start:start + 110].strip() + "…"
                if kind in DOWNGRADABLE and CORRECTIVE_CONTEXT.search(line):
                    kind = kind + "?"        # corrective context — see report()
                found.append((kind, label or m.group(0).strip(), i, snippet))

    outbound = not internal
    for term in (REAL_INSTITUTIONS if outbound else []):
        # Word-bounded so "staggering" never matches "Geri" and a variable
        # name like valTxt never matches "VALT" — both were real false
        # positives in the 26 Aug manual sweep.
        add("INST", r"\b" + re.escape(term) + r"\b", re.I, term)
    for pat in (RETIRED_FIGURES if outbound else []):
        add("FIG", pat, re.I)
    for pat in (BANNED_VOCAB if outbound else []):
        add("VOCAB", pat, re.I)
    for pat in (VERDICT if outbound else []):
        add("VERDICT", pat, re.I)
    for pat in (SHELF_B if outbound else []):
        add("SHELF", pat, re.I)
    # VERB: line-level negation or framing downgrades to CHECK ("VERB?"); there
    # is no document-level downgrade for VERB (see the comment on VERB).
    for pat in (VERB if outbound else []):
        for i, line in enumerate(lines, 1):
            m = re.search(pat, line, re.I)
            if m:
                snippet = line.strip()
                if len(snippet) > 110:
                    start = max(0, m.start() - 40)
                    snippet = "…" + snippet[start:start + 110].strip() + "…"
                kind = "VERB?" if (NEGATED_CONTEXT.search(line) or CORRECTIVE_CONTEXT.search(line)) else "VERB"
                found.append((kind, m.group(0).strip(), i, snippet))
    # Drop SHELF hits whose own line OR immediate neighbours declare the item
    # withheld. The window is needed because a table cell and its column header
    # are different lines: the first run blocked the insurance submission's
    # "Withheld pending counsel" column because the header sat two lines above
    # the cell. Kept deliberately narrow — a wide window would suppress real
    # findings anywhere near the word "excluded".
    # SHELF severity is decided at DOCUMENT level, not line level.
    # Two line-window attempts failed: a table cell and its "Withheld pending
    # counsel" column header sit far apart once HTML is stripped, and any window
    # wide enough to bridge them would suppress genuine findings elsewhere in
    # the file. The real distinction is not proximity — it is what KIND of
    # document this is. One that explicitly frames a withheld list is declaring
    # a boundary; one with no such framing is offering the thing. So a document
    # that frames withholding downgrades SHELF from BLOCK to CHECK and asks the
    # reader to confirm placement, rather than falsely blocking a correct file.
    doc_frames_withholding = bool(WITHHELD_CONTEXT.search(text))
    for pat in (ABSOLUTE if outbound else []):
        add("ABS", pat, re.I)
    for pat in (PROVENANCE if outbound else []):
        add("PROV", pat)
    # Citations collapse to ONE finding listing the distinct authorities. Eight
    # separate CITE lines on a legal document is noise; the instruction is the
    # same either way — open every one of them in this pass.
    cites, cite_line = [], None
    for pat in (CITATIONS if outbound else []):
        for i, line in enumerate(lines, 1):
            m = re.search(pat, line)
            if m:
                c = m.group(0).strip()
                if c not in cites:
                    cites.append(c)
                    cite_line = cite_line or i
    if cites:
        found.append(("CITE", ", ".join(sorted(cites)), cite_line or 1,
                      f"{len(cites)} distinct authorit"
                      f"{'y' if len(cites) == 1 else 'ies'} cited in this document"))
    # Bare masterbrand: SETNOVA in caps NOT followed by Advisory/Capital.
    if outbound:
        add("BRAND", r"\bSETNOVA\b(?!\s*(?:ADVISORY|CAPITAL|·))")
    for pat in load_retracted(path):
        add("RETRACT", pat, re.I)
    for pat in (NEVER_SAY if outbound else []):
        add("NEVER", pat, re.I)
    for pat in (SUPERSEDED_PRICE if outbound else []):
        add("PRICE", pat, re.I)
    for pat in (TENOR_REFERENCE if outbound else []):
        add("TENOR", pat, re.I)
    # Brackets: BLOCK on an outbound surface; CHECK on a self-declared template.
    if outbound:
        is_template = bool(TEMPLATE_CONTEXT.search(text))
        for i, line in enumerate(lines, 1):
            m = BRACKET.search(line)
            if m:
                snippet = line.strip()
                if len(snippet) > 110:
                    start = max(0, m.start() - 40)
                    snippet = "…" + snippet[start:start + 110].strip() + "…"
                found.append(("BRACKET?" if is_template else "BRACKET",
                              m.group(0).strip()[:80], i, snippet))

    # Version string vs filename. One line, and this was the fourth occurrence:
    # Desk v2.3a's title AND banner were corrected on 31 Aug and its visible
    # footer still read "v2.2"; DFI v2 and v2.1 both title as "v2".
    fv = re.search(r"_v(\d+(?:\.\d+)*[a-z]?)_", os.path.basename(path), re.I)
    if fv and path.lower().endswith((".html", ".htm")):
        want = fv.group(1)
        title = re.search(r"<title>(.*?)</title>", raw, re.S | re.I)
        title = html.unescape(title.group(1)).strip() if title else ""
        # Only SELF-IDENTIFYING version strings: a proper-noun run immediately
        # followed by the version, e.g. "Setnova Treasury Desk v2.2". A bare
        # changelog line ("v2.2b — fixed the table overflow") is history, not a
        # claim about what this file is, and flagging it buries the real hit.
        seen = set(m.group(2) for m in re.finditer(
            r"\b([A-Z][\w&'’.]*(?:\s+[A-Z0-9][\w&'’.]*){0,4})\s+v(\d+(?:\.\d+)*[a-z]?)\b",
            text))
        if title and not re.search(r"\bv" + re.escape(want) + r"\b", title, re.I):
            found.append(("VERSION", f"title says {title!r}, filename says v{want}",
                          1, "<title> does not carry this file's version"))
        wrong = sorted(v for v in seen if v.lower() != want.lower())
        if wrong:
            found.append(("VERSION", f"the document also identifies itself as "
                                     f"v{', v'.join(wrong)}; filename says v{want}", 1,
                          "a self-identifying version string disagrees with the filename"))

    # De-duplicate on (kind, line) so one bad line reports once per class.
    seen, out = set(), []
    for f in found:
        key = (f[0], f[2])
        if key not in seen:
            seen.add(key)
            out.append(f)
    return sorted(out, key=lambda f: (f[2], f[0])), doc_frames_withholding, internal


def report(path, findings, shelf_downgraded=False, internal=False):
    name = os.path.basename(path)
    if internal:
        print(f"SKIPPED (INTERNAL) — {name}: the outbound-surface checks were "
              f"suppressed by the RELEASECHECK: INTERNAL marker. THIS IS NOT A "
              f"PASS. Integrity checks (RETRACT, VERSION, COVER) still ran"
              f"{' and found nothing' if not findings else ''}.")
        print("  An outbound-class document must pass with NO marker. If this "
              "document is going to a third party, remove the marker and re-run.")
        if not findings:
            return
    elif not findings:
        print(f"PASS — {name}: no findings.")
        return
    sev = dict(SEVERITY)
    exp = dict(EXPLAIN)
    if shelf_downgraded:
        sev["SHELF"] = "CHECK"
        exp["SHELF"] = ("Shelf B term — this document frames a withheld list, so "
                        "confirm the term sits in that list and is not being offered")
    sev["VERB?"] = "CHECK"
    exp["VERB?"] = (EXPLAIN["VERB"] + " — BUT this line negates or frames it, so it is "
                    "downgraded: confirm it is the reservation, not the offence")
    for k in list(DOWNGRADABLE):
        sev[k + "?"] = "CHECK"
        exp[k + "?"] = (exp[k] + " — BUT this line reads as a CORRECTION or an "
                        "exclusion note, so it is downgraded: confirm it is "
                        "describing the defect, not committing it")
    exp["BRACKET?"] = (exp["BRACKET"] + " — BUT this document declares itself a "
                       "TEMPLATE, so it is downgraded: confirm every bracket is "
                       "resolved in the instance that is actually sent")
    order = {"BLOCK": 0, "WARN": 1, "CHECK": 2}
    findings.sort(key=lambda f: (order[sev[f[0]]], f[2]))
    blocks = sum(1 for f in findings if sev[f[0]] == "BLOCK")
    print(f"\n{name} — {len(findings)} finding(s), {blocks} blocking:\n")
    for kind, hit, ln, snippet in findings:
        print(f"  [{sev[kind]}·{kind}] line {ln} — {hit}")
        print(f"          {snippet}")
        print(f"          → {exp[kind]}")
    print()


def self_test():
    fixture = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "test", "fixture-bad-release.md")
    if not os.path.exists(fixture):
        print(f"SELF-TEST FAILED — fixture missing at {fixture}")
        return 2
    fx, _, _ = scan(fixture)
    kinds = {f[0].rstrip("?") for f in fx}
    # COVER and VERSION are HTML-only structural checks; the fixture is .md, so
    # they are exercised by their own HTML fixture below rather than here.
    expected = set(SEVERITY) - {"COVER", "VERSION"}
    missing = expected - kinds
    if missing:
        print("SELF-TEST FAILED — these checks did not fire on the known-bad "
              f"fixture: {', '.join(sorted(missing))}")
        print("A check that stops firing has silently broken. Fix it before "
              "trusting any PASS from this tool.")
        return 2
    # Structural checks get their own HTML fixture — a .md file cannot exercise
    # a <title>/filename disagreement or a runtime-generated body.
    hfix = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "test", "fixture-bad_v9.9_2026-01-01.html")
    if not os.path.exists(hfix):
        print(f"SELF-TEST FAILED — HTML fixture missing at {hfix}")
        return 2
    hx, _, _ = scan(hfix)
    hkinds = {f[0].rstrip("?") for f in hx}
    hmissing = {"VERSION"} - hkinds
    if hmissing:
        print("SELF-TEST FAILED — these structural checks did not fire on the "
              f"known-bad HTML fixture: {', '.join(sorted(hmissing))}")
        return 2
    # Pattern-level: every VERDICT and SHELF pattern must fire on the fixture by
    # itself. Kind-level passing hides a pattern that has stopped matching.
    ftext = open(fixture, encoding="utf-8").read()
    dead = [pat for pat in VERDICT + SHELF_B + VERB if not re.search(pat, ftext, re.I)]
    if dead:
        print("SELF-TEST FAILED — these verb-gate patterns match nothing in the "
              f"fixture: {', '.join(dead)}")
        return 2
    # Negative control: the firm's own scope reservations, referral lines and
    # withheld findings must NOT block. A gate that blocks the sentence the
    # practice is built on teaches its reader to ignore BLOCK.
    clean = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "test", "fixture-clean-release.md")
    if not os.path.exists(clean):
        print(f"SELF-TEST FAILED — clean fixture missing at {clean}")
        return 2
    cx, cdown, _ = scan(clean)
    csev = dict(SEVERITY)
    if cdown:
        csev["SHELF"] = "CHECK"
    cblocks = [f for f in cx if not f[0].endswith("?") and csev.get(f[0]) == "BLOCK"]
    if cblocks:
        print("SELF-TEST FAILED — the clean fixture raised blocking findings: "
              + "; ".join(f"[{f[0]}] {f[1]} (line {f[2]})" for f in cblocks))
        return 2
    print(f"SELF-TEST PASSED — all {len(expected)} content checks fired on the "
          f"fixture ({', '.join(sorted(kinds))}), every one of the "
          f"{len(VERDICT) + len(SHELF_B) + len(VERB)} verb-gate patterns fired, VERSION fired "
          f"on the HTML fixture, and the clean fixture raised no blocking finding.")
    return 0


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    if args[0] == "--self-test":
        if len(args) > 1:   # second re-review: "--self-test file.md" exited 0 without checking file.md
            print("INPUT ERROR: --self-test takes no files; run the files without it"); return 2
        return self_test()

    rc = self_test()
    if rc != 0:
        return rc
    print()

    # 15 Oct 2026 (outside review CX-07): a requested file that did not exist printed "skip" and the run still exited 0,
    # so a typo in a path read as a clean release. A missing file is now an input error: exit 2, never a pass.
    worst, missing = 0, []
    for path in args:
        if not os.path.exists(path):
            print(f"MISSING — {path} not found: nothing was checked for it")
            missing.append(path)
            continue
        # Adversarial review of the CX-07 fix (15 Oct 2026): a folder crashed with a traceback, and an empty file or a
        # binary .docx printed "PASS — no findings" although no text was read. Zero coverage is an input error, never a pass.
        if os.path.isdir(path):
            print(f"MISSING — {path} is a folder: name the files to check"); missing.append(path); continue
        if os.path.splitext(path)[1].lower() not in (".html", ".htm", ".md", ".txt"):
            print(f"MISSING — {path}: not a text format this checker reads (.html, .htm, .md, .txt); export it first"); missing.append(path); continue
        rawb = open(path, "rb").read()
        if not rawb.strip():
            print(f"MISSING — {path} is empty: nothing to check"); missing.append(path); continue
        # Second re-review, 15 Oct: zip bytes renamed .txt and a NUL-filled .md passed. Text has no NUL bytes and decodes.
        try:
            rawb.decode("utf-8")
            is_text = b"\x00" not in rawb
        except UnicodeDecodeError:
            is_text = False
        if not is_text:
            print(f"MISSING — {path} is not UTF-8 text (binary content under a text extension)"); missing.append(path); continue
        findings, downgraded, internal = scan(path)
        if LAST_COVERAGE[0] == 0:
            # an HTML file of comments, scripts or markup only: no reader-facing text was read, so nothing was checked
            print(f"MISSING — {path}: no reader-facing text found ({LAST_COVERAGE[1]}); nothing was checked"); missing.append(path); continue
        print(f"coverage — {os.path.basename(path)}: {LAST_COVERAGE[0]:,} characters of reader-facing text scanned ({LAST_COVERAGE[1]})")
        report(path, findings, downgraded, internal)
        if findings or internal:
            worst = 1
    if missing:
        print(f"INPUT ERROR: {len(missing)} requested file(s) not found, unreadable or empty; this release is NOT checked.")
        return 2
    if worst:
        print("BLOCK findings must be resolved. WARN findings must be scoped or "
              "justified. CHECK findings mean: open the primary source and read "
              "it in this pass — a summary is not the source.")
    return worst


if __name__ == "__main__":
    sys.exit(main())
