OWL SWARM TRADING STACK — Quick-Start Guide (One-Page Printable)

**Version:** 1.7 Quick-Start | **Updated:** 2026-07-03

---

## WHAT THIS IS

A free trading bot that runs on your computer, trades crypto for you 24/7, and costs $0 to operate. Start with $3, $5, $50, or whatever you are comfortable with. No monthly fees. No subscriptions.

---

## BEFORE YOU START

| What You Need | Details |
|---|---|
| Computer | Any Windows 10/11 or Mac laptop/desktop that can stay on |
| Internet | WiFi or Ethernet |
| Browser | Chrome |
| Money | Whatever you can afford to lose ($3 works) |
| Time | About 30 minutes to set up |

---

## STEP 1: GET PROTONVPN (FREE)

1. Go to [protonvpn.com](https://protonvpn.com) → sign up free → download → install
2. Open app → click **Quick Connect**
3. **Look at the top of the app.** You need **Netherlands** or **Japan**. If it says **United States**, click **Change Server**, wait 1:30, check again. Repeat up to 3 times.
4. Leave it connected 24/7. Turn on **Kill Switch** and **Always-On VPN** in settings.

> **Why:** Blofin blocks US/Canada. The VPN hides your real location.

---

## STEP 2: CREATE BLOFIN ACCOUNT

**Must have ProtonVPN connected to Netherlands or Japan first.**

1. Go to [blofin.com](https://blofin.com) → **Sign Up**
2. Use email, create password, verify email
3. If asked for country: say **Netherlands** or **Japan** (whichever your VPN shows)

> **No ID upload needed.** You can trade and withdraw up to $20,000/day immediately.

---

## STEP 3: SET UP 2FA (GOOGLE AUTHENTICATOR)

**Get the app:**
- **iPhone:** App Store → search "Google Authenticator" → install
- **Android:** Google Play Store → search "Google Authenticator" → install

**Set up on Blofin:**
1. Blofin → profile icon → **Security** → **Google Authenticator** → **Bind**
2. Blofin shows a QR code
3. On your phone: open Google Authenticator → tap **+** → **Scan QR code** → point at computer screen
4. Enter the 6-digit code from your phone into Blofin
5. **Write down the backup code Blofin gives you.** Save it somewhere safe.

---

## STEP 4: CREATE BLOFIN API KEYS

1. Blofin → profile icon → **API Management** → **Create API Key**
2. Name: `OWL-Swarm-Trading`
3. Permissions:
   - ✅ **Read**
   - ✅ **Trade**
   - ❌ **Withdraw** (leave OFF)
4. Click **Create**
5. Enter your 2FA code from Google Authenticator
6. **Copy all 3 values immediately** (Blofin only shows them once):
   - API Key
   - Secret Key
   - Passphrase

---

## STEP 5: SAVE YOUR KEYS TO DESKTOP

Open Notepad (Windows key → type "notepad" → Enter):

```
API Key: [paste your API key here]
Secret Key: [paste your secret key here]
Passphrase: [paste your passphrase here]
```

Save As → Desktop → filename: `My Blofin Keys.txt`

---

## STEP 6: GET OPENROUTER API KEY (FREE)

1. Go to [openrouter.ai](https://openrouter.ai) → **Sign Up** (Google account is fastest)
2. Profile icon → **Keys** → **Create Key** → name it `OWL-Swarm` → copy the key (starts with `sk-or-`)
3. Profile icon → **Settings** → turn ON **"Enable free models"**

Open Notepad again:
```
OpenRouter API Key: [paste your key here]
```
Save As → Desktop → filename: `My OpenRouter Key.txt`

---

## STEP 7: BUY USDT ON COINBASE

1. Go to [coinbase.com](https://coinbase.com) → sign up → verify email
2. **Buy & Sell** → select **USDT** → enter amount ($5 or whatever) → pay with debit card

> **$3 is enough.** The bot works with any amount.

---

## STEP 8: SEND USDT TO BLOFIN

1. Blofin → **Assets** → **Deposit** → select **USDT** → select **TRC20** network
2. Click **Copy** next to the deposit address
3. Coinbase → **Send / Receive** → select **USDT** → paste Blofin address → select **TRC20** → enter amount → **Send now**
4. Wait 5–10 minutes. Costs about $1 fee regardless of amount.

---

## STEP 9: MOVE USDT TO FUTURES WALLET (CRITICAL)

**The bot trades futures. Your money must be in the Futures Wallet, NOT the Spot Wallet.**

1. Blofin → **Assets**
2. Find your USDT balance in the **Spot** section
3. Click **Transfer** (or **Spot → Futures**)
4. Select **USDT** → enter amount → **Confirm**

> **If you skip this, the bot sees $0 and won't trade.**

---

## STEP 10: USE FREE AI TO INSTALL EVERYTHING

**Open a free AI chat:**
- Go to [kimi.com](https://kimi.com) (recommended) or [chat.openai.com](https://chat.openai.com) or [claude.ai](https://claude.ai)
- Sign up free (email only, no credit card)

**Copy and paste this ENTIRE prompt into the chat:**

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

**Before sending:** Replace `[TYPE YOUR USERNAME HERE]` with your actual computer username.

**Then:** Just follow the AI's instructions. It will tell you exactly what to click and type, one step at a time. If something doesn't work, tell the AI and it will fix it.

---

## STEP 11: LAUNCH

After the AI finishes, you will have two icons on your desktop:
- **OWL Swarm Launcher** (start the bot)
- **Stop OWL Swarm** (stop the bot)

1. Make sure ProtonVPN is still connected to Netherlands or Japan
2. Make sure your USDT is in your **Futures Wallet** on Blofin
3. Double-click **OWL Swarm Launcher**
4. Wait 60 seconds — Chrome opens automatically showing your dashboard

---

## DAILY USE (10 SECONDS)

**You do NOT restart the bot every day.** It stays running as long as your computer stays on.

1. Glance at the dashboard in Chrome
2. Look at the **top left corner**
3. Check that **"Updated: [time]"** is counting up by the second
4. If yes — the bot is alive and working. You're done.
5. If frozen — double-click **OWL Swarm Launcher** to restart

**Keep your computer awake:**
- Windows key → type "power" → **Power & sleep settings** → set **Sleep** to **Never**
- Don't close the PowerShell window. Minimize it if you need to use your computer.

---

## ADD MORE MONEY LATER

1. Stop the bot (double-click **Stop OWL Swarm**)
2. Buy more USDT on Coinbase
3. Send to your same Blofin address (TRC20, same $1 fee)
4. Transfer from Spot Wallet to Futures Wallet
5. Restart the bot (double-click **OWL Swarm Launcher**)

---

## WHEN YOUR ACCOUNT GROWS BIG (OPTIONAL)

Blofin's $20,000/day withdrawal limit is plenty for most people. But if you grow to $100,000+ and need more:

**Palau Digital Residency ID** — $248/year at [rns.id](https://rns.id)
- Real government ID from a sovereign nation
- Accepted by Blofin, Binance, Bybit, KuCoin
- Raises your limit from $20K/day to **$1,000,000/day**
- Only get this when you actually need it

---

## SECURITY REMINDERS

- ✅ Blofin API key: Read + Trade only. Withdraw = OFF.
- ✅ ProtonVPN: Always on, always Netherlands or Japan.
- ✅ Only trade what you can afford to lose.
- ✅ Write down your 2FA backup code.

---

## QUICK FIXES

| Problem | Fix |
|---|---|
| Bot shows $0 balance | Move USDT from Spot Wallet to Futures Wallet on Blofin |
| "git/python/npm not recognized" | Restart your computer after installing |
| Dashboard blank | Stop bot → wait 10 sec → restart bot |
| No trades showing | Normal. Bot is selective. Be patient. |
| Blofin says "region restricted" | ProtonVPN is on US server. Change to Netherlands/Japan. |

---

## LINKS

- **ProtonVPN:** [protonvpn.com](https://protonvpn.com)
- **Blofin:** [blofin.com](https://blofin.com)
- **OpenRouter:** [openrouter.ai](https://openrouter.ai)
- **Coinbase:** [coinbase.com](https://coinbase.com)
- **Kimi (free AI assistant):** [kimi.com](https://kimi.com)
- **ChatGPT (free AI assistant):** [chat.openai.com](https://chat.openai.com)
- **Claude (free AI assistant):** [claude.ai](https://claude.ai)
- **Palau ID (optional upgrade):** [rns.id](https://rns.id)
- **Bot code:** [github.com/mknight2690-sys/owl-swarm-trading-stack](https://github.com/mknight2690-sys/owl-swarm-trading-stack)
- **Full tutorial:** [github.com/mknight2690-sys/owl-swarm-trading-stack/blob/master/OWL_SWARM_SETUP_TUTORIAL.md](https://github.com/mknight2690-sys/owl-swarm-trading-stack/blob/master/OWL_SWARM_SETUP_TUTORIAL.md)

---

**You can do this. Your $3 can grow. Your $5 can grow. Let it compound. 🦉**

**File saved to:** `C:\Users\mknig\OneDrive\Documents\Kimi\Workspaces\Owl Swarm\OWL_SWARM_QUICKSTART.md`
