# Missed-Call Agent — v1

What this does: when someone calls your trade business and you can't pick up, it texts
them back within seconds, has a short AI conversation to capture the job details, and
copies you on the whole thing so you stay in control.

This is a pilot, not a finished product. Scope is deliberately tiny — one job: stop
losing enquiries to a missed call.

---

## 1. Get the three accounts you need

You only need to do this once.

1. **Twilio** — [twilio.com/try-twilio](https://www.twilio.com/try-twilio). Sign up,
   verify your email + phone. Then **buy a UK phone number**: Console > Phone Numbers >
   Buy a number (make sure it has Voice + SMS capability). Grab your **Account SID** and
   **Auth Token** from Console > Account > API keys & tokens.
2. **Anthropic API key** — [console.anthropic.com](https://console.anthropic.com) > API
   Keys > Create key. (Separate from your claude.ai login — this is the pay-as-you-go
   API. For SMS-length replies, cost per conversation is fractions of a penny.)
3. **Render** — [render.com](https://render.com). Free account. This hosts the server
   so it's always reachable (don't use ngrok for anything beyond a 5-minute local test —
   the URL changes every restart).

## 2. Fill in your config

Copy `.env.example` to `.env` and fill in the real values — your Twilio SID/token, the
Twilio number you bought, your own mobile (`OWNER_PHONE`), your Anthropic key, and the
business name/owner name/trade so the assistant's texts sound right.

## 3. Deploy to Render

1. Push this folder to a GitHub repo (Render deploys from a repo — takes 2 minutes if
   you don't already have one: create a repo on github.com, upload these files).
2. Render dashboard > New > Web Service > connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Add every variable from your `.env` file under Environment in the Render dashboard
   (Render won't read your local `.env` — you re-enter them there).
6. **Use a paid instance, not the free tier**, even for the pilot. Free instances sleep
   after inactivity — the first call after a quiet spell would hit a 30-second cold
   start, which defeats the entire point. The cheapest paid tier (~$7/mo) is fine.
7. Deploy. You'll get a URL like `https://your-app.onrender.com`.

## 4. Point the Twilio number at it

In the Twilio console, on your number's configuration page:

- **Voice > A call comes in:** Webhook → `https://your-app.onrender.com/voice` → HTTP POST
- **Messaging > A message comes in:** Webhook → `https://your-app.onrender.com/sms` → HTTP POST

## 5. Test it for real

1. Call the Twilio number from a different phone. Let your own mobile (`OWNER_PHONE`)
   ring and **don't answer it** (deliberately, this once).
2. You should get a text on the calling phone within a couple seconds.
3. Reply naturally, like a real customer would ("kitchen tap's leaking badly").
4. Watch it ask one follow-up at a time (postcode, urgency, callback time).
5. Check `OWNER_PHONE` is receiving a copy of every exchange.

If a step doesn't fire: check Render's logs tab first, then Twilio Console > Monitor >
Logs > Errors — that'll show exactly which webhook failed and why.

## What's deliberately NOT in v1

No booking calendar, no database, no multi-business support, no voice AI (the
"conversation" is all SMS, not the customer talking to a robot on the phone). Don't add
any of this until you've shown it to a real plumber/electrician and they've said "yes,
build me one." Adding features before that conversation is exactly the trap we're
avoiding.

## One thing to be straight about

The assistant identifies itself as an assistant if asked, and is genuinely sending the
business's own reply to its own inbound enquiries — not cold outreach or marketing. Keep
it that way: this pattern (instant reply to someone who just contacted *you*) is on far
safer ground than anything that messages people who haven't reached out first.
