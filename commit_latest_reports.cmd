@echo off
REM Run this AFTER the full pipeline has finished to commit and push the latest reports.
REM Commits: V2 reports (sepa_scan_user_report_*.txt, chatgpt_*_v2_*.txt, etc.)

cd /d "%~dp0"

git add reportsV2/
git status --short reportsV2/
if errorlevel 1 goto :eof

git commit -m "Latest reports" -- reportsV2/
if errorlevel 1 (
    echo Nothing to commit or commit failed.
    exit /b 1
)

git push origin main
if errorlevel 1 (
    echo Push failed.
    exit /b 1
)

echo.
echo Done. Latest reportsV2 pushed to repo.
exit /b 0
