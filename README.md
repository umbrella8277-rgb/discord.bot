# Discord Bot - Railway Deployment

A feature-rich Discord bot with moderation, leveling, economy, music, and games.

## Deployment Instructions

### 1. Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin YOUR-REPO-URL
git push -u origin main
```

### 2. Deploy on Railway
1. Go to https://railway.app/
2. Login with GitHub
3. New Project → Deploy from GitHub repo
4. Select your repository

### 3. Add Environment Variable
In Railway dashboard:
- Go to Variables tab
- Add: `DISCORD_TOKEN` = your bot token

### 4. Done!
Your bot will be online in 2-3 minutes.

## Features
- 236+ commands
- XP/Leveling system
- Economy system
- Music player (with ffmpeg)
- Moderation tools
- Fun games and utilities

## Required Discord Intents
Enable in Discord Developer Portal:
- MESSAGE CONTENT INTENT
- SERVER MEMBERS INTENT
- PRESENCE INTENT (optional)
