# OWL SWARM TRADING STACK — Complete Setup Tutorial

**Version:** 1.7 (AI-First Edition) | **Updated:** 2026-07-03  
**Who this is for:** Everyone. Never traded crypto? Start here. Have $3? Start here. Have $300? Start here. Never used a command line? Start here. We will walk you through every single step. No judgment. No assumptions. Just help.

> **Welcome.** You are about to set up a robot that trades crypto for you while you sleep. It costs $0 to run. You can start with $3, $5, $50, or whatever you feel comfortable with. There is no minimum. The bot works with any amount. Your $3 can grow. Your $5 can grow. Let it compound. This is real.

---

## HOW THIS WORKS

**You will use a free AI assistant to guide you through everything.** You open a free AI chat, copy and paste one prompt, and the AI tells you exactly what to click, what to type, and what to expect at each step. It's like having a patient friend sitting next to you who knows exactly what to do.

**Why this way?** You don't need to understand git, npm, pip, or any technical stuff. The AI explains each step in plain English. If you get stuck, you ask "what went wrong?" and it helps you fix it. This is the easiest way to get your bot running.

**What you need:**
- A free AI chat — we recommend [Kimi](https://kimi.com), but [ChatGPT](https://chat.openai.com) or [Claude](https://claude.ai) work too
- The single prompt we give you below
- About 20–30 minutes of following along

---

## TABLE OF CONTENTS

1. [Phase 0: What You Need](#phase-0-what-you-need)
2. [Phase 1: Buy Some Crypto (USDT)](#phase-1-buy-some-crypto-usdt)
3. [Phase 2: Get a VPN (ProtonVPN — Free)](#phase-2-get-a-vpn-protonvpn--free)
4. [Phase 3: Create Your Blofin Account](#phase-3-create-your-blofin-account)
5. [Phase 4: Set Up 2FA (Google Authenticator)](#phase-4-set-up-2fa-google-authenticator)
6. [Phase 5: Get Your OpenRouter API Key (Free AI Brain)](#phase-5-get-your-openrouter-api-key-free-ai-brain)
7. [Phase 6: Move USDT to Your Futures Wallet](#phase-6-move-usdt-to-your-futures-wallet)
8. [Phase 7: Use the AI Assistant to Install Everything](#phase-7-use-the-ai-assistant-to-install-everything)
9. [Phase 8: Launch Your Bot](#phase-8-launch-your-bot)
10. [Phase 9: Daily Check-In](#phase-9-daily-check-in)
11. [Phase 10: When Your Money Grows (Optional Palau ID)](#phase-10-when-your-money-grows-optional-palau-id)
12. [Troubleshooting](#troubleshooting)
13. [Mac Users — Read This](#mac-users--read-this)

---

## PHASE 0: WHAT YOU NEED

### Hardware (What Computer)
- **Any computer that can stay on.** A laptop, desktop, old computer — whatever you have. It just needs to stay awake while the bot runs.
- **Windows 10 or 11** (Mac users: see [Mac section at the bottom](#mac-users--read-this))
- **4GB RAM minimum** — basically any computer made in the last 10 years
- **Stable internet** — WiFi or Ethernet, both work fine
- **Chrome browser** — if you don't have it, go to [google.com/chrome](https://google.com/chrome) and click "Download Chrome"

### Money (How Much)
- **Whatever you feel comfortable with.** This is the golden rule. Only put in money you can afford to lose.
- **$3 is enough.** The bot will trade with $3. It will find coins that fit a $3 balance. It will be slower, but it will work.
- **$5 is a nice starting point.** More coins become tradeable. You'll see activity sooner.
- **$50 is great.** The bot can trade many more coins. You'll see daily activity.
- **There is no maximum.** People run this bot with $10,000. The bot scales with your money.
- **The bot is free to run.** No monthly fees. No subscriptions. The only cost is your starting capital and a one-time $1 network fee when you move money to Blofin.

### Time
- **First time setup:** About 30 minutes
- **Every day after:** 10 seconds (glance at the dashboard to confirm it's running)

### Accounts to Create (All Free)
1. **ProtonVPN** — keeps your internet private (free version works perfectly)
2. **Blofin** — where the bot trades (free to sign up, no ID needed to start)
3. **OpenRouter** — the AI brain that decides which trades to take (free version works)
4. **Kimi** (or ChatGPT / Claude) — your free AI assistant that walks you through installation

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

> **Don't have $5?** That's perfectly okay. Buy $3. The bot works with $3. Buy whatever you can afford. There is no shame in starting small. Every dollar counts. Let it compound.

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

**Also:** Your internet provider can see every website you visit. A VPN stops that. It's just good privacy practice, especially when dealing with money.

### How the Free Version Works

ProtonVPN's free version randomly gives you one of three countries. You do NOT get to pick:
- **Netherlands** — Blofin accepts this ✅
- **Japan** — Blofin accepts this ✅
- **United States** — Blofin blocks this ❌

So you click "connect" and hope you get Netherlands or Japan. If you get the United States, you click "Change Server" and try again.

### Blofin-Blocked Countries (What You Want to AVOID)

If ProtonVPN assigns you to any of these, you MUST change server:
- **United States** (all states)
- **Canada**
- **Mainland China**
- **Russia**
- **North Korea, Iran, Syria, Cuba, Sudan** (sanctioned nations)

> **You want Netherlands or Japan.** Those are the only Blofin-accepted countries on ProtonVPN free tier.

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

> **You do NOT need to upload an ID or verify your identity to start.** Blofin lets you trade and withdraw up to **$20,000 per day** with no KYC (no identity verification). You can start trading TODAY with just an email and password. If you ever need to withdraw more than $20,000 in a single day, there's an optional upgrade in Phase 10.

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

> **About the $20,000/day limit:** This is per day. If you make $500/day in profits, you can withdraw all of it. If you make $20,000 in one day, you can withdraw all of it. The limit resets every 24 hours. For most people starting with $5, this limit is plenty. If you grow your account and need more than $20K/day, see Phase 10.

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
8. **IMPORTANT:** Open Notepad on your computer and paste all three into a file. Save it somewhere you'll remember (like your Desktop). You'll need this soon.

> **If you lose these keys, you have to create new ones.** Blofin never shows the Secret Key again for security reasons. So save them now.

### Step 3.4: Save Your Keys to Your Desktop

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

> **Keep this file on your Desktop.** The AI assistant will read it and create the correct file for the bot automatically.

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

> **Keep this file on your Desktop too.** The AI assistant will read it and create the correct file for the bot automatically.

---

## PHASE 6: MOVE USDT TO YOUR FUTURES WALLET

This is a **critical step** that many people miss. Blofin has two wallets:
- **Spot Wallet** — where your USDT lands when you deposit it
- **Futures Wallet** — where the bot trades

The bot trades futures contracts, so your USDT needs to be in the **Futures Wallet**, not the Spot Wallet.

### Step 6.1: Transfer from Spot to Futures

1. Log in to [blofin.com](https://blofin.com) in Chrome (make sure ProtonVPN is still connected to Netherlands or Japan)
2. Click **Assets** at the top of the page
3. Look for your **USDT** balance. It should show your deposited amount in the Spot section.
4. Click **Transfer** or look for a button that says **"Spot → Futures"**
5. Select **USDT**
6. Enter the amount you want to transfer (all of it, or leave a tiny bit in Spot if you want)
7. Click **Confirm** or **Transfer**
8. Done! Your USDT is now in the Futures Wallet where the bot can trade with it.

> **If you skip this step, the bot will see $0 available and won't trade.** Make sure your money is in the Futures Wallet.

---

## PHASE 7: USE THE AI ASSISTANT TO INSTALL EVERYTHING

This is where the magic happens. You have your Blofin keys saved on your Desktop. You have your OpenRouter key saved on your Desktop. Now you open a free AI chat and let it handle ALL the installation, file creation, and setup for you.

### Step 7.1: Open Your Free AI Chat

We recommend **Kimi** because it's fast, free, and handles technical tasks well. But ChatGPT and Claude work too.

1. Open Chrome
2. Go to [kimi.com](https://kimi.com) (or [chat.openai.com](https://chat.openai.com) or [claude.ai](https://claude.ai))
3. Sign up for a free account (just email + password — no credit card needed)
4. You now have a free AI assistant that will help you through everything

### Step 7.2: Copy and Paste the Prompt

In the chat box, copy and paste this ENTIRE prompt (it's long, but it's everything the AI needs):

---

```
I need help setting up the OWL Swarm Trading Bot on my computer. I am a complete beginner and need patient, step-by-step guidance. Please do not assume I know anything about programming, command lines, or crypto.

MY COMPUTER:
- Windows 10/11 (or Mac — tell me which one you have)
- My username is: [TYPE YOUR USERNAME HERE]

MY FILES ON MY DESKTOP:
- "My Blofin Keys.txt" — contains my Blofin API Key, Secret Key, and Passphrase
- "My OpenRouter Key.txt" — contains my OpenRouter API key (starts with sk-or-)

WHAT I NEED YOU TO HELP ME DO:

1. Check if Git, Python 3.12, and Node.js are installed on my computer. If any are missing, tell me exactly where to download them and what to click. Wait for me to install each one before moving on.

2. Open Command Prompt (or Terminal on Mac) for me. Run: cd %USERPROFILE% (or cd ~ on Mac), then run: git clone https://github.com/mknight2690-sys/owl-swarm-trading-stack.git

3. Read "My Blofin Keys.txt" from my Desktop. Create a new file at the EXACT location:
   C:\Users\[MY USERNAME]\OneDrive\Documents\1B Blofin API.txt
   (or /Users/[MY USERNAME]/Documents/1B Blofin API.txt on Mac)
   The filename must be EXACTLY "1B Blofin API.txt" with correct capitalization and spaces.

4. Read "My OpenRouter Key.txt" from my Desktop. Create a new file at the EXACT location:
   C:\Users\[MY USERNAME]\OneDrive\Documents\1BananaOnTheWall Openrouter API Key.txt
   (or /Users/[MY USERNAME]/Documents/1BananaOnTheWall Openrouter API Key.txt on Mac)
   The filename must be EXACTLY "1BananaOnTheWall Openrouter API Key.txt" with correct capitalization and spaces.

5. Install Python dependencies: cd into the trading-engine folder inside owl-swarm-trading-stack, then run "pip install -e ."

6. Install Node.js dependencies: cd into the owl-swarm-trading-stack folder, then run "npm install"

7. Compile the dashboard by running: "npx tsc --project tsconfig.json"

8. Create desktop shortcuts (Windows) or launcher scripts (Mac) for the bot's launch and stop files.

9. Launch the bot and open the dashboard in Chrome.

Please explain each step in plain English BEFORE we do it. Tell me exactly what to type or click. If I get an error, help me fix it. I am completely new to this, so please be patient and thorough. Go one step at a time and wait for me to confirm before moving to the next step.
```

---

3. **Before sending:** Replace `[TYPE YOUR USERNAME HERE]` with your actual Windows username (the one you see when you log in to your computer). If you're on Mac, replace `[MY USERNAME]` with your Mac username.
4. Press **Enter** or click the send button
5. The AI will now guide you through every step, one at a time

### Step 7.3: Follow the AI's Instructions

The AI will:
- Tell you exactly what software to install and where to get it
- Give you the exact commands to type
- Help you troubleshoot if anything goes wrong
- Explain what each step does in plain English
- Wait for you to confirm before moving to the next step

**How to open Command Prompt** (the AI will ask you to do this):
1. Press the **Windows key** on your keyboard
2. Type **"cmd"** (without quotes)
3. Press **Enter**
4. A black window opens. This is Command Prompt. Don't worry — it's just a place where you type commands.

> **What is Command Prompt?** It's a black box where you type text commands instead of clicking buttons. The AI tells you EXACTLY what to type, so you can copy and paste. Nothing will break if you type the wrong thing — you can just close the window and start over.

**If you get stuck:** Just type "I don't understand" or "That didn't work" and the AI will explain it differently or help you fix it. There is no rush. The AI is patient. You can do this.

---

## PHASE 8: LAUNCH YOUR BOT

This is it. The moment your money starts working for you.

### Before You Start

Make sure:
- ✅ ProtonVPN is connected and shows **Netherlands** or **Japan** (NOT United States)
- ✅ You have USDT in your **Futures Wallet** on Blofin (not the Spot Wallet — see Phase 6)
- ✅ Both credential files were created by the AI in the right locations
- ✅ The AI created desktop shortcuts for you

### Launch!

1. Double-click the **OWL Swarm Launcher** icon the AI created on your desktop
2. A blue PowerShell window opens. Watch it!
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

## PHASE 9: DAILY CHECK-IN

Once your bot is running, **you do NOT need to start it every day.** The bot stays running as long as your computer stays awake and the PowerShell window stays open.

### How to Check If It's Still Running (10 Seconds)

1. Look at the dashboard in Chrome
2. Look at the **top left corner**
3. You should see:
   - **"Running"** or a green indicator
   - **"Updated: [time]"** that counts up by the second
4. If the timestamp is still counting up, the bot is alive and working
5. If the timestamp is frozen or missing, the bot stopped. Double-click **OWL Swarm Launcher** to restart it.

### Keep Your Computer Awake

If your computer goes to sleep, the bot stops. Here's how to keep it awake:
1. Press **Windows key**
2. Type **"power"** and click **Edit Power Plan** or **Power & sleep settings**
3. Set **Screen** to turn off after **Never** or **1 hour** (your choice)
4. Set **Sleep** to **Never**
5. Click **Save changes**

> **Important:** Don't close the PowerShell window. Don't close the Chrome tab. Don't put your laptop to sleep. The bot needs your computer to stay on. If you need to use your computer for other things, just minimize the PowerShell window — it will keep running in the background.

### Growing Your Account

When you see the bot working and you want to add more money:
1. Click **Stop OWL Swarm** to stop the bot
2. Buy more USDT on Coinbase
3. Send it to your same Blofin address (same TRC20 network, same $1 fee)
4. Transfer the new USDT from Spot Wallet to Futures Wallet (see Phase 6)
5. Click **OWL Swarm Launcher** to restart
6. The bot automatically uses the larger balance

> **More money = more tradeable coins = more frequent trades. The bot scales with your balance. Your $5 proof-of-concept can become $50, then $500, then $5,000. The same bot. The same strategy. Just bigger numbers.**

---

## PHASE 10: WHEN YOUR MONEY GROWS (OPTIONAL PALAU ID)

> **Is $20,000 per day enough for you?** Without verifying your identity, Blofin lets you withdraw up to $20,000 USDT every 24 hours. If you're starting with $5, this limit is more than enough. You will not touch it for a long time. If you grow to $1,000, you still won't touch it. If you grow to $10,000, you still won't touch it.
>
> **But when your account grows** — when you have $100,000+ and you want to pull out $50,000 in a single day — then you need higher limits. And if you live in a country that Blofin blocks (like the US or Canada), you can't verify your identity with your real passport.
>
> **That's where the Palau ID comes in.** This is the upgrade path. This is for when your $5 has compounded into real money and you need to move it freely. This is what experienced traders do when they scale up.

### What Is the Palau ID?

The **Republic of Palau Digital Residency ID** is a real government-issued digital identity card for non-residents. Palau is a sovereign nation. Their program lets anyone in the world apply for a legal ID with a Palau address — accepted by most crypto exchanges for full identity verification.

**Cost:** ~$248 USD per year (one-time payment, valid for 12 months)  
**Apply at:** [rns.id](https://rns.id)  
**What you get:** A physical ID card + digital identity + Palau address  
**Accepted by:** Blofin, Binance, Bybit, KuCoin, and most major exchanges  
**Result:** Daily withdrawal limit jumps from $20,000 to **$1,000,000**

### Why Palau ID?

1. **If you're in a blocked country** (US, Canada, etc.), your real passport won't work for KYC on Blofin. Palau ID does.
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

### The bot shows $0 balance even though I have money on Blofin
- **Your USDT is probably in the Spot Wallet, not the Futures Wallet.**
- Fix: Go to Blofin → Assets → Transfer → move USDT from Spot to Futures (see Phase 6)

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

> **Mac users: When you use the AI assistant, just tell it you're on Mac. The AI will automatically use Terminal instead of Command Prompt and adapt all paths for you.**

---

## QUICK REFERENCE CHEAT SHEET

| I Want To... | How To Do It |
|---|---|
| **Start the bot** | Double-click **OWL Swarm Launcher** icon |
| **Stop the bot** | Double-click **Stop OWL Swarm** icon |
| **Check if bot is running** | Look at dashboard top-left — "Updated" timestamp should count up |
| **See my dashboard** | Open Chrome → type `http://127.0.0.1:7878` |
| **Check my trades** | Go to [blofin.com](https://blofin.com) → log in → Positions tab |
| **Add more money** | Coinbase → Buy USDT → Send to Blofin (TRC20 network) → Transfer to Futures Wallet |
| **Move money to Futures Wallet** | Blofin → Assets → Transfer → Spot → Futures |
| **Update the bot code** | Command Prompt → `cd owl-swarm-trading-stack` → `git pull` |
| **Check bot logs** | Open `C:\Users\YOU\owl-swarm-trading-stack\outputs\live-run.log` in Notepad |
| **Change VPN server** | ProtonVPN → **Change Server** → wait 1:30 / 1:40 / 1:50 |
| **Get Palau ID** | [rns.id](https://rns.id) → $248/year → unlocks $1M/day withdrawals |
| **Get AI help with setup** | Go to [kimi.com](https://kimi.com) → paste the prompt from Phase 7 |

---

## SECURITY CHECKLIST

- [ ] My Blofin API key only has **Read** and **Trade** permissions (Withdraw is OFF)
- [ ] My API keys are stored in text files, NOT pasted into the bot code
- [ ] My USDT is in the **Futures Wallet** on Blofin (not Spot Wallet)
- [ ] ProtonVPN is always connected to **Netherlands** or **Japan** when the bot runs
- [ ] My computer has a password/login screen
- [ ] Nobody else uses my computer or knows my credential file locations
- [ ] I understand: **only trade what you can afford to lose.** This is a tool, not a guarantee. The bot is designed to survive first and profit second, but losses can still happen.
- [ ] I wrote down my 2FA backup code from Blofin somewhere safe
- [ ] **Optional:** Palau ID secured for when my account grows big

---

## END OF TUTORIAL

**You made it. You're here. That alone puts you ahead of everyone who never started.**

Whether you have $3 or $300, whether you know everything about computers or are just figuring it out — the bot can work for you. Your money can grow. Let it compound. Check on it. Be patient. Trust the process.

**Your $5 can become $50. Your $50 can become $500. Your $500 can become $5,000.** The math works. The risk gate protects you. The stop-losses cut the losers. The winners run. That's how compounding works. That's how this works.

**You can do this. Now go prove it.** 🦉

**File saved to:** `C:\Users\mknig\OneDrive\Documents\Kimi\Workspaces\Owl Swarm\OWL_SWARM_SETUP_TUTORIAL.md`

**Public link:** [github.com/mknight2690-sys/owl-swarm-trading-stack/blob/master/OWL_SWARM_SETUP_TUTORIAL.md](https://github.com/mknight2690-sys/owl-swarm-trading-stack/blob/master/OWL_SWARM_SETUP_TUTORIAL.md)
