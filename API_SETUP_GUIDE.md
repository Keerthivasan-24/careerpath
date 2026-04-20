# 🔑 API Keys Setup Guide

## Quick Setup (2 minutes per key)

### 1. Groq (Already Set ✅)
- Already configured in app.py
- No action needed

### 2. Google Gemini (Recommended - Best Free Tier)
1. Go to: https://aistudio.google.com/apikey
2. Click "Create API Key"
3. Copy the key
4. Open `app.py` line 29
5. Replace: `GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_KEY_HERE")`

**Free Limits:** 15 requests/min, 1000/day

### 3. OpenRouter (Optional Backup)
1. Go to: https://openrouter.ai/keys
2. Sign up and create key
3. Copy the key
4. Open `app.py` line 33
5. Replace: `OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "YOUR_KEY_HERE")`

**Free Limits:** 20 requests/min, 50/day

## How It Works
- App tries Groq first (fastest)
- If rate limit → switches to Gemini
- If rate limit → switches to OpenRouter
- **No crashes, automatic fallback!**

## Run the App
```bash
setup.bat
```
