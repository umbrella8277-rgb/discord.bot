@echo off
color 0B
echo.
echo ========================================
echo   UPDATING DEPLOYMENT
echo ========================================
echo.

cd /d "%~dp0"

echo [1/3] Adding changes...
git add .

echo [2/3] Committing...
git commit -m "Update bot"

echo [3/3] Pushing to GitHub...
git push

if errorlevel 1 (
    echo.
    echo ERROR: Push failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo   SUCCESS! UPDATES PUSHED
echo   Railway will redeploy in 2-3 minutes
echo ========================================
echo.
pause
