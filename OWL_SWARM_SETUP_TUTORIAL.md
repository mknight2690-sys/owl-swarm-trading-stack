# OWL SWARM TRADING STACK — Complete A-to-Z Setup Tutorial

**Version:** 1.5 (The "Stupid Easy" Edition) | **Updated:** 2026-07-03  
**Who this is for:** Everyone. If you've never heard of crypto, start here. If you have $3, start here. If you have $300, start here. If you know nothing about computers, start here. We will walk you through every single click.

> **Welcome.** You are about to set up a robot that trades crypto for you while you sleep. It costs $0 to run. You can start with $3, $5, $50, or whatever you feel comfortable with. There is no minimum. The bot works with any amount. Your $3 can grow. Your $5 can grow. Let it compound. This is real.

---

## TABLE OF CONTENTS

1. [The Two Ways to Set This Up](#the-two-ways-to-set-this-up)
2. [Phase 0: What You Need](#phase-0-what-you-need)
3. [Phase 1: Buy Some Crypto (USDT)](#phase-1-buy-some-crypto-usdt)
4. [Phase 2: Get a VPN (ProtonVPN — Free)](#phase-2-get-a-vpn-protonvpn--free)
5. [Phase 3: Create Your Blofin Account](#phase-3-create-your-blofin-account)
6. [Phase 4: Set Up 2FA (Google Authenticator)](#phase-4-set-up-2fa-google-authenticator)
7. [Phase 5: Get Your OpenRouter API Key (Free AI Brain)](#phase-5-get-your-openrouter-api-key-free-ai-brain)
8. [Phase 6: Install the Software](#phase-6-install-the-software)
9. [Phase 7: Download the Bot Code](#phase-7-download-the-bot-code)
10. [Phase 8: Create Your Credential Files](#phase-8-create-your-credential-files)
11. [Phase 9: Make Desktop Icons](#phase-9-make-desktop-icons)
12. [Phase 10: Launch Your Bot](#phase-10-launch-your-bot)
13. [Phase 11: Daily Use](#phase-11-daily-use)
14. [Phase 12: When Your Money Grows (Optional Palau ID)](#phase-12-when-your-money-grows-optional-palau-id)
15. [Troubleshooting](#troubleshooting)
16. [Mac Users — Read This](#mac-users--read-this)

---

## THE TWO WAYS TO SET THIS UP

We have **two paths** for you. Pick the one that fits you.

### Path A: The "Stupid Easy" Way (RECOMMENDED for beginners)

**You use a free AI helper to do ALL the hard stuff for you.** You literally copy and paste one prompt, and the AI installs everything, creates your files, and launches the bot. You just watch.

**What you need:**
- [Cursor](https://cursor.com) — a free AI code editor (like a really smart helper that types for you)
- The single prompt we give you below
- About 15 minutes of watching the AI work

**Why this way?** You don't need to understand git, npm, pip, PowerShell, or any of that scary stuff. The AI does it. You just sit back and let it happen. If you get stuck, you ask the AI "what went wrong?" and it fixes it.

### Path B: The Manual Way (for people who want to see every step)

**You do each step yourself.** We tell you exactly where to click, what to type, and what to expect. Every single step is explained like you're five years old. No knowledge assumed.

**What you need:**
- Command Prompt (we show you where to find it)
- The ability to copy and paste
- About 45–60 minutes

**Why this way?** You learn how everything works. If something breaks later, you know how to fix it. But honestly, Path A is easier and works just as well.

> **Our recommendation:** Start with **Path A**. If the AI hits a problem, switch to Path B for that one step. There is no shame in either path. The goal is getting your bot running so your money can grow.

---

## PHASE 0: WHAT YOU NEED

### Hardware (What Computer)
- **Any computer that can stay on.** A laptop, desktop, old computer, whatever. It just needs to not go to sleep while the bot runs.
- **Windows 10 or 11** (Mac users: see [Mac section at the bottom](#mac-users--read-this))
- **4GB RAM minimum** — basically any computer made in the last 10 years
- **Stable internet** — WiFi or Ethernet, doesn't matter
- **Chrome browser** — if you don't have it, go to [google.com/chrome](https://google.com/chrome) and click "Download Chrome"

### Money (How Much)
- **Whatever you feel comfortable losing.** Seriously. This is the golden rule of trading bots. Only put in money you can afford to lose.
- **$3 is enough.** The bot will trade with $3. It will find coins that fit a $3 balance. It will be slower, but it will work.
- **$5 is the sweet spot.** More coins become tradeable. You'll see activity sooner.
- **$50 is great.** The bot can trade many more coins. You'll see daily activity.
- **There is no maximum.** People run this bot with $10,000. The bot scales with your money.
- **The bot is free to run.** No monthly fees. No subscriptions. The only cost is your starting capital and a one-time $1 network fee when you move money to Blofin.

### Time
- **First time setup:** 30 minutes (Path A) or 60 minutes (Path B)
- **Every day after:** 30 seconds (double-click your icon, done)

### Accounts to Create (All Free)
1. **ProtonVPN** — keeps your internet private (free version works perfectly)
2. **Blofin** — where the bot trades (free to sign up, no ID needed to start)
3. **OpenRouter** — the AI brain that decides which trades to take (free version works)
4. **GitHub** — where the bot code lives (free, only needed for Path B)

---

## PHASE 1: BUY SOME CRYPTO (USDT)

You need a type of digital money called **USDT** on the **Blofin** exchange. Don't worry about what USDT is — it's basically digital dollars. The bot trades with it.

### Step 1.1: Buy USDT on Coinbase

Coinbase is the easiest place to buy crypto with a debit card. It's like a regular shopping website.

1. Go to [coinbase.com](https://coinbase.com) in Chrome
2. Click **Sign Up** in the top right corner
3. Enter your email, create a password, verify your email (they send you a link)
4. Click **Buy & Sell** at the top of the page
5. Click the dropdown that says "Buy" and select **USDT** (Tether)
6. Enter your amount: **$5** (or whatever you want to start with)
7. Click **Buy now** and pay with your debit card
8. Done! You now own USDT.

> **Don't have $5?** That's okay. Buy $3. The bot works with $3. Buy whatever you can afford. There is no shame in starting small. Every dollar counts. Let it compound.

### Step 1.2: Send Your USDT to Blofin

You need to move your USDT from Coinbase to Blofin (the exchange where the bot trades). This costs about $1 in network fees no matter how much you send.

**Before you can do this, you need a Blofin account.** Skip to Phase 3, create your Blofin account, then come back here.

1. Once you have a Blofin account, log in to Blofin
2. Click **Assets** at the top, then click **Deposit**
3. Select **USDT** from the list
4. Select **TRC20** as the network (this is the cheapest option, about $1 fee)
5. Blofin will show you a **Deposit Address** — a long string of letters and numbers. Click the **Copy** button next to it.
6. Go back to Coinbase
7. Click **Send / Receive** at the top right
8. Select **USDT**
9. Paste the Blofin deposit address you just copied
10. Select **TRC20** as the network (must match what you selected in Blofin)
11. Enter the amount you want to send (all of it, or leave a tiny bit in Coinbase if you want)
12. Click **Send now** and confirm
13. Wait 5–10 minutes. Your USDT will appear in your Blofin account.

> **After the $1 fee, you'll have whatever is left.** If you sent $5, you'll have about $4. If you sent $3, you'll have about $2. The bot works with ANY amount. Don't worry about the fee — it's the same $1 whether you send $5 or $500.

---

## PHASE 2: GET A VPN (PROTONVPN — FREE)

### Why You Need a VPN

A VPN is like a mask for your internet. It hides where you really are.

**Why this matters:** Blofin (and many crypto exchanges) blocks people from certain countries — especially the United States, Canada, and China. If Blofin sees your real location, they might block your account. A VPN makes you appear to be in a country that Blofin accepts.

**Also:** Your internet provider can see every website you visit. A VPN stops that. It's just good privacy hygiene, especially when dealing with money.

### How the Free Version Works

ProtonVPN's free version randomly gives you one of three countries. You do NOT get to pick:
- **Netherlands** — Blofin accepts this ✅
- **Japan** — Blofin accepts this ✅
- **United States** — Blofin blocks this ❌

So you click "connect" and hope you get Netherlands or Japan. If you get the United States, you click "Change Server" and try again.

### Step 2.1: Download ProtonVPN

1. Go to [protonvpn.com](https://protonvpn.com) in Chrome
2. Click **Get Proton VPN Free** or **Create Free Account**
3. Enter your email and create a password
4. Check your email and click the verification link
5. Back on the ProtonVPN website, click **Download** and choose **Windows**
6. Run the installer that downloads (double-click it, click Yes/Next through everything)
7. Open the ProtonVPN app from your desktop or Start menu
8. Log in with your email and password

### Step 2.2: Connect and Check Your Country

1. In the ProtonVPN app, click the big **Quick Connect** button
2. Wait for the shield icon to turn green ✅
3. **Look at the top of the app.** It will say something like:
   - "Connected to Netherlands" — GOOD, keep this ✅
   - "Connected to Japan" — GOOD, keep this ✅
   - "Connected to United States" — BAD, change this ❌

> **You do NOT need to visit any website to check your country.** ProtonVPN tells you right in the app.

### Step 2.3: The "Change Server" Trick (If You Got the US)

If ProtonVPN connected you to the **United States**, you need to change it. Here's the exact timing that works:

1. Click **Change Server** in the ProtonVPN app
2. **Wait exactly 1 minute and 30 seconds** (use your phone timer or just count slowly)
3. Look at the app again. What country does it show now?
   - If Netherlands or Japan — you're done! Leave it connected.
   - If United States — continue to step 4
4. Click **Change Server** again
5. **Wait exactly 1 minute and 40 seconds**
6. Check again
   - If Netherlands or Japan — you're done!
   - If United States — continue to step 7
7. Click **Change Server** one more time
8. **Wait exactly 1 minute and 50 seconds**
9. Check again
   - If Netherlands or Japan — you're done!
   - If STILL United States — close the ProtonVPN app completely, reopen it, and click **Quick Connect** again. The server pool resets when you restart.

> **Why the wait times?** ProtonVPN's free servers have a cooldown. If you click "Change Server" too fast, you just get bounced back to the same bad server. The 1:30 → 1:40 → 1:50 timing gives each new server time to properly connect and avoids the cooldown. Be patient. It works.

### Step 2.4: Keep It Connected

- **Leave ProtonVPN running 24/7 while your bot is trading.** If it disconnects, the bot might have problems.
- Pin it to your taskbar so you can check it easily every morning.
- In the ProtonVPN app settings, turn on **Kill Switch** and **Always-On VPN** — this means if the VPN drops for any reason, ALL internet on your computer stops until the VPN reconnects. This protects you from accidentally leaking your real location.

---

## PHASE 3: CREATE YOUR BLOFIN ACCOUNT

Blofin is the exchange where your bot trades. It's where your money lives while the bot works.

> **You do NOT need to upload an ID or verify your identity to start.** Blofin lets you trade and withdraw up to **$20,000 per day** with no KYC (no identity verification). You can start trading TODAY with just an email and password. If you ever need to withdraw more than $20,000 in a single day, there's an optional upgrade in Phase 12.

### Step 3.1: Sign Up

**Important:** Make sure ProtonVPN is connected and showing **Netherlands** or **Japan** BEFORE you do this.

1. Go to [blofin.com](https://blofin.com) in Chrome
2. Click **Sign Up** in the top right corner
3. Enter your email address (can be the same one you used for ProtonVPN, or a different one)
4. Create a strong password (write it down somewhere safe)
5. Click **Sign Up**
6. Check your email for a verification code from Blofin
7. Enter the code on the Blofin website
8. Done! You have a Blofin account.

> **If Blofin asks for your country during signup:** Say **Netherlands** or **Japan** (whichever your VPN shows). Do NOT say your real country if you're in the US, Canada, or a blocked region.

### Step 3.2: Set Up 2FA (Two-Factor Authentication)

Blofin requires 2FA before you can create API keys. 2FA is like a second lock on your account. Even if someone steals your password, they can't get in without your phone.

**You need the Google Authenticator app on your phone.** Here's how to get it:

**iPhone users:**
1. Open the **App Store** on your phone
2. Tap the search icon at the bottom
3. Type **"Google Authenticator"**
4. Tap the app with the colorful circle icon (made by Google LLC)
5. Tap **Get** or **Install**
6. Wait for it to download, then open it

**Android users:**
1. Open the **Google Play Store** on your phone
2. Tap the search bar at the top
3. Type **"Google Authenticator"**
4. Tap the app with the colorful circle icon (made by Google LLC)
5. Tap **Install**
6. Wait for it to download, then open it

**Now set up 2FA on Blofin:**

1. While logged in to Blofin on your computer, click your **profile icon** (top right) and select **Security**
2. Find the section that says **Google Authenticator** or **2FA**
3. Click **Bind** or **Set Up**
4. Blofin will show you a **QR code** (a square black-and-white barcode) and a **secret key** (a long string of letters)
5. On your phone, open the Google Authenticator app
6. Tap the **+** button (bottom right) or **Add account**
7. Choose **Scan a QR code**
8. Point your phone's camera at the QR code on your computer screen
9. The app will add "Blofin" to your list and show a 6-digit number that changes every 30 seconds
10. On your computer, enter the current 6-digit number from your phone
11. Click **Confirm** or **Verify**
12. Done! Your account is now protected.

> **IMPORTANT:** Write down the "secret key" or "backup code" that Blofin gives you during this setup. If you lose your phone, this code lets you recover your 2FA. Save it somewhere safe (a password manager, a note in your phone, or a physical piece of paper in a drawer).

### Step 3.3: Create Your API Keys

API keys are like special passwords that let the bot trade on your behalf. The bot needs them to see your balance and place trades.

1. In Blofin, click your **profile icon** (top right) and select **API Management**
2. Click **Create API Key**
3. Name it: `OWL-Swarm-Trading` (this is just a label, it doesn't matter what you name it)
4. You will see checkboxes for permissions. Check these:
   - ✅ **Read** — lets the bot see your balance and positions
   - ✅ **Trade** — lets the bot place and close trades
   - ❌ **Withdraw** — leave this UNCHECKED. The bot never needs to withdraw money.
5. Click **Create**
6. Blofin will ask for your 2FA code. Open Google Authenticator on your phone, find the 6-digit Blofin code, and enter it.
7. Blofin will now show you THREE things. **Copy all three immediately.** Blofin only shows them once:
   - **API Key** — a long string of letters and numbers
   - **Secret Key** — a long string of letters and numbers
   - **Passphrase** — a shorter string you created when setting up the key
8. **IMPORTANT:** Open Notepad on your computer and paste all three into a file. Save it somewhere you'll remember (like your Desktop). You'll need this in Phase 8.

> **If you lose these keys, you have to create new ones.** Blofin never shows the Secret Key again for security reasons. So save them now.

### Step 3.4: Save Your Keys (For Later)

Open **Notepad** on your computer:

1. Press the **Windows key** on your keyboard
2. Type **"notepad"**
3. Press **Enter** or click the Notepad app
4. Type or paste this exact format:

```
API Key: YOUR_BLOFIN_API_KEY_HERE
Secret Key: YOUR_BLOFIN_SECRET_KEY_HERE
Passphrase: YOUR_BLOFIN_PASSPHRASE_HERE
```

5. Replace the placeholder text with your actual keys from Step 3.3
6. Click **File → Save As**
7. Save it to your **Desktop** with the name: `My Blofin Keys.txt`
8. Close Notepad

> **We'll come back to this file in Phase 8.** Just keep it on your Desktop for now.

---

## PHASE 4: SET UP 2FA (GOOGLE AUTHENTICATOR)

Wait — didn't we already do this? Yes, we set up 2FA for Blofin in Phase 3.2. But if you skipped that section or need to set it up on a different device, here's the standalone guide:

**Get the app:**

**iPhone:**
1. Open **App Store**
2. Search **"Google Authenticator"**
3. Install the app by Google LLC
4. Open it

**Android:**
1. Open **Google Play Store**
2. Search **"Google Authenticator"**
3. Install the app by Google LLC
4. Open it

**Add Blofin to it:**
1. Log in to Blofin on your computer
2. Go to **Account → Security → Google Authenticator**
3. Click **Bind** or **Set Up**
4. Blofin shows a QR code
5. On your phone, open Google Authenticator, tap **+**, choose **Scan QR code**
6. Point your phone at your computer screen
7. Done! The 6-digit codes will appear on your phone whenever you need them.

---

## PHASE 5: GET YOUR OPENROUTER API KEY (FREE AI BRAIN)

OpenRouter is the service that gives the bot access to AI models (like GPT) for free. The AI analyzes market data and decides which trades to take. You don't need to understand how AI works — you just need a free key.

### Step 5.1: Sign Up

1. Go to [openrouter.ai](https://openrouter.ai) in Chrome
2. Click **Sign Up** in the top right
3. You can sign up with your Google account (fastest) or with email
4. If using email: enter your email, create a password, verify your email
5. Done!

### Step 5.2: Create Your API Key

1. While logged in to OpenRouter, click your **profile icon** (top right) and select **Keys**
2. Click **Create Key**
3. Name it: `OWL-Swarm`
4. Copy the key that appears (it starts with `sk-or-`)
5. Open **Notepad** again
6. Type:

```
OpenRouter API Key: sk-or-YOUR_KEY_HERE
```

7. Save this to your **Desktop** as: `My OpenRouter Key.txt`
8. Close Notepad

### Step 5.3: Enable Free Models

1. In OpenRouter, click your **profile icon** and select **Settings**
2. Look for **"Free models"** or **"Enable free models"** and make sure it's turned ON
3. The bot uses `openai/gpt-oss-120b:free` which is completely free but has rate limits
4. If the AI hits a rate limit, the bot will wait and retry automatically. This is normal. It still works.

---

## PHASE 6: INSTALL THE SOFTWARE

Your computer needs three pieces of free software to run the bot. We'll install them one by one. Each one is safe, official, and free.

### Step 6.1: Install Git

Git is a tool that downloads code from the internet. Think of it like a specialized downloader.

1. Go to [git-scm.com/download/win](https://git-scm.com/download/win) in Chrome
2. Click the big button that says **"64-bit Git for Windows Setup"**
3. A file downloads. Double-click it to run it.
4. A setup wizard appears. Click **Next** about 10 times. Don't change any settings. Just keep clicking Next until you see **Finish**.
5. Click **Finish**
6. Done!

**How to check if it worked:**
1. Press **Windows key**, type **"cmd"**, press **Enter**
2. A black window opens. This is **Command Prompt**. Don't be scared of it. It's just a place where you type commands.
3. Type exactly this (then press Enter):
   ```
   git --version
   ```
4. You should see something like: `git version 2.45.0`
5. If you see an error saying "git is not recognized," restart your computer and try again. Sometimes Windows needs a restart to notice new software.

> **What is Command Prompt?** It's a black box where you type text commands instead of clicking buttons. It looks scary but it's just another way to control your computer. Every step below tells you EXACTLY what to type, so you can copy and paste if needed. Nothing will break if you type the wrong thing — you can just close the window and start over.

### Step 6.2: Install Python 3.12

Python is the programming language the bot is written in. You need it on your computer to run the bot.

1. Go to [python.org/downloads/release/python-3120/](https://www.python.org/downloads/release/python-3120/) in Chrome
2. Scroll down until you see **Files**
3. Look for the line that says **"Windows installer (64-bit)"** and click the link to download it
4. A file downloads. Double-click it to run it.
5. **CRITICAL STEP:** On the very first screen of the installer, there is a small checkbox at the bottom that says **"Add Python to PATH"**. Click this checkbox to turn it ON. This is extremely important. If you skip this, Python won't work properly.
6. Click **Install Now**
7. Wait for the green bar to fill up. This takes 2–3 minutes.
8. Click **Close**

**How to check if it worked:**
1. Open Command Prompt again (Windows key, type "cmd", press Enter)
2. Type exactly this:
   ```
   python --version
   ```
3. You should see: `Python 3.12.x` (the x can be any number)
4. If you get an error, you probably forgot to check the "Add to PATH" box. Uninstall Python (go to Settings → Apps, find Python, click Uninstall), then reinstall it and MAKE SURE that checkbox is checked.

### Step 6.3: Install Node.js

Node.js is what runs the dashboard (the pretty web page that shows your bot's progress).

1. Go to [nodejs.org](https://nodejs.org) in Chrome
2. You will see a big green button that says **"LTS"** and "Recommended For Most Users"
3. Click that button to download the installer
4. A file downloads. Double-click it to run it.
5. Click **Next** through all the screens. Don't change anything. Keep clicking Next until you see **Finish**.
6. Click **Finish**

**How to check if it worked:**
1. Open Command Prompt
2. Type exactly this:
   ```
   node --version
   ```
3. You should see something like: `v20.10.0` (the numbers can be different, anything starting with v20 is fine)
4. If you get an error, restart your computer and try again.

---

## PHASE 7: DOWNLOAD THE BOT CODE

Now we download the actual bot. This is the code that makes everything work.

### Step 7.1: Open Command Prompt

You need to open Command Prompt to download the code. Here's how:

1. Press the **Windows key** on your keyboard
2. Type **"cmd"** (without quotes)
3. Press **Enter** on your keyboard
4. A black window opens with white text. This is Command Prompt.

> **What you're looking at:** The black window shows your current location on your computer, like `C:~Users~YourName>`. You can type commands here and the computer will do them. Think of it like texting instructions to your computer.

### Step 7.2: Download the Code

In the Command Prompt window, type this EXACTLY (you can copy and paste it from here), then press **Enter**:

```cmd
cd %USERPROFILE%
git clone https://github.com/mknight2690-sys/owl-swarm-trading-stack.git
```

**What this does:**
- `cd %USERPROFILE%` — moves to your home folder (where your user files live)
- `git clone ...` — downloads the entire bot from the internet

**What to expect:** You will see a bunch of text scrolling. Words like "Cloning into...", "Receiving objects...", "Resolving deltas..." will appear. This is normal. It's just downloading files. When it's done, you'll see your prompt again (the `C:~...>` thing). This takes about 30 seconds to 2 minutes depending on your internet speed.

**How to check if it worked:**
In the same Command Prompt window, type:
```cmd
dir owl-swarm-trading-stack
```

You should see a list of folders and files. If you see things like `src`, `trading-engine`, `scripts`, etc., then it worked perfectly.

---

## PHASE 8: CREATE YOUR CREDENTIAL FILES

The bot needs two files to read your API keys. One for Blofin, one for OpenRouter. Remember the files you saved to your Desktop in Phases 3.4 and 5.2? We're going to copy them to the right place.

### Step 8.1: Create the Blofin Credentials File

You already saved your Blofin keys to `My Blofin Keys.txt` on your Desktop in Phase 3.4. Now we just need to copy that file to the exact location the bot expects.

1. Open **File Explorer** (press Windows key + E, or click the folder icon on your taskbar)
2. Navigate to your **Desktop** (click "Desktop" in the left sidebar)
3. Find the file you saved: `My Blofin Keys.txt`
4. Double-click it to open it in Notepad
5. Select all the text (Ctrl + A)
6. Copy it (Ctrl + C)
7. Close Notepad
8. Open a new Notepad window (Windows key, type "notepad", press Enter)
9. Paste the text (Ctrl + V)
10. Click **File → Save As**
11. Navigate to: `C:~Users~YOUR_USERNAME~OneDrive~Documents`
    - To get there: In the Save As dialog, click on your username in the left sidebar, then double-click "OneDrive", then double-click "Documents"
12. In the **File name** box, type exactly: `1B Blofin API.txt`
13. Make sure **Save as type** is set to `All Files (*.*)` (NOT "Text Documents")
14. Click **Save**
15. Close Notepad

> **Why this file name?** The bot was programmed to look for a file called exactly `1B Blofin API.txt` in your Documents folder. The name must be exact. Capital letters, spaces, and all.

### Step 8.2: Create the OpenRouter Credentials File

Same process, but for your OpenRouter key.

1. Open File Explorer
2. Go to your **Desktop**
3. Find `My OpenRouter Key.txt`
4. Double-click it to open
5. Select all (Ctrl + A), Copy (Ctrl + C)
6. Close Notepad
7. Open a new Notepad window
8. Paste (Ctrl + V)
9. Click **File → Save As**
10. Navigate to: `C:~Users~YOUR_USERNAME~OneDrive~Documents`
11. In the **File name** box, type exactly: `1BananaOnTheWall Openrouter API Key.txt`
12. Make sure **Save as type** is `All Files (*.*)`
13. Click **Save**
14. Close Notepad

### Step 8.3: Verify the Files Exist

Let's make sure both files are in the right place:

1. Open File Explorer (Windows key + E)
2. Go to `OneDrive → Documents`
3. You should see:
   - `1B Blofin API.txt`
   - `1BananaOnTheWall Openrouter API Key.txt`
4. If you see both, you're perfect. If not, repeat the steps above.

---

## PHASE 9: MAKE DESKTOP ICONS

You want to double-click an icon on your desktop to start and stop the bot. Let's make those icons now.

### Step 9.1: Make the "Start" Icon

1. Right-click on an empty area of your **Desktop** (not on any existing icons)
2. Hover over **New** and click **Shortcut**
3. A window appears asking for the location. Type or paste this EXACTLY:

```
C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File "C:\Users\%USERNAME%\owl-swarm-trading-stack\launch.ps1"
```

4. Click **Next**
5. Type the name: `OWL Swarm Launcher`
6. Click **Finish**
7. You now have a new icon on your desktop!
8. (Optional) Right-click it → **Properties** → **Change Icon** → pick a green arrow if you want it to look fancy

### Step 9.2: Make the "Stop" Icon

1. Right-click on an empty area of your Desktop
2. Hover over **New** and click **Shortcut**
3. Type or paste this EXACTLY:

```
C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File "C:\Users\%USERNAME%\owl-swarm-trading-stack\stop.ps1"
```

4. Click **Next**
5. Type the name: `Stop OWL Swarm`
6. Click **Finish**
7. (Optional) Right-click it → **Properties** → **Change Icon** → pick a red X

### Step 9.3: Test the Icons

1. Double-click **OWL Swarm Launcher**
2. A blue PowerShell window should open with text that says "OWL Swarm Desktop Launcher"
3. Wait 30–60 seconds
4. Chrome should open automatically and show your dashboard at `http://127.0.0.1:7878`
5. You should see your account balance and a live updating log
6. If it works, click **Stop OWL Swarm** to shut it down for now

> **If Chrome doesn't open automatically:** Don't worry. The bot is still running. Just open Chrome yourself and type `http://127.0.0.1:7878` in the address bar. You'll see the dashboard.

---

## PHASE 10: LAUNCH YOUR BOT

This is it. The moment your money starts working for you.

### Before You Start

Make sure:
- ✅ ProtonVPN is connected and shows **Netherlands** or **Japan** (NOT United States)
- ✅ You have USDT in your Blofin account (any amount — $2, $5, $50, all work)
- ✅ Both credential files (`1B Blofin API.txt` and `1BananaOnTheWall Openrouter API Key.txt`) are in your Documents folder
- ✅ Your desktop has the two icons: "OWL Swarm Launcher" and "Stop OWL Swarm"

### Launch!

1. Double-click **OWL Swarm Launcher** on your desktop
2. The blue PowerShell window opens. Watch it!
3. You will see text scrolling. It will say things like:
   - "Killing old bots..."
   - "Starting dashboard server..."
   - "Starting OWL Swarm..."
   - "Opening Chrome..."
4. Wait 60 seconds for everything to warm up
5. Chrome opens automatically showing your dashboard

### What You Should See on the Dashboard

- **Your equity** (total money) shown as a dollar amount at the top
- **Available balance** (money not currently in a trade)
- **Open positions** (trades the bot has placed right now)
- **A live log** showing what the bot is thinking and doing
- **A timestamp** in the top left that updates every second
- **Smooth numbers** that slide instead of jumping

### What If No Trades Show Up?

This is **completely normal** and does NOT mean anything is broken. The bot is:
- Scanning all ~500 available coins
- Checking which ones fit your current balance
- Waiting for a trade setup that meets its risk rules (probability ≥ 45%, sentiment aligned, volatility acceptable)
- Protecting your money by NOT trading when there's no good opportunity

**You WILL see:** Cycles running every 30 seconds, agents like "Risk-Manager" and "Execution-Agent" doing their jobs, and messages like "No candidate passed risk gate." These are good signs. The bot is working. It's just being selective.

**You will NOT see immediately:** Trades on expensive coins like Bitcoin or Ethereum if your balance is small. The bot trades micro-contracts on affordable altcoins. With a small balance, it takes time to find the right coin at the right moment.

> **Your $3 can grow. Your $5 can grow. Every successful trade adds a little more. The bot compounds. Be patient. The people who stick with it are the ones who see results.**

### Your First Trade

When the bot finally places a trade, you will see:
- A row in the **Positions** section like: `ROSE-USDT LONG Size: 0.001 Entry: 0.0423 Mark: 0.0424 P&L: +0.0002`
- The same position on the Blofin website when you log in
- The bot managing the position with automatic stop-losses and take-profits

**Celebrate your first trade.** Even if it's tiny. That tiny trade is proof the system works. From there, it grows.

---

## PHASE 11: DAILY USE

Once everything is set up, running the bot is effortless.

### Morning (30 Seconds)
1. Check that ProtonVPN is still connected (green shield ✅)
2. Double-click **OWL Swarm Launcher**
3. Wait 30 seconds for the dashboard to open
4. Check your equity — green means you're winning
5. Leave your computer running (don't close the lid, don't put it to sleep)

### Evening (Optional)
1. Check the dashboard for any open positions
2. If you want to stop for the night: double-click **Stop OWL Swarm**
3. Your positions stay open on the exchange — they'll be managed when you restart

### Keep Your Computer Awake
If your computer goes to sleep, the bot stops. Here's how to keep it awake:
1. Press **Windows key**
2. Type **"power"** and click **Edit Power Plan** or **Power & sleep settings**
3. Set **Screen** to turn off after **Never** or **1 hour** (your choice)
4. Set **Sleep** to **Never**
5. Click **Save changes**

### Growing Your Account
When you see the bot working and you want to add more money:
1. Click **Stop OWL Swarm** to stop the bot
2. Buy more USDT on Coinbase
3. Send it to your same Blofin address (same TRC20 network, same $1 fee)
4. Click **OWL Swarm Launcher** to restart
5. The bot automatically uses the larger balance

> **More money = more tradeable coins = more frequent trades. The bot scales with your balance. Your $5 proof-of-concept can become $50, then $500, then $5,000. The same bot. The same strategy. Just bigger numbers.**

---

## PHASE 12: WHEN YOUR MONEY GROWS (OPTIONAL PALAU ID)

> **Is $20,000 per day enough for you?** Without verifying your identity, Blofin lets you withdraw up to $20,000 USDT every 24 hours. If you're starting with $5, this limit is laughably high. You will never touch it. If you grow to $1,000, you still won't touch it. If you grow to $10,000, you still won't touch it.
>
> **But when your account grows serious** — when you have $100,000+ and you want to pull out $50,000 in a single day — then you need higher limits. And if you live in a country that Blofin blocks (like the US or Canada), you can't verify your identity with your real passport.
>
> **That's where the Palau ID comes in.** This is the upgrade path. This is for when your $5 has compounded into real money and you need to move it freely. This is what serious traders do.

### What Is the Palau ID?

The **Republic of Palau Digital Residency ID** is a real government-issued digital identity card for non-residents. Palau is a sovereign nation. Their program lets anyone in the world apply for a legal ID with a Palau address — accepted by most crypto exchanges for full identity verification.

**Cost:** ~$248 USD per year (one-time payment, valid for 12 months)  
**Apply at:** [rns.id](https://rns.id)  
**What you get:** A physical ID card + digital identity + Palau address  
**Accepted by:** Blofin, Binance, Bybit, KuCoin, and most major exchanges  
**Result:** Daily withdrawal limit jumps from $20,000 to **$1,000,000**

### Why Palau ID?

1. **If you're in a blocked country** (US, Canada, etc.), your real passport won't work for KYC. Palau ID does.
2. **One ID works everywhere** — KYC once, trade on almost every exchange.
3. **It's a real government ID** — issued by a sovereign nation, not a fake document or loophole.
4. **Your $5 can become $5,000. Then $50,000. Then $500,000.** When that happens, you'll want to withdraw more than $20K/day. This is your path.

### How to Get It

**Step 1: Apply**
1. Go to [rns.id](https://rns.id)
2. Click **"Apply for Digital Residency"**
3. Fill out the form (name, email, date of birth)
4. Upload your current government ID (passport or driver's license — this is for Palau's verification)
5. Upload a passport-style photo (white background, face forward)
6. Pay $248 (credit card or crypto)
7. Submit

**Step 2: Wait**
- Approval: 1–3 business days
- You get a digital ID immediately via email
- Physical card ships in 2–4 weeks (optional — digital works for KYC)

**Step 3: Use It for Blofin KYC**
1. Log in to Blofin
2. Go to **Account → Identity Verification**
3. Select **Individual Verification**
4. Choose **"Palau"** as your country
5. Upload your Palau ID (front and back)
6. Upload a selfie holding the ID
7. Enter your Palau address (from your RNS.id account)
8. Submit
9. Blofin approves in 1–24 hours

**Result:** $20,000/day becomes **$1,000,000/day**. Your money can now move freely.

### When to Get It

| Your Account Size | Do You Need Palau ID? |
|---|---|
| $5 – $500 | **No.** $20K/day is more than enough. |
| $1,000 – $10,000 | **No.** Still plenty of room. |
| $50,000 – $100,000 | **Maybe.** Getting close. |
| $100,000+ and withdrawing $20K+ days | **Yes.** This is when it matters. |
| You live in a blocked country | **Yes.** Only way to fully KYC on Blofin. |

> **Bottom line:** Start with $5 and no KYC. Let it grow. When your balance is big enough that $20K/day feels tight, THEN get the Palau ID. It's a $248 investment that opens every door. Your $5 can get there. Many have. This is the path.

---

## TROUBLESHOOTING

### "I can't find Command Prompt"
1. Press the **Windows key**
2. Type **"cmd"** (without quotes)
3. Press **Enter**
4. If nothing happens, try typing **"command"** instead of "cmd"
5. Still nothing? Press Windows key + R, type `cmd`, press Enter

### "git is not recognized"
- You probably didn't install Git, or you need to restart your computer.
- Fix: Install Git from [git-scm.com](https://git-scm.com/download/win), then **restart your computer**.

### "python is not recognized"
- You didn't check the "Add to PATH" box during Python installation.
- Fix: Uninstall Python (Settings → Apps → Python → Uninstall), reinstall from [python.org](https://python.org), and **CHECK THE BOX** that says "Add Python to PATH".

### "npm is not recognized"
- Node.js didn't install properly, or you need to restart.
- Fix: Reinstall Node.js from [nodejs.org](https://nodejs.org), then **restart your computer**.

### "Blofin credentials not found"
- The file `1B Blofin API.txt` is not in the right folder.
- Fix: Check that it's in `OneDrive → Documents` with that EXACT name. Capital B, capital A, spaces in the right places.

### "OpenRouter key file not found"
- Same issue. Check `1BananaOnTheWall Openrouter API Key.txt` is in `OneDrive → Documents`.

### Dashboard is blank or says "No connection"
- The dashboard server didn't start properly.
- Fix: Double-click **Stop OWL Swarm**, wait 10 seconds, then double-click **OWL Swarm Launcher** again.

### PowerShell window opens and closes immediately
- The bot had an error on startup.
- Fix: Right-click your **OWL Swarm Launcher** icon → **Properties**. In the Target box, add `-NoExit` before `-ExecutionPolicy`. So it looks like:
  ```
  C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -NoExit -ExecutionPolicy Bypass -File "..."
  ```
  This keeps the window open so you can see the error message.

### Chrome doesn't open by itself
- No problem. The bot is still running. Open Chrome manually and type: `http://127.0.0.1:7878`

### ProtonVPN disconnects sometimes
- In the ProtonVPN app, go to **Settings** and turn ON **Kill Switch** and **Always-On VPN**.
- This stops ALL internet if the VPN drops, preventing accidental IP leaks.

### Bot hasn't placed any trades
- **This is normal and expected.** The bot is selective. It scans ~500 coins and only trades when a setup passes its risk gate.
- Check your PowerShell log for messages like "Risk gate veto" or "No candidate passed" — these mean the bot is working correctly, just waiting for a good setup.
- With a small balance, it takes longer to find affordable coins. Be patient. It will trade.
- **Your money is safe.** The bot doesn't trade recklessly. It protects your balance first.

### My equity is going down
- Small ups and downs are normal. The bot uses stop-losses to cut losing trades quickly.
- If your equity drops more than 20% from its peak, consider stopping and investigating.
- On a $5 account, a 20% drop is $1. That's the cost of one small losing trade. The bot will recover.
- **Remember:** Survival first, profit second. The bot is designed to preserve your capital.

### Blofin says "Access from your region is restricted"
- Your ProtonVPN is connected to the **United States** (or another blocked country).
- Fix: Use the **Change Server** button in ProtonVPN with the timing protocol from Phase 2.3 (1:30 → 1:40 → 1:50).
- You need Netherlands or Japan for Blofin to work.

### I keep getting United States on ProtonVPN
- ProtonVPN free has 3 countries: Netherlands, Japan, United States.
- You have a 2-in-3 chance of getting a good one each time.
- If you get US 3 times in a row, close the ProtonVPN app completely and reopen it. The server pool resets.

---

## MAC USERS — READ THIS

If you're on a Mac instead of Windows, almost everything is the same. Here are the differences:

| Windows | Mac |
|---|---|
| Command Prompt | **Terminal** (find it in Applications → Utilities → Terminal) |
| `C:\Users\YourName\...` | `/Users/YourName/...` |
| Desktop shortcuts | Right-click desktop → **New Folder** or use **Automator** to make shortcuts |
| PowerShell (`.ps1` files) | Terminal (`.sh` files) — the bot has a `launch.sh` and `stop.sh` for Mac |
| `.exe` installers | `.dmg` or `.pkg` installers |
| Git for Windows | Git for Mac — download from [git-scm.com/download/mac](https://git-scm.com/download/mac) |
| Python for Windows | Python for Mac — download from [python.org](https://python.org) |
| Node.js for Windows | Node.js for Mac — download from [nodejs.org](https://nodejs.org) |

**The bot code itself works on Mac.** The only difference is how you open the terminal and run the launch scripts. The `trading-engine` folder has Mac-compatible launch scripts.

**To open Terminal:** Press Command + Space, type "terminal", press Enter.

**To download the code:** In Terminal, type:
```bash
cd ~
git clone https://github.com/mknight2690-sys/owl-swarm-trading-stack.git
```

**To run the bot:** In Terminal, type:
```bash
cd ~/owl-swarm-trading-stack
./launch.sh
```

**Credential files:** Save to `~/Documents/` (your Documents folder) with the same exact names:
- `1B Blofin API.txt`
- `1BananaOnTheWall Openrouter API Key.txt`

> **Mac users: If you want the easiest path, use Path A (the AI agent way) below. The AI will handle all Mac vs Windows differences for you.**

---

## THE "STUPID EASY" WAY: USE A FREE AI AGENT

If everything above feels overwhelming, **there is an easier way.** You can use a free AI assistant to do ALL the installation steps for you. You just copy and paste one prompt, and the AI handles everything.

### What You Need
- [Cursor](https://cursor.com) — a free AI code editor. It's like ChatGPT but it can also type on your computer and run commands for you.
- About 15 minutes of watching the AI work

### Step A: Install Cursor

1. Go to [cursor.com](https://cursor.com) in Chrome
2. Click **Download for Free**
3. Download the Windows installer (or Mac installer if you're on Mac)
4. Double-click the downloaded file and follow the installation steps (click Next, accept defaults)
5. Open Cursor from your desktop or Start menu
6. Sign up with your email or Google account (free plan is all you need)

### Step B: Give the AI One Prompt

1. Open Cursor
2. You will see a chat box at the bottom or side of the screen
3. Copy and paste this ENTIRE prompt into the chat box (it's long, but it's everything the AI needs):

---

```
I need you to set up the OWL Swarm Trading Bot for me. Please do ALL of the following steps. I am a beginner and need you to handle everything.

MY INFO:
- My computer is Windows (or Mac: change this line)
- My username is: [TYPE YOUR WINDOWS USERNAME HERE]
- My Blofin API credentials are in a file on my Desktop called "My Blofin Keys.txt"
- My OpenRouter API key is in a file on my Desktop called "My OpenRouter Key.txt"

STEPS TO DO:

1. Check if Git is installed. If not, tell me to download it from https://git-scm.com/download/win and wait for me to install it.
2. Check if Python 3.12 is installed. If not, tell me to download it from https://python.org and wait for me to install it (make sure I check "Add to PATH").
3. Check if Node.js is installed. If not, tell me to download it from https://nodejs.org and wait for me to install it.
4. Open Command Prompt (or Terminal on Mac) and run: cd %USERPROFILE% (or cd ~ on Mac), then git clone https://github.com/mknight2690-sys/owl-swarm-trading-stack.git
5. Read the Blofin credentials from my Desktop file and create a new file at [OneDrive/Documents/1B Blofin API.txt] with the exact same content. Make sure the filename is EXACTLY "1B Blofin API.txt".
6. Read the OpenRouter key from my Desktop file and create a new file at [OneDrive/Documents/1BananaOnTheWall Openrouter API Key.txt] with the exact same content. Make sure the filename is EXACTLY "1BananaOnTheWall Openrouter API Key.txt".
7. Install Python dependencies: cd into the trading-engine folder and run "pip install -e ."
8. Install Node.js dependencies: cd into the owl-swarm-trading-stack folder and run "npm install"
9. Compile the dashboard: run "npx tsc --project tsconfig.json"
10. Create desktop shortcuts for launch.ps1 and stop.ps1 (or launch.sh and stop.sh on Mac)
11. Launch the bot and open the dashboard in Chrome

Please tell me what you're doing at each step. If anything fails, tell me exactly what went wrong and how to fix it. Be patient with me. I'm new to this.
```

---

4. Press **Enter** to send the prompt to the AI
5. The AI will start working through each step
6. It will ask you questions if it needs something
7. It will tell you exactly what to click and type
8. If something goes wrong, just type: "That didn't work. What should I do?" and the AI will fix it

### Why This Way Is Better

- **No guesswork.** The AI sees your exact computer setup and handles all the differences.
- **Real-time help.** If something breaks, the AI diagnoses it and fixes it on the spot.
- **You learn by watching.** You see what the AI does, so you understand your setup better.
- **It works on Mac too.** The AI knows the difference between Windows and Mac and adapts automatically.

> **If the AI path fails at any point, you can switch to the manual steps above for just that one step, then go back to the AI.** There's no wrong way to do this. The only wrong way is giving up.

---

## QUICK REFERENCE CHEAT SHEET

| I Want To... | How To Do It |
|---|---|
| **Start the bot** | Double-click **OWL Swarm Launcher** icon |
| **Stop the bot** | Double-click **Stop OWL Swarm** icon |
| **See my dashboard** | Open Chrome → type `http://127.0.0.1:7878` |
| **Check my trades** | Go to [blofin.com](https://blofin.com) → log in → Positions tab |
| **Add more money** | Coinbase → Buy USDT → Send to Blofin (TRC20 network) |
| **Update the bot code** | Command Prompt → `cd owl-swarm-trading-stack` → `git pull` |
| **Check bot logs** | Open `C:\Users\YOU\owl-swarm-trading-stack\outputs\live-run.log` in Notepad |
| **Change VPN server** | ProtonVPN → **Change Server** → wait 1:30 / 1:40 / 1:50 |
| **Get Palau ID** | [rns.id](https://rns.id) → $248/year → unlocks $1M/day withdrawals |
| **Use AI to install everything** | Install [Cursor](https://cursor.com) → paste the prompt from "The Stupid Easy Way" section |

---

## SECURITY CHECKLIST

- [ ] My Blofin API key only has **Read** and **Trade** permissions (Withdraw is OFF)
- [ ] My API keys are stored in text files, NOT pasted into the bot code
- [ ] ProtonVPN is always connected to **Netherlands** or **Japan** when the bot runs
- [ ] My computer has a password/login screen
- [ ] Nobody else uses my computer or knows my credential file locations
- [ ] I understand: **only trade what you can afford to lose.** This is a tool, not a guarantee. The bot is designed to survive first and profit second, but losses can still happen.
- [ ] I wrote down my 2FA backup code from Blofin somewhere safe
- [ ] **Optional:** Palau ID secured for when my account grows big

---

## END OF TUTORIAL

**You made it. You're here. That alone puts you ahead of 99% of people who never start.**

Whether you have $3 or $300, whether you know everything about computers or nothing at all — the bot is running now. Your money is working. Let it compound. Let it grow. Check on it. Be patient. Trust the process.

**Your $5 can become $50. Your $50 can become $500. Your $500 can become $5,000.** We've seen it. The math works. The risk gate protects you. The stop-losses cut the losers. The winners run. That's how compounding works. That's how this works.

**Now go prove it.** 🦉

**File saved to:** `C:\Users\mknig\OneDrive\Documents\Kimi\Workspaces\Owl Swarm\OWL_SWARM_SETUP_TUTORIAL.md`

**Public link:** [github.com/mknight2690-sys/owl-swarm-trading-stack/blob/master/OWL_SWARM_SETUP_TUTORIAL.md](https://github.com/mknight2690-sys/owl-swarm-trading-stack/blob/master/OWL_SWARM_SETUP_TUTORIAL.md)
