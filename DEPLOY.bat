@echo off
color 0A
echo.
echo ========================================
echo   DISCORD BOT - RAILWAY DEPLOYMENT
echo ========================================
echo.
echo This will push your bot to GitHub
echo.
pause

cd /d "%~dp0"

echo.
echo [Step 1/5] Initializing Git...
git init
if errorlevel 1 (
    echo ERROR: Git not installed! Download from: https://git-scm.com/download/win
    pause
    exit /b 1
)

echo [Step 2/5] Adding files...
git add .

echo [Step 3/5] Creating commit...
git commit -m "Discord bot ready for Railway"

echo [Step 4/5] Setting main branch...
git branch -M main

echo.
echo ========================================
echo   ENTER YOUR GITHUB REPOSITORY URL
echo ========================================
echo.
echo Example: https://github.com/username/discord-bot.git
echo.
set /p REPO_URL="Paste URL here: "

echo.
echo [Step 5/5] Pushing to GitHub...
git remote add origin %REPO_URL%
git push -u origin main

if errorlevel 1 (
    echo.
    echo ERROR: Push failed! Make sure:
    echo - Repository URL is correct
    echo - Repository is empty
    echo - You're logged into Git
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   SUCCESS! CODE PUSHED TO GITHUB
echo ========================================
echo.
echo NEXT STEPS:
echo.
echo 1. Go to: https://railway.app/
echo 2. Login with GitHub
echo 3. Click "New Project"
echo 4. Select "Deploy from GitHub repo"
echo 5. Choose your repository
echo 6. Go to "Variables" tab
echo 7. Add variable:
echo    Name:  DISCORD_TOKEN
echo    Value: YOUR_BOT_TOKEN
echo 8. Wait 2-3 minutes for deployment
echo 9. Your bot will be ONLINE!
echo.
echo ========================================
pause
