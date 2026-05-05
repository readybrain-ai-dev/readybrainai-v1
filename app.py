import os
import tempfile
import subprocess
import stripe
import psycopg
from flask import Flask, request, jsonify, render_template, session, redirect, send_from_directory, url_for
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=API_KEY)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback-secret-change-this")

FOUNDER_KEY = os.getenv("FOUNDER_KEY", "READYBRAIN-UCSD-A18565216")

# ============================
# 💳 STRIPE CONFIG
# ============================
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

STRIPE_PRICES = {
    "monthly": "price_1TTHWVLCJYMjF6nvi9e50Mgs",
    "6months": "price_1TTHWRLCJYMjF6nvryqK3Ycw",
    "yearly":  "price_1TTHWULCJYMjF6nvUm6TlXwG",
}

# ============================
# 🗄️ DATABASE
# ============================
def get_db():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return None
    try:
        conn = psycopg.connect(db_url)
        return conn
    except Exception as e:
        print("❌ DB connection error:", str(e))
        return None

def init_db():
    conn = get_db()
    if not conn:
        return
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                stripe_customer_id TEXT,
                is_premium BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()
        conn.close()
        print("✅ Database initialized")
    except Exception as e:
        print("❌ DB init error:", str(e))

def set_user_premium(email, stripe_customer_id=None):
    conn = get_db()
    if not conn:
        return
    try:
        conn.execute("""
            INSERT INTO users (email, stripe_customer_id, is_premium)
            VALUES (%s, %s, TRUE)
            ON CONFLICT (email) DO UPDATE
            SET is_premium = TRUE, stripe_customer_id = COALESCE(%s, users.stripe_customer_id)
        """, (email, stripe_customer_id, stripe_customer_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print("❌ DB set premium error:", str(e))

def check_user_premium(email):
    conn = get_db()
    if not conn:
        return False
    try:
        row = conn.execute("SELECT is_premium FROM users WHERE email = %s", (email,)).fetchone()
        conn.close()
        return row and row[0]
    except Exception as e:
        print("❌ DB check premium error:", str(e))
        return False

# Initialize DB on startup
with app.app_context():
    init_db()

def user_is_founder():
    return session.get("founder_mode") is True

def user_is_premium():
    if session.get("premium_mode") is True:
        return True
    email = session.get("user_email")
    if email:
        return check_user_premium(email)
    return False

@app.before_request
def allow_admin_for_founder():
    if request.endpoint == "admin_page":
        if session.get("founder_override") is True:
            session["founder_mode"] = True

LANGUAGE_NAMES = {
    "my": "Burmese", "zh": "Chinese", "ja": "Japanese", "ko": "Korean",
    "th": "Thai", "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay",
    "tl": "Filipino", "hi": "Hindi", "bn": "Bengali", "es": "Spanish",
    "pt": "Portuguese", "en": "English",
}

def lang_to_name(code):
    return LANGUAGE_NAMES.get(code, "English")

@app.route("/")
def landing():
    return render_template("index.html")

@app.route("/listen")
def listen_page():
    founder_key = request.args.get("founderKey")
    if founder_key == FOUNDER_KEY:
        session["founder_mode"] = True
        session["founder_override"] = True
        print("🔥 Founder mode ENABLED")
    return render_template("listen.html")

@app.route("/premium")
def premium_page():
    pub_key = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    return render_template("premium.html", stripe_pub_key=pub_key)

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/tos")
def tos():
    return render_template("tos.html")

@app.route("/health")
def health():
    return "ok", 200

@app.route("/manifest.json")
def manifest():
    return send_from_directory(app.static_folder, "manifest.json")

@app.route("/sw.js")
def service_worker():
    return send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")

@app.route("/ads.txt")
def ads_txt():
    return send_from_directory(app.static_folder, "ads.txt")

@app.route("/activate_premium", methods=["POST"])
def activate_premium():
    session["premium_mode"] = True
    return jsonify({"status": "ok"})

@app.route("/restore-premium", methods=["POST"])
def restore_premium():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    if not email:
        return jsonify({"premium": False})
    is_premium = check_user_premium(email)
    if is_premium:
        session["premium_mode"] = True
        session["user_email"] = email
    return jsonify({"premium": is_premium})

# ============================
# 💳 STRIPE CHECKOUT
# ============================
@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    data = request.get_json() or {}
    plan = data.get("plan", "monthly")
    price_id = STRIPE_PRICES.get(plan, STRIPE_PRICES["monthly"])

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=url_for("payment_success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=url_for("premium_page", _external=True),
        )
        return jsonify({"url": checkout_session.url})
    except Exception as e:
        print("❌ Stripe error:", str(e))
        return jsonify({"error": str(e)}), 500

@app.route("/payment-success")
def payment_success():
    session_id = request.args.get("session_id")
    if session_id:
        try:
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            customer_email = checkout_session.customer_details.email
            customer_id = checkout_session.customer
            if customer_email:
                session["premium_mode"] = True
                session["user_email"] = customer_email
                set_user_premium(customer_email, customer_id)
                print(f"✅ Premium activated for {customer_email}")
        except Exception as e:
            print("❌ Stripe session error:", str(e))
            session["premium_mode"] = True
    return render_template("success.html")

@app.route("/payment-cancel")
def payment_cancel():
    return redirect("/premium")

# ============================
# 🔧 MANAGE SUBSCRIPTION
# ============================
@app.route("/manage-subscription", methods=["POST"])
def manage_subscription():
    data = request.get_json() or {}
    email = data.get("email") or session.get("user_email")
    if not email:
        return jsonify({"error": "No email"}), 400
    try:
        customers = stripe.Customer.list(email=email, limit=1)
        if not customers.data:
            return jsonify({"error": "No customer found"}), 404
        customer_id = customers.data[0].id
        portal = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url="https://readybrainai.com/premium"
        )
        return jsonify({"url": portal.url})
    except Exception as e:
        print("❌ Portal error:", str(e))
        return jsonify({"error": str(e)}), 500

# ============================
# 🔔 STRIPE WEBHOOK
# ============================
@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as e:
        print("❌ Webhook error:", str(e))
        return jsonify({"error": str(e)}), 400

    event_type = event["type"]
    print(f"📩 Webhook received: {event_type}")

    if event_type in ["customer.subscription.deleted", "customer.subscription.updated"]:
        subscription = event["data"]["object"]
        status = subscription.get("status")
        customer_id = subscription.get("customer")

        if status in ["canceled", "unpaid", "past_due"]:
            try:
                customer = stripe.Customer.retrieve(customer_id)
                email = customer.get("email")
                if email:
                    conn = get_db()
                    if conn:
                        conn.execute(
                            "UPDATE users SET is_premium = FALSE WHERE email = %s",
                            (email,)
                        )
                        conn.commit()
                        conn.close()
                        print(f"❌ Premium removed for {email}")
            except Exception as e:
                print("❌ Webhook DB error:", str(e))

    return jsonify({"status": "ok"})

# ============================
# ⚡ MAIN ANSWER ROUTE (instant - no Whisper)
# ============================
@app.route("/interview_regen", methods=["POST"])
def interview_regen():
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    translate_to_english = data.get("translate_to_english", False)
    language = data.get("language", "en")

    if not text:
        return jsonify({"answer": "(no text)"}), 400

    # Check usage limit
    if not user_is_founder() and not user_is_premium():
        uses = session.get("uses", 0)
        if uses >= 9999:
            return jsonify({"error": "limit_reached"})
        session["uses"] = uses + 1

    lang_name = lang_to_name(language)

    if translate_to_english:
        prompt = f"""You are ReadyBrain AI, an expert interview coach helping non-native English speakers ace their job interviews.

The user said the following during interview practice. This could be a question, brain teaser, scenario, or their own answer.

Your job: Write the BEST possible 2-3 sentence interview-style response in English.

If it's a question or brain teaser, give a smart, confident answer to it.
If it's already an answer, rewrite it to sound more professional and impressive.

Make it:
- Natural and fluent English
- Confident and clear
- Professional but not robotic
- Free of filler words

What the user said:
\"\"\"{text}\"\"\"

Output ONLY the final English response. Nothing else."""
    else:
        prompt = f"""You are ReadyBrain AI, an expert interview coach helping non-native English speakers ace their job interviews.

The user just spoke the following text during interview practice. This could be:
- Their answer to an interview question
- A brain teaser or problem they were asked
- A scenario or question they need to respond to
- Anything they said out loud

Your job: Write the BEST possible 2-3 sentence interview-style response, written in {lang_name}.

If it's a question or brain teaser, write a confident answer to it.
If it's already an answer, make it cleaner and more confident.
Always sound professional, thoughtful, and ready for a real interview.

CRITICAL: Write ONLY in {lang_name}. Do NOT include any translation notes, labels, explanations, or English text alongside the answer. Output ONLY the answer in {lang_name}.

What the user said:
\"\"\"{text}\"\"\"

Output ONLY the final response in {lang_name}. Nothing else."""

    try:
        result = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return jsonify({"answer": result.choices[0].message.content.strip()})
    except Exception as e:
        print("❌ interview_regen error:", str(e))
        return jsonify({"answer": "Error. Please try again."})

# ============================
# ADMIN ROUTES
# ============================
@app.route("/admin")
def admin_page():
    if not user_is_founder():
        return "Access denied", 403
    return render_template("admin.html")

@app.route("/admin_status")
def admin_status():
    return jsonify({
        "founder": user_is_founder(),
        "premium": user_is_premium(),
        "uses": session.get("uses", 0)
    })

@app.route("/admin_reset_uses", methods=["POST"])
def admin_reset_uses():
    if not user_is_founder():
        return "Access denied", 403
    session["uses"] = 0
    return "ok"

@app.route("/admin_enable_premium", methods=["POST"])
def admin_enable_premium():
    if not user_is_founder():
        return "Access denied", 403
    session["premium_mode"] = True
    return "ok"

@app.route("/admin_disable_premium", methods=["POST"])
def admin_disable_premium():
    if not user_is_founder():
        return "Access denied", 403
    session["premium_mode"] = False
    return "ok"

@app.route("/admin_clear_session", methods=["POST"])
def admin_clear_session():
    if not user_is_founder():
        return "Access denied", 403
    session.clear()
    session["founder_mode"] = True
    session["founder_override"] = True
    return "ok"

@app.route("/admin_switch_to_user", methods=["POST"])
def admin_switch_to_user():
    session.clear()
    session["founder_override"] = True
    return redirect("/listen")

@app.route("/admin_switch_to_founder", methods=["POST"])
def admin_switch_to_founder():
    session.clear()
    session["founder_mode"] = True
    session["founder_override"] = True
    return redirect("/admin")

if __name__ == "__main__":
    app.run(debug=True)