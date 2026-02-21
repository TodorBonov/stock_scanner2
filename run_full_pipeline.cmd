@echo off
REM Full pipeline: fetch, report, position suggestions, ChatGPT validation (execution order 01->02->03->04)
REM Optional: 05_chatgpt_validation_advanced, 06_chatgpt_position_suggestions, 07_retry_failed_stocks

echo ================================================================================
echo FULL PIPELINE (Fetch + Report + ChatGPT + Position Suggestions)
echo ================================================================================

echo.
echo [1/4] Fetching stock data (force refresh)...
python 01_fetch_stock_data.py --refresh
if errorlevel 1 (
    echo [ERROR] Data fetch failed!
    exit /b 1
)

echo.
echo [2/4] Generating full report...
python 02_generate_full_report.py
if errorlevel 1 (
    echo [ERROR] Report generation failed!
    exit /b 1
)

echo.
echo [3/4] Running position suggestions...
python 03_position_suggestions.py
if errorlevel 1 (
    echo [ERROR] Position suggestions failed!
    exit /b 1
)

echo.
echo [4/4] Running ChatGPT validation...
python 04_chatgpt_validation.py
if errorlevel 1 (
    echo [ERROR] ChatGPT validation failed!
    exit /b 1
)

echo.
echo ================================================================================
echo [SUCCESS] Full pipeline completed!
echo ================================================================================
echo.
echo Check the reports\ directory for:
echo   - summary_report_*.txt
echo   - detailed_report_*.txt
echo   - summary_Chat_GPT.txt
echo   - position_suggestions_*.txt
