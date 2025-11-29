import os
import tempfile
import subprocess
from flask import Flask, request, jsonify, render_template, session
from dotenv import load_dotenv
from openai import OpenAI

# ============================
# INIT
# ============================
load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=API_KEY)

app = Flask(__name__)

# Needed for usage tracking later
app.secret_key = "RB_SECRET_KEY_123456"


# ============================
# 🔥 FOUNDER & PREMIUM KEYS
# ============================
FOUNDER_KEY = "READYBRAIN-UCSD-A18565216"
PREMIUM_COOKIE = "rb_premium_mode"


def user_is_founder():
    return session.get("founder_mode") is True


def user_is_premium():
    return session.get("premium_mode") is True


# ============================
# ⭐ FIX: Founder can ALWAYS access admin
# ============================
@app.before_request
def allow_admin_for_founder():
    if request.endpoint == "admin_page":
        # When founder switches to user, this keeps admin unlocked ONLY for you
        if session.get("founder_override") is True:
            session["founder_mode"] = True


# ============================
# LANGUAGE MAP
# ============================
LANGUAGE_NAMES = {
    "en": "English",
    "my": "Burmese",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "es": "Spanish",
    "hi": "Hindi",
}


def lang_to_name(code):
    return LANGUAGE_NAMES.get(code, code)


# ============================
# ROUTES
# ============================
@app.route("/")
def landing():
    return render_template("index.html")


@app.route("/listen")
def listen_page():
    # Founder mode via URL
    founder_key = request.args.get("founderKey")
    if founder_key == FOUNDER_KEY:
        session["founder_mode"] = True
        session["founder_override"] = True
        print("🔥 Founder mode ENABLED")

    return render_template("listen.html")


@app.route("/premium")
def premium_page():
    return render_template("premium.html")


@app.route("/health")
def health():
    return "ok", 200


# ============================
# ⭐ PREMIUM ACTIVATION
# ============================
@app.route("/activate_premium", methods=["POST"])
def activate_premium():
    session["premium_mode"] = True
    print("🌟 Premium mode activated")
    return jsonify({"status": "ok"})


# ============================
# 🎤 MAIN INTERVIEW LISTENER
# ============================
@app.route("/interview_listen", methods=["POST"])
def interview_listen():
    print("\n===== 🎤 /interview_listen START =====")

    # Founder & premium bypass
    if user_is_founder():
        print("🔥 Founder detected → unlimited")
    elif user_is_premium():
        print("🌟 Premium user → unlimited")
    else:
        # Free limit
        uses = session.get("uses", 0)
        if uses >= 3:
            return jsonify({
                "error": "limit_reached",
                "redirect": "/premium"
            })
        session["uses"] = uses + 1

    # ============================
    # Recording logic (unchanged)
    # ============================

    input_lang = request.form.get("language", "auto")
    output_lang = request.form.get("output_language", "same")

    if "audio" not in request.files:
        return jsonify({
            "question": "(no audio)",
            "answer": "No audio detected.",
            "detected_language": None
        }), 400

    audio = request.files["audio"]
    filename = audio.filename or "input.webm"
    ext = filename.split(".")[-1] if "." in filename else "webm"

    input_path = None
    wav_path = None

    try:
        # Save audio
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as temp:
            audio.save(temp.name)
            input_path = temp.name

        # Convert to wav
        wav_path = input_path.replace(f".{ext}", ".wav")
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", input_path,
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                wav_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )

        # Transcribe
        def transcribe(language_hint=None):
            with open(wav_path, "rb") as f:
                return client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    response_format="verbose_json",
                    temperature=0,
                    language=language_hint
                )

        lang_hint = None if input_lang == "auto" else input_lang
        result = transcribe(lang_hint)

        spoken_text = (result.text or "").strip()
        detected_lang = getattr(result, "language", None) or input_lang or "unknown"

        # Retry Burmese
        if len(spoken_text) < 2 and input_lang == "my":
            result = transcribe("my")
            spoken_text = (result.text or "").strip()
            detected_lang = getattr(result, "language", None) or "my"

        clean_text = spoken_text.strip()

        # UNCLEAR detection
        if not clean_text or len(clean_text) < 4:
            return jsonify({
                "question": "(unclear)",
                "answer": "Unclear. Please try again.",
                "detected_language": detected_lang
            })

        # Noise detection
        segments = getattr(result, "segments", None)
        if segments:
            max_no_speech = max(
                seg.get("no_speech_prob", 0.0)
                if isinstance(seg, dict)
                else getattr(seg, "no_speech_prob", 0.0)
                for seg in segments
            )
            if max_no_speech > 0.8:
                return jsonify({
                    "question": "(unclear)",
                    "answer": "Unclear. Please try again.",
                    "detected_language": detected_lang
                })

        # Decide output language
        if output_lang == "same":
            if detected_lang != "unknown":
                final_lang = detected_lang
            else:
                final_lang = input_lang if input_lang != "auto" else "en"
        else:
            final_lang = output_lang

        final_lang_name = lang_to_name(final_lang)

        # Rewrite prompt
        rewrite_prompt = f"""
You are ReadyBrain AI.

Rewrite the following into a short, confident 2–3 sentence interview answer.
Write the FINAL version in {final_lang_name}.

Original text:
\"\"\"{spoken_text}\"\"\"

Rules:
- Keep original meaning
- No new ideas
- Simple and confident
- Output ONLY the final answer
"""

        ai = client.responses.create(
            model="gpt-4o-mini",
            input=rewrite_prompt
        )
        ai_output = ai.output_text.strip()

        return jsonify({
            "question": spoken_text,
            "answer": ai_output,
            "detected_language": detected_lang,
            "output_language": final_lang
        })

    finally:
        for p in (input_path, wav_path):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except:
                    pass


