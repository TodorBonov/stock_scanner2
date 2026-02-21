# Latest-data pipeline: report, position suggestions, ChatGPT validation using existing cache
# Runs: 02_generate_full_report.py -> 03_position_suggestions.py -> 04_chatgpt_validation.py
# Requires: data/cached_stock_data.json (run 01_fetch_stock_data.py or run_full_pipeline.ps1 first)

$ErrorActionPreference = "Stop"

Write-Host ("=" * 80)
Write-Host "LATEST-DATA PIPELINE (Report + ChatGPT + Position Suggestions, no fetch)"
Write-Host ("=" * 80)

$cacheFile = "data/cached_stock_data.json"
if (-not (Test-Path $cacheFile)) {
    Write-Host "[ERROR] Cache not found: $cacheFile"
    Write-Host "Run 01_fetch_stock_data.py or run_full_pipeline.ps1 first."
    exit 1
}

Write-Host "`n[1/3] Generating full report (using existing cache)..."
python 02_generate_full_report.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Report generation failed!"
    exit 1
}

Write-Host "`n[2/3] Running position suggestions..."
python 03_position_suggestions.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Position suggestions failed!"
    exit 1
}

Write-Host "`n[3/3] Running ChatGPT validation..."
python 04_chatgpt_validation.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] ChatGPT validation failed!"
    exit 1
}

Write-Host "`n" + ("=" * 80)
Write-Host "[SUCCESS] Latest-data pipeline completed!"
Write-Host ("=" * 80)
Write-Host "`nCheck the reports/ directory for:"
Write-Host "  - summary_report_*.txt"
Write-Host "  - detailed_report_*.txt"
Write-Host "  - summary_Chat_GPT.txt"
Write-Host "  - position_suggestions_*.txt"
