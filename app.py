import os
import logging

from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Dial
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
from twilio.rest import Client
import anthropic

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("missed-call-agent")

app = Flask(__name__)

# ---- Config (all set as environment variables — see .env.example) ----
TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_NUMBER = os.environ["TWILIO_NUMBER"]        # the Twilio number customers call/text, e.g. +44...
OWNER_PHONE = os.environ["OWNER_PHONE"]            # the tradesperson's real mobile, e.g. +44...
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

BUSINESS_NAME = os.environ.get("BUSINESS_NAME", "the business")
OWNER_NAME = os.environ.get("OWNER_NAME", "the owner")
TRADE = os.environ.get("TRADE", "trades")
RING_TIMEOUT = int(os.environ.get("RING_TIMEOUT_SECONDS", "18"))

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
validator = RequestValidator(TWILIO_AUTH_TOKEN)

SYSTEM_PROMPT = f"""You are an SMS intake assistant for {BUSINESS_NAME}, a {TRADE} business.
A customer's call was just missed. Your ONLY job is to find out, over a few short texts:
1. What the job/problem is
2. Their address or postcode
3. How urgent it is (emergency right now / today / this week)
4. The best time to call them back

Rules:
- Ask ONE short question at a time. This is SMS — keep every message under 300 characters.
- Be warm and plain-spoken, not corporate.
- Never quote a price or give a time estimate for arrival.
- If asked whether you're a real person, say you're {OWNER_NAME}'s assistant, texting on their behalf.
- Once you have all four things, thank them and say {OWNER_NAME} will call within the hour to
  confirm — then stop asking questions.
"""

# In-memory conversation store: {customer_phone_number: [{"role": ..., "content": ...}, ...]}
# NOTE: this resets on every restart/redeploy. Fine for a pilot/demo — swap for
# Redis or a small database table before relying on this day to day.
conversations: dict[str, list[dict]] = {}


def _valid_twilio_request() -> bool:
    signature = request.headers.get("X-Twilio-Signature", "")
    return validator.validate(request.url, request.form, signature)


def _ask_claude(history: list[dict]) -> str:
    result = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=SYSTEM_PROMPT,
        messages=history,
    )
    return "".join(block.text for block in result.content if block.type == "text").strip()


@app.route("/health", methods=["GET"])
def health():
    return "ok", 200


@app.route("/voice", methods=["POST"])
def voice_incoming():
    """A customer just called the Twilio number — try the owner's real mobile first."""
    if not _valid_twilio_request():
        return "Forbidden", 403

    response = VoiceResponse()
    dial = Dial(action="/voice/missed", timeout=RING_TIMEOUT)
    dial.number(OWNER_PHONE)
    response.append(dial)
    return str(response), 200, {"Content-Type": "text/xml"}


@app.route("/voice/missed", methods=["POST"])
def voice_missed():
    """Fires after the dial attempt completes — whatever the outcome was."""
    if not _valid_twilio_request():
        return "Forbidden", 403

    dial_status = request.form.get("DialCallStatus")  # completed / no-answer / busy / failed
    caller = request.form.get("From")
    response = VoiceResponse()

    if dial_status == "completed":
        # Owner picked up normally — nothing to do.
        return str(response), 200, {"Content-Type": "text/xml"}

    log.info(f"Missed call from {caller} (status={dial_status}) — sending intake text")
    intake_text = (
        f"Hi, sorry we missed your call \u2014 this is {OWNER_NAME}'s assistant at {BUSINESS_NAME}. "
        f"What's the job, and what's your postcode?"
    )
    twilio_client.messages.create(to=caller, from_=TWILIO_NUMBER, body=intake_text)
    conversations[caller] = [{"role": "assistant", "content": intake_text}]

    response.say("Sorry we missed that call. We've just sent you a text - reply there and we'll get it sorted.")
    return str(response), 200, {"Content-Type": "text/xml"}


@app.route("/sms", methods=["POST"])
def sms_incoming():
    """Every reply from the customer comes through here."""
    if not _valid_twilio_request():
        return "Forbidden", 403

    customer = request.form.get("From")
    body = (request.form.get("Body") or "").strip()

    history = conversations.setdefault(customer, [])
    history.append({"role": "user", "content": body})

    reply_text = _ask_claude(history)
    history.append({"role": "assistant", "content": reply_text})

    twiml = MessagingResponse()
    twiml.message(reply_text)

    # Keep the owner in the loop on their own phone at all times.
    twilio_client.messages.create(
        to=OWNER_PHONE,
        from_=TWILIO_NUMBER,
        body=f"[{customer}] {body}\n\u2192 AI replied: {reply_text}",
    )

    return str(twiml), 200, {"Content-Type": "text/xml"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