# ============================
# TEXT MODE
# ============================
@app.route("/interview_answer", methods=["POST"])
def interview_answer():
    data = request.get_json() or {}
    question = data.get("question", "").strip()
    job_role = data.get("job_role", "").strip()
    background = data.get("background", "").strip()

    if not question:
        return jsonify({"answer": "Please type a question."})

    prompt = f"""
You are ReadyBrain AI.

Write a short 2–3 sentence interview answer in clear, confident language.

Question: "{question}"
Job role: "{job_role}"
Background: "{background}"

Output ONLY the final answer.
"""

    try:
        result = client.responses.create(
            model="gpt-4o-mini",
            input=prompt
        )
        return jsonify({"answer": result.output_text.strip()})
    except:
        return jsonify({"answer": "Error generating answer."})


# ============================
# REGENERATE ANSWER
# ============================
@app.route("/interview_regen", methods=["POST"])
def interview_regen():
    data = request.get_json() or {}
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"answer": "(no text)"}), 400

    prompt = f"""
You are ReadyBrain AI.

Rewrite this in 2–3 confident, clean sentences.
Keep the same meaning.
Output ONLY the improved answer.

\"\"\"{text}\"\"\"
"""

    try:
        result = client.responses.create(
            model="gpt-4o-mini",
            input=prompt
        )
        return jsonify({"answer": result.output_text.strip()})
    except:
        return jsonify({"answer": "Error regenerating answer."})


# ============================
# 🔥 ADMIN / FOUNDER PANEL ROUTES
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


# ============================
# ⭐ NEW: SWITCH BETWEEN USER + FOUNDER
# ============================
@app.route("/admin_switch_to_user", methods=["POST"])
def admin_switch_to_user():
    # founder override stays TRUE so you never get locked out
    session.clear()
    session["founder_override"] = True  # lets you still open /admin
    print("🔁 Switched to USER MODE (limit active, but admin still open)")
    return "ok"


@app.route("/admin_switch_to_founder", methods=["POST"])
def admin_switch_to_founder():
    session.clear()
    session["founder_mode"] = True
    session["founder_override"] = True
    print("🔥 Switched to FOUNDER MODE (unlimited)")
    return "ok"


# ============================
# LOCAL DEV
# ============================
if __name__ == "__main__":
    app.run(debug=True)
