# Benchmark results (canonical)

**Canonical detection log:** `detection_both_20261003T214429Z.log`  
**Canonical throughput log:** `throughput_20261003T221623Z.log`  
**Hardware:** `hardware_20261003T211001Z.txt`  
**Dedup diagnosis (pre-fix):** `DIAGNOSIS_dedup.md`  
**Reproduce:** see `COMMANDS.md`

Earlier incomplete runs (`detection_both_20261003T211004Z.log`,
`detection_both_20261003T214226Z.log`) are retained for audit only — do not
cite them. They predate label/clock-skew harness fixes.

## Detection (5 rounds × 3 repeats each schedule)

Production open-incident dedup unchanged. Harness uses a **fresh service per
round**. Type-strict matching within a 10s window (±2s clock skew).

### Tuning schedule (original timings)

| Metric | Micro-average (3 repeats) |
|---|---|
| Precision | **100.0%** |
| Recall | **28.6%** |
| F1 | **44.4%** |
| Totals | TP=30 FP=0 FN=75 |

| detection_type | Precision | Recall | F1 |
|---|---|---|---|
| spike | 100.0% | 33.3% | 50.0% |
| error_rate | 100.0% | 50.0% | 66.7% |
| rage_pattern | 0.0% | 0.0% | 0.0% |

Rage is 0% on the tuning schedule because injections place `rage_pattern`
after `error_burst`, and `run_detection` returns `error_rate` first while the
window is still hot — rage is never reached. That is detector precedence, not
a harness bug.

### Held-out schedule (different timings + magnitudes)

| Metric | Micro-average (3 repeats) |
|---|---|
| Precision | **100.0%** |
| Recall | **42.9%** |
| F1 | **60.0%** |
| Totals | TP=45 FP=0 FN=60 |

| detection_type | Precision | Recall | F1 |
|---|---|---|---|
| spike | 100.0% | 33.3% | 50.0% |
| error_rate | 100.0% | 50.0% | 66.7% |
| rage_pattern | 100.0% | 50.0% | 66.7% |

Remaining FNs are largely **within-round open-incident dedup** (second/third
injection of the same type while the first is still open).

## Throughput

| Tier | Achieved | P99 | Failed |
|---|---|---|---|
| 10/s | 9.9/s | 17ms | 0 |
| 25/s | 24.8/s | 28ms | 0 |
| 50/s | 49.6/s | 42ms | 0 |
| 100/s | **99.2/s** | **89ms** | 0 |

Hardware: Lenovo 83F5, Intel Core Ultra 9 275HX (24 logical processors),
31.4 GB RAM, Postgres 16 in Docker on localhost:5434, single uvicorn worker
on 127.0.0.1:8001, **1** sequential HTTP client.
