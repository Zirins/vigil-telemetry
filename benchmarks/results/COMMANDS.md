# Benchmark reproduction

## Environment for the runs saved in this folder

- OS: Windows (see `hardware_*.txt`)
- CPU: Intel Core Ultra 9 275HX (24 logical processors)
- RAM: 31.4 GB
- Machine: Lenovo 83F5
- Postgres: Docker `postgres:16` (`vigil-postgres`) on host port 5434
- API: single uvicorn worker `app.main:app` on `127.0.0.1:8001`
- Concurrent HTTP clients for throughput: **1** (sequential batches)

## Exact commands (canonical)

From repo root, with backend healthy at `http://127.0.0.1:8001`:

```powershell
# Detection — tuning + held-out, 5 rounds × 3 repeats
python backend/scripts/benchmark.py `
  --base-url http://127.0.0.1:8001 `
  --schedule both `
  --rounds 5 `
  --repeats 3 `
  --log-dir benchmarks/results

# Throughput — tiers 10/25/50/100 events/sec, 30s each
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
python backend/scripts/throughput_benchmark.py `
  --base-url http://127.0.0.1:8001 `
  | Tee-Object -FilePath "benchmarks/results/throughput_$stamp.log"
```

Canonical outputs cited in README / `RESULTS.md`:

- `detection_both_20261003T214429Z.log`
- `throughput_20261003T221623Z.log`

## Fair-eval note

Production open-incident dedup is unchanged. The harness registers a **fresh
service per round** so unresolved open incidents from round N cannot zero out
rounds N+1… (see `DIAGNOSIS_dedup.md`). Within a round, dedup still allows at
most one open incident per `(service_id, detection_type)`.

Thresholds in `detection.py` were **not** retuned for these numbers.
