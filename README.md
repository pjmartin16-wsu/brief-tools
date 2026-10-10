# setnova-tools

Deterministic release checks for the Setnova Advisory Treasury Morning Brief.

`setnova_checks.py` runs every mechanical gate of the brief's production prompt as code (standard library only):
wording scans, change-basis arithmetic against Treasury's own table, plain-text vs HTML figures, prose vs grid,
cross-edition consistency, dashes and branding. Exit 0 = pass, 1 = at least one failure, 2 = input error.

    python3 setnova_checks.py --self-test

Every rule has a seeded fixture that must make it fail. Add the fixture before adding the rule.
The production run uses a copy only if its SHA-256 matches the one pinned in the run's prompt,
so a change here takes effect only when the prompt's pin is updated too.

## Rule-change policy (PM, 10 Oct 2026)

A new rule must either replace an old one or come with a test: a seeded fixture in `SEEDS` that makes it FAIL.
A quarterly pass (the "Setnova quarterly rule prune" scheduled task) lists the rules that no longer fire, and PM decides which to delete.
A change here takes effect in the brief only when the hash pinned in the brief prompt is updated.
