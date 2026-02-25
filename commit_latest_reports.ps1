# Run this AFTER the full pipeline has finished to commit and push the latest reports.
# Commits: V2 reports (reportsV2/ – sepa_scan_user_report_*.txt, chatgpt_*_v2_*.txt, etc.)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

git add reportsV2/
git status --short reportsV2/

git commit -m "Latest reports" -- reportsV2/
if ($LASTEXITCODE -ne 0) {
    Write-Host "Nothing to commit or commit failed."
    exit 1
}

git push origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "Push failed."
    exit 1
}

Write-Host "`nDone. Latest reportsV2 pushed to repo."
