# Dedup diagnosis (pre-fix)

Captured from earlier 5-round run on a single shared service_id=20
(old harness). Backend: http://127.0.0.1:8001.

| Round | Incidents | Rows |
|------:|----------:|------|
| 1 | 3 | id=430 spike open; id=431 rage_pattern open; id=432 error_rate open |
| 2 | 0 | — |
| 3 | 0 | — |
| 4 | 0 | — |
| 5 | 0 | — |

All three round-1 incidents remained `open`, so `get_open_incident` /
partial unique index blocked every subsequent create for those detection
types. Aggregate recall collapsed to 5.7% (2 TP / 33 FN) even though the
detector itself still fired on round 1.

Fix applied in harness only: fresh service per round (see COMMANDS.md).
