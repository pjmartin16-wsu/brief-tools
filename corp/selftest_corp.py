"""Self-test for corp_build.py: rebuilding the 16 Nov 2026 corporate edition from its saved tape and supplement
must reproduce the bytes both checkers reviewed on 20 Nov 2026 (commercial paper removed, A133).
Usage: python3 corp/selftest_corp.py   (from the repo root)"""
import hashlib, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
EXPECT = "c573934fb33c225acae7572b8f78748c886fdba70ca1019006147e2be6e32b6b"
out = os.path.join(tempfile.mkdtemp(), "edition.html")
r = subprocess.run([sys.executable, os.path.join(HERE, "corp_build.py"), os.path.join(HERE, "fixtures", "tape_2026-11-16.json"),
                    os.path.join(HERE, "fixtures", "supp_2026-11-16.json"), out], capture_output=True, text=True)
if r.returncode:
    print("CORP SELF-TEST FAIL: builder exited", r.returncode, r.stderr.strip()[-500:]); sys.exit(1)
got = hashlib.sha256(open(out, "rb").read()).hexdigest()
bad = open(out, encoding="utf-8").read().count("—")
if got != EXPECT or bad:
    print(f"CORP SELF-TEST FAIL: sha256 {got} (expected {EXPECT}); em dashes {bad}"); sys.exit(1)
print("CORP SELF-TEST PASS")
