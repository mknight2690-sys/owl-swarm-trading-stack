# OWL SWARM TRADING STACK — Complete A-to-Z Setup Tutorial

**Version:** 1.0 | **Updated:** 2026-07-03  
**What this is:** Turn your Windows laptop into a 24/7 automated crypto futures trading bot. Deposit ~$50 USDT, connect to Blofin, launch once, and watch the dashboard.

---

## TABLE OF CONTENTS

1. [Phase 0: What You Need](#phase-0-what-you-need)
2. [Phase 1: Crypto Onramp (Fiat → USDT)](#phase-1-crypto-onramp-fiat--usdt)
3. [Phase 2: VPN Setup (ProtonVPN)](#phase-2-vpn-setup-protonvpn)
4. [Phase 3: Blofin Account + API Keys](#phase-3-blofin-account--api-keys)
5. [Phase 4: OpenRouter Free API Key](#phase-4-openrouter-free-api-key)
6. [Phase 5: Install Software](#phase-5-install-software)
7. [Phase 6: Download the Stack](#phase-6-download-the-stack)
8. [Phase 7: Create Credential Files](#phase-7-create-credential-files)
9. [Phase 8: Install Dependencies](#phase-8-install-dependencies)
10. [Phase 9: Create Desktop Shortcuts](#phase-9-create-desktop-shortcuts)
11. [Phase 10: First Launch](#phase-10-first-launch)
12. [Phase 11: Daily Operation](#phase-11-daily-operation)
13. [Troubleshooting](#troubleshooting)

---

## PHASE 0: WHAT YOU NEED

### Hardware
- **Windows 10 or 11 laptop/desktop** (can leave on 24/7)
- **4GB RAM minimum** (8GB recommended)
- **Stable internet connection** (WiFi or Ethernet)
- **Chrome browser** installed

### Money
- **~$50 to $100 on your debit card** for initial USDT deposit
- **$0 for software** — everything is free/open-source

### Accounts You Will Create (all free)
1. **ProtonVPN** (free tier) — hides your IP from the exchange
2. **Blofin** (free signup) — crypto futures exchange
3. **OpenRouter** (free tier) — AI brain for trading decisions
4. **GitHub** (free) — to download the code

### Time Required
- **First setup:** 45–60 minutes
- **Daily operation:** 30 seconds (double-click launcher)

---

## PHASE 1: CRYPTO ONRAMP (FIAT → USDT)

You need **USDT** (Tether) on the **Blofin** exchange. USDT is a "stablecoin" pegged to $1. Here's the easiest path:

### Step 1.1: Buy USDT on Coinbase (or any exchange you already use)

1. Go to **https://www.coinbase.com**
2. Sign up / log in
3. Click **Buy & Sell** at top
4. Select **USDT** (Tether)
5. Enter amount: **$50** (or whatever you want to trade with)
6. Pay with your **debit card**
7. Confirm purchase

### Step 1.2: Send USDT to Blofin

1. In Coinbase, go to **Send / Receive**
2. Select **USDT**
3. Choose network: **TRC20** (Tron) — cheapest fees (~$1)
4. Coinbase will ask for a **destination address**

**BEFORE you can get the address, you need a Blofin account.** Continue to Phase 3, create your Blofin account, then come back here to get your deposit address.

> **IMPORTANT:** Start with $50 only. This is a micro-scalper. It trades tiny sizes. You can add more later once you see it working.

---

## PHASE 2: VPN SETUP (PROTONVPN)

**Why:** Your ISP and the exchange can see your trading activity. A VPN masks your IP. ProtonVPN is Swiss-based, free tier works fine.

### Step 2.1: Sign Up

1. Go to **https://account.protonvpn.com/signup?plan=free**
2. Enter your email
3. Create password
4. Verify email (check spam folder)

### Step 2.2: Download & Install

1. Go to **https://protonvpn.com/download**
2. Download **Windows** version
3. Run the installer (click through defaults)
4. Launch ProtonVPN app
5. Log in with your email/password

### Step 2.3: Connect

1. In the app, click **Quick Connect** or pick any server
2. Wait for the green shield icon ✅
3. **Leave it connected 24/7 while the bot runs**

> **Pro tip:** Pin ProtonVPN to your taskbar. Check it every morning to make sure it's still connected.

---

## PHASE 3: BLOFIN ACCOUNT + API KEYS

Blofin is the crypto exchange where the bot trades USDT-M perpetual futures.

### Step 3.1: Create Blofin Account

1. Go to **https://www.blofin.com** (make sure VPN is connected first)
2. Click **Sign Up** in top right
3. Use your email (can be same as ProtonVPN or different)
4. Create a strong password
5. Verify email
6. Complete basic KYC (upload ID photo + selfie) — this is required for withdrawals
7. Set up **2FA** (Google Authenticator app) — required for API keys

### Step 3.2: Get Your Deposit Address (for the Coinbase transfer)

1. Log in to Blofin
2. Go to **Assets → Deposit**
3. Select **USDT**
4. Select network: **TRC20** (must match what you selected in Coinbase)
5. Copy the **deposit address** (long string of letters/numbers)
6. Go back to Coinbase, paste this address, and send the USDT
7. Wait 5–10 minutes for it to arrive

### Step 3.3: Create API Keys

The bot needs API keys to place trades on your behalf.

1. In Blofin, go to **Account → API Management**
2. Click **Create API Key**
3. Name it: `OWL-Swarm-Trading`
4. Check permissions:
   - ✅ **Read** (account info, positions)
   - ✅ **Trade** (place orders, close positions)
   - ❌ **Withdraw** (NEVER enable this — the bot doesn't need to withdraw)
5. Enter your **2FA code** from Google Authenticator
6. Blofin will show you:
   - **API Key** (long string, starts with letters/numbers)
   - **Secret Key** (long string, starts with letters/numbers)
   - **Passphrase** (short string, you created this)

> **CRITICAL:** Copy ALL THREE immediately. Blofin only shows the Secret Key once. If you lose it, you have to create a new API key.

### Step 3.4: Save Your API Keys (for later)

Open **Notepad** and type exactly this format:

```
API Key: YOUR_API_KEY_HERE
Secret Key: YOUR_SECRET_KEY_HERE
Passphrase: YOUR_PASSPHRASE_HERE
```

Save this file somewhere safe on your computer. You will need it in Phase 7.

---

## PHASE 4: OPENROUTER FREE API KEY

The bot uses AI (LLMs) to analyze market data and decide which trades to take. OpenRouter provides free access to AI models.

### Step 4.1: Sign Up

1. Go to **https://openrouter.ai/signup**
2. Sign up with Google or email
3. Verify email

### Step 4.2: Get Your Free API Key

1. Go to **https://openrouter.ai/keys**
2. Click **Create Key**
3. Name it: `OWL-Swarm`
4. Copy the key (starts with `sk-or-`)

### Step 4.3: Enable Free Models

1. In OpenRouter, go to **Settings**
2. Make sure **Free models** are enabled
3. The bot uses `openai/gpt-oss-120b:free` (free tier, rate-limited but works)

> **Note:** Free tier has rate limits. If you hit limits, the bot will retry. It still works. If you want faster responses, you can add $5 credit to OpenRouter later.

---

## PHASE 5: INSTALL SOFTWARE

You need three things installed on your Windows computer.

### Step 5.1: Install Git

1. Go to **https://git-scm.com/download/win**
2. Download the **64-bit Git for Windows Setup**
3. Run the installer
4. Click **Next** through all defaults (don't change anything)
5. When it asks about **PATH**, select **"Git from the command line and also from 3rd-party software"**
6. Finish installation

**Verify:** Open Command Prompt (type `cmd` in Windows search, hit Enter), type:
```
git --version
```
You should see something like `git version 2.45.0`. If you get an error, restart your computer and try again.

### Step 5.2: Install Python 3.12

1. Go to **https://www.python.org/downloads/release/python-3120/**
2. Scroll down to **Files**
3. Download **Windows installer (64-bit)** — the big button at top
4. Run the installer
5. **CRITICAL:** Check the box that says **"Add Python to PATH"** at the bottom of the first screen
6. Click **Install Now**
7. Wait for it to finish

**Verify:** Open Command Prompt, type:
```
python --version
```
You should see `Python 3.12.x`. If not, restart your computer.

### Step 5.3: Install Node.js

1. Go to **https://nodejs.org**
2. Click the big **LTS** button (green, says "Recommended For Most Users")
3. Download and run the installer
4. Click through all defaults
5. Finish installation

**Verify:** Open Command Prompt, type:
```
node --version
```
You should see `v20.x.x` or higher.

---

## PHASE 6: DOWNLOAD THE STACK

Now you download the actual trading bot code.

### Step 6.1: Open Git Bash

1. Right-click on your **Desktop**
2. Select **"Git Bash Here"**
3. A black terminal window opens

### Step 6.2: Clone the Repository

In the Git Bash window, type this EXACTLY (then press Enter):

```bash
cd /c/Users/$USER
git clone https://github.com/mknight2690-sys/owl-swarm-trading-stack.git
```

Wait for it to finish. You will see a lot of text scrolling. When it says `done` and returns to the prompt, it's finished.

### Step 6.3: Verify the Download

In Git Bash, type:
```bash
ls owl-swarm-trading-stack/
```

You should see folders like `src`, `trading-engine`, `scripts`, etc.

---

## PHASE 7: CREATE CREDENTIAL FILES

The bot reads your API keys from specific text files. You need to create these files exactly where the bot expects them.

### Step 7.1: Create the Blofin Credentials File

1. Open **Notepad**
2. Type exactly this (replace with your actual keys from Phase 3.3):

```
API Key: YOUR_BLOFIN_API_KEY_HERE
Secret Key: YOUR_BLOFIN_SECRET_KEY_HERE
Passphrase: YOUR_BLOFIN_PASSPHRASE_HERE
```

3. Click **File → Save As**
4. Navigate to: `C:\Users\YOUR_USERNAME\OneDrive\Documents\`
5. In the **File name** box, type exactly: `1B Blofin API.txt`
6. Make sure **Save as type** is set to `All Files (*.*)`
7. Click **Save**
8. Close Notepad

> **Replace `YOUR_USERNAME`** with your actual Windows username. To find it: press Windows key, type `cmd`, open Command Prompt, and type `echo %USERNAME%`. That prints your username.

### Step 7.2: Create the OpenRouter Credentials File

1. Open **Notepad** again
2. Type exactly this (replace with your actual key from Phase 4.2):

```
OpenRouter API Key: sk-or-YOUR_KEY_HERE
```

3. Click **File → Save As**
4. Navigate to: `C:\Users\YOUR_USERNAME\OneDrive\Documents\`
5. In the **File name** box, type exactly: `1BananaOnTheWall Openrouter API Key.txt`
6. Make sure **Save as type** is set to `All Files (*.*)`
7. Click **Save**
8. Close Notepad

### Step 7.3: Verify Files Exist

Open Command Prompt and type:
```
dir "C:\Users\%USERNAME%\OneDrive\Documents\1B Blofin API.txt"
dir "C:\Users\%USERNAME%\OneDrive\Documents\1BananaOnTheWall Openrouter API Key.txt"
```

Both should say `File(s) found`. If not, you saved to the wrong folder.

---

## PHASE 8: INSTALL DEPENDENCIES

The bot needs Python libraries and Node.js packages to run.

### Step 8.1: Open PowerShell as Admin

1. Press **Windows key**
2. Type `powershell`
3. Right-click on **Windows PowerShell**
4. Select **Run as administrator**
5. Click **Yes** on the UAC prompt

### Step 8.2: Install Python Dependencies

In the PowerShell window, type this EXACTLY (it's one long command, let it wrap):

```powershell
cd C:\Users\$env:USERNAME\owl-swarm-trading-stack\trading-engine
pip install -e .
```

Wait for it to finish. This downloads about 50 Python packages. It takes 3–5 minutes. You'll see green progress bars.

If you see errors about `pip` not found, type this first:
```powershell
python -m pip install --upgrade pip
```
Then retry the `pip install -e .` command.

### Step 8.3: Install Node.js Dependencies

In the SAME PowerShell window, type:

```powershell
cd C:\Users\$env:USERNAME\owl-swarm-trading-stack
npm install
```

Wait for it to finish. This downloads the dashboard server dependencies. Takes 2–3 minutes.

### Step 8.4: Compile the Dashboard

In the SAME PowerShell window, type:

```powershell
npx tsc --project tsconfig.json
```

This compiles the TypeScript dashboard code into JavaScript. Takes 30 seconds. If it says `error TS...`, ignore it — the dashboard will still work.

---

## PHASE 9: CREATE DESKTOP SHORTCUTS

You want to double-click icons on your desktop to start/stop the bot. Here's how to make them.

### Step 9.1: Create the Launcher Shortcut

1. Right-click on your **Desktop**
2. Select **New → Shortcut**
3. In the location box, type exactly:

```
C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File "C:\Users\%USERNAME%\owl-swarm-trading-stack\launch.ps1"
```

4. Click **Next**
5. Name it: `OWL Swarm Launcher`
6. Click **Finish**
7. Right-click the new shortcut → **Properties**
8. Click **Change Icon** → Browse → find `C:\Windows\System32\shell32.dll` → pick a green arrow icon
9. Click **OK**

### Step 9.2: Create the Stopper Shortcut

1. Right-click on your **Desktop**
2. Select **New → Shortcut**
3. In the location box, type exactly:

```
C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File "C:\Users\%USERNAME%\owl-swarm-trading-stack\stop.ps1"
```

4. Click **Next**
5. Name it: `Stop OWL Swarm`
6. Click **Finish**
7. Right-click the new shortcut → **Properties**
8. Click **Change Icon** → pick a red X icon
9. Click **OK**

### Step 9.3: Test the Shortcuts

1. Double-click **OWL Swarm Launcher**
2. A PowerShell window should open with blue text saying `OWL Swarm Desktop Launcher`
3. Wait 30 seconds
4. Chrome should open automatically showing `http://127.0.0.1:7878`
5. You should see the dashboard with your equity displayed
6. If it works, click **Stop OWL Swarm** to shut it down

---

## PHASE 10: FIRST LAUNCH

This is the moment. Make sure:
- ✅ ProtonVPN is connected
- ✅ You have USDT in your Blofin account
- ✅ Both credential files are created
- ✅ All software is installed

### Step 10.1: Launch

1. Double-click **OWL Swarm Launcher** on your desktop
2. PowerShell window opens — watch the blue text
3. It will:
   - Kill any old bots (clean slate)
   - Start the dashboard server
   - Start the trading engine
   - Open Chrome to the dashboard
4. Wait 60 seconds for everything to warm up

### Step 10.2: What You Should See

- **PowerShell window:** Blue text cycling through "CYCLE X starting..." every 30 seconds
- **Chrome dashboard:** Shows your equity, available balance, open positions, and a live log
- **Top left:** Timestamp ticking every second
- **Equity number:** Smoothly sliding (not jumping)

### Step 10.3: Verify It's Trading

1. Look at the dashboard **Positions** section
2. If you see a row like `ROSE-USDT LONG Size: 0.001 Entry: 0.0423 Mark: 0.0424 P&L: +0.0002` — the bot is trading!
3. Check Blofin website → **Positions** tab — you should see the same position there

### Step 10.4: First 24 Hours

- The bot will place 0–3 trades per day on a $50 account
- Each trade is tiny (micro-contracts)
- Don't panic if no trades happen for hours — the risk gate waits for good setups
- The bot uses 50x leverage, so a 1% move = 50% P&L on that position

---

## PHASE 11: DAILY OPERATION

Once set up, running the bot takes 30 seconds per day.

### Morning Routine

1. Check ProtonVPN is connected (green shield ✅)
2. Double-click **OWL Swarm Launcher**
3. Wait 30 seconds for dashboard to open
4. Check your equity — if it's green, you're winning
5. Leave laptop running (don't close lid, or set lid-close to "Do nothing")

### Evening Routine

1. Check dashboard for any open positions
2. If you want to stop for the night: double-click **Stop OWL Swarm**
3. Positions stay open on the exchange — the bot will manage them when restarted

### Leaving Laptop On 24/7

1. Press **Windows key**
2. Type `power` and open **Edit Power Plan**
3. Set **Turn off display:** Never
4. Set **Put computer to sleep:** Never
5. Click **Save changes**

This keeps your laptop awake forever.

---

## TROUBLESHOOTING

### "Blofin credentials not found" error
- You saved the file to the wrong folder
- Fix: Re-read Phase 7.1 — the file MUST be in `C:\Users\YOU\OneDrive\Documents\1B Blofin API.txt`

### "OpenRouter key file not found" error
- Same issue — wrong folder or wrong filename
- Fix: Re-read Phase 7.2 — exact filename matters

### Dashboard shows "No connection" or blank page
- The dashboard server didn't start
- Fix: Double-click **Stop OWL Swarm**, wait 10 seconds, then double-click **OWL Swarm Launcher** again

### PowerShell window closes immediately
- Right-click the launcher shortcut → **Properties**
- Change target to:
  ```
  C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -NoExit -ExecutionPolicy Bypass -File "C:\Users\YOURNAME\owl-swarm-trading-stack\launch.ps1"
  ```
- The `-NoExit` keeps the window open so you can see errors

### "pip is not recognized" error
- Python wasn't added to PATH during installation
- Fix: Reinstall Python from Phase 5.2, and CHECK the "Add to PATH" box

### Chrome doesn't open automatically
- Open Chrome manually and go to: `http://127.0.0.1:7878`
- The dashboard is there even if Chrome didn't auto-launch

### ProtonVPN keeps disconnecting
- In ProtonVPN settings, enable **Kill Switch** and **Always-On VPN**
- This prevents any internet traffic if the VPN drops

### Bot is not placing trades
- Check the PowerShell log for "Risk gate veto" or "No candidate passed"
- This means the market is choppy and the bot is waiting for a good setup
- This is CORRECT behavior — survival first, profit second

### Equity is dropping
- Small drawdowns are normal in scalping
- The bot cuts losses fast (automatic stop-losses on every trade)
- If equity drops more than 20% from peak, double-click **Stop OWL Swarm** and investigate

---

## QUICK REFERENCE CHEAT SHEET

| Action | What to Do |
|--------|-----------|
| **Start bot** | Double-click `OWL Swarm Launcher` |
| **Stop bot** | Double-click `Stop OWL Swarm` |
| **View dashboard** | Open Chrome → `http://127.0.0.1:7878` |
| **Check positions** | Blofin website → Positions tab |
| **Add more money** | Coinbase → Buy USDT → Send to Blofin (TRC20) |
| **Update bot code** | Git Bash → `cd owl-swarm-trading-stack && git pull` |
| **Check logs** | Open `C:\Users\YOU\owl-swarm-trading-stack\outputs\live-run.log` in Notepad |

---

## SECURITY CHECKLIST

- [ ] API keys only have **Read + Trade** permissions (NO Withdraw)
- [ ] API keys are stored in `.txt` files, NOT in the code
- [ ] VPN is always connected while bot runs
- [ ] Laptop has a login password
- [ ] No one else has access to your credential files
- [ ] You understand the bot can lose money — only trade what you can afford to lose

---

## CREDITS

- **OWL Swarm Trading Stack** by mknight2690
- Built on **AutoHedge** by The Swarm Corporation
- Dashboard: TypeScript + Node.js
- Engine: Python + LLM swarm intelligence
- Exchange: Blofin

---

## SUPPORT

If you get stuck:
1. Read the error message in the PowerShell window carefully
2. Check the **Troubleshooting** section above
3. Look at the log file: `C:\Users\YOURNAME\owl-swarm-trading-stack\outputs\live-run.log`
4. Open a GitHub issue at: https://github.com/mknight2690-sys/owl-swarm-trading-stack/issues

---

**END OF TUTORIAL**

**Now go make money.** 🦉
