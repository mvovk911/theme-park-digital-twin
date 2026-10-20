# Reproduce the completed run analysis

[Result](analysis.md) · [Independent review](review.md) · [Complete v2 contract](review-run.json) · [Raw archive](raw-evidence.tar.gz) · [Member hashes](raw-evidence-manifest.json) · [Archive hash](raw-evidence-archive.json)

The archive contains exact synthetic API and GPU ledgers, the resource CSV and eight saved native frames. It excludes runtime databases, credentials and provider inventory. The five analyzer inputs match the hashes retained in `analysis.json` and `review-run.json`.

From the repository root:

```bash
mkdir -p runtime/final-evidence-reproduction
tar -xzf docs/experiments/run-analysis/final/raw-evidence.tar.gz -C runtime/final-evidence-reproduction
python3 operators/analyze_fox_run.py \
  --api-dir runtime/final-evidence-reproduction/api \
  --gpu-dir runtime/final-evidence-reproduction/gpu/gpu-observation \
  --resource-csv runtime/final-evidence-reproduction/gpu/gpu-resources.csv \
  --output runtime/final-evidence-analysis
```

The output directory must not already exist. Reproduction changes input paths and analysis capture timestamps; numerical results, exact input hashes, source identities and failures should agree. Verify extracted members against `manifest.json`. The archive SHA256 is `1a00d1da71a20b7ddea64cfe3bb3c63353340069f40f102ab91ceff1c89c57b8` (3,357,074 bytes).

The source analyzer SHA256 is `7833c30d628d603873a876b121c78870b0c4735dde2083884d12b15e06d6719d`. Its shared v2 validator is also used by the final deck. The contract verifies consistency and sampled coverage; hashes identify bytes and do not authenticate logs or establish continuous uptime or business value.

Saved images are hourly samples 0, 120, 240, 360, 480, 600, 720 and 840. The final image is from approximately hour seven; no hour-eight screenshot is invented. Exact image hashes and frame/source ages remain beside their observations.
