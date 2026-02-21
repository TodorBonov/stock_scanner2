# Full pipeline: fetch, report, position suggestions, ChatGPT validation, ChatGPT position suggestions, then commit & push
# Runs: 01 -> 02 -> 03 -> 04 -> 06 -> commit_latest_reports.ps1 (optional: 05_chatgpt_validation_advanced, 07_retry_failed_stocks)

$ErrorActionPreference = "Stop"

Write-Host ("=" * 80)
Write-Host "FULL PIPELINE (Fetch + Report + ChatGPT + Position Suggestions + ChatGPT Positions + Push)"
Write-Host ("=" * 80)

Write-Host "`n[1/6] Fetching stock data (force refresh)..."
python 01_fetch_stock_data.py --refresh
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Data fetch failed!"
    exit 1
}

Write-Host "`n[2/6] Generating full report..."
python 02_generate_full_report.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Report generation failed!"
    exit 1
}

Write-Host "`n[3/6] Running position suggestions..."
python 03_position_suggestions.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Position suggestions failed!"
    exit 1
}

Write-Host "`n[4/6] Running ChatGPT validation..."
python 04_chatgpt_validation.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] ChatGPT validation failed!"
    exit 1
}

Write-Host "`n[5/6] Running ChatGPT position suggestions..."
python 06_chatgpt_position_suggestions.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] ChatGPT position suggestions failed (e.g. no OPENAI_API_KEY or no positions) - continuing."
}

Write-Host "`n[6/6] Committing and pushing reports to repo..."
& "$PSScriptRoot\commit_latest_reports.ps1"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] Commit/push failed or nothing to commit - check git status."
}

Write-Host "`n" + ("=" * 80)
Write-Host "[SUCCESS] Full pipeline completed!"
Write-Host ("=" * 80)
Write-Host "`nCheck the reports/ directory for:"
Write-Host "  - summary_report_*.txt"
Write-Host "  - detailed_report_*.txt"
Write-Host "  - summary_Chat_GPT.txt"
Write-Host "  - position_suggestions_*.txt"
Write-Host "  - position_suggestions_Chat_GPT*.txt"
Write-Host "`nReports committed and pushed to repo (if there were changes)."