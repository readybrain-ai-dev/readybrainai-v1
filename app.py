import os
import tempfile
import subprocess
from flask import Flask, request, jsonify, render_template, session, redirect, send_from_directory
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=API_KEY)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback-secret-change-this")

FOUNDER_KEY = os.getenv("FOUNDER_KEY", "READYBRAIN-UCSD-A18565216")

def user_is_founder():
    return session.get("founder_mode") is True

def user_is_premium():
    return session.get("premium_mode") is True

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

WHISPER_SUPPORTED = {
    "zh", "ja", "ko", "th", "vi", "id", "ms", "hi", "bn", "es", "pt", "en", "tl"
}

def lang_to_name(code):
    return LANGUAGE_NAMES.get(code, code)

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
    return render_template("premium.html")

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/health")
def health():
    return "ok", 200

@app.route("/ads.txt")
def ads_txt():
    return send_from_directory(app.static_folder, "ads.txt")

@app.route("/activate_premium", methods=["POST"])
def activate_premium():
    session["premium_mode"] = True
    return jsonify({"status": "ok"})

# ============================
# 🎤 MAIN INTERVIEW LISTENER
# ============================
@app.route("/interview_listen", methods=["POST"])
def interview_listen():
    print("\n===== 🎤 /interview_listen START =====")

    if user_is_founder():
        print("🔥 Founder → unlimited")
    elif user_is_premium():
        print("🌟 Premium → unlimited")
    else:
        uses = session.get("uses", 0)
        if uses >= 9999:
            return jsonify({"error": "limit_reached", "redirect": "/premium"})
        session["uses"] = uses + 1

    input_lang = request.form.get("language", "auto")

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
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as temp:
            audio.save(temp.name)
            input_path = temp.name

        wav_path = input_path.replace(f".{ext}", ".wav")

        ffmpeg_result = subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        if ffmpeg_result.returncode != 0:
            print("❌ ffmpeg error:", ffmpeg_result.stderr.decode())
            return jsonify({
                "question": "(error)",
                "answer": "Audio processing failed. Please try again.",
                "detected_language": None
            }), 500

        def transcribe(language_hint=None):
            with open(wav_path, "rb") as f:
                return client.audio.transcriptions.create(
                    model="whisper-1", file=f,
                    response_format="verbose_json", temperature=0,
                    language=language_hint
                )

        if input_lang == "auto" or input_lang not in WHISPER_SUPPORTED:
            lang_hint = None
            print(f"ℹ️ Language '{input_lang}' → using auto-detect")
        else:
            lang_hint = input_lang

        result = transcribe(lang_hint)
        spoken_text = (result.text or "").strip()
        detected_lang = getattr(result, "language", None) or input_lang or "unknown"

        if not spoken_text or len(spoken_text) < 4:
            return jsonify({
                "question": "(unclear)",
                "answer": "Unclear. Please try again.",
                "detected_language": detected_lang
            })

        segments = getattr(result, "segments", None)
        if segments:
            max_no_speech = max(
                seg.get("no_speech_prob", 0.0) if isinstance(seg, dict) else getattr(seg, "no_speech_prob", 0.0)
                for seg in segments
            )
            if max_no_speech > 0.8:
                return jsonify({
                    "question": "(unclear)",
                    "answer": "Unclear. Please try again.",
                    "detected_language": detected_lang
                })

        if input_lang == "my":
            final_lang = "my"
        elif input_lang != "auto" and input_lang in LANGUAGE_NAMES:
            final_lang = input_lang
        else:
            final_lang = detected_lang if detected_lang != "unknown" else "en"

        final_lang_name = lang_to_name(final_lang)

        rewrite_prompt = f"""You are ReadyBrain AI, an expert interview coach helping non-native English speakers ace their job interviews.

The user just spoke the following text during interview practice. This could be:
- Their answer to an interview question
- A brain teaser or problem they were asked
- A scenario or question they need to respond to
- Anything they said out loud

Your job: Write the BEST possible 2-3 sentence interview-style response to whatever they said, written in {final_lang_name}.

If it's a question or brain teaser, write a confident answer to it.
If it's already an answer, make it cleaner and more confident.
Always sound professional, thoughtful, and ready for a real interview.

What the user said:
\"\"\"{spoken_text}\"\"\"

Output ONLY the final response in {final_lang_name}. Nothing else."""

        ai = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": rewrite_prompt}]
        )
        ai_output = ai.choices[0].message.content.strip()

        return jsonify({
            "question": spoken_text,
            "answer": ai_output,
            "detected_language": detected_lang,
            "output_language": final_lang
        })

    except Exception as e:
        print("❌ interview_listen error:", str(e))
        return jsonify({
            "question": "(error)",
            "answer": "Something went wrong. Please try again.",
            "detected_language": None
        }), 500

    finally:
        for p in (input_path, wav_path):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except:
                    pass

# ============================
# REGENERATE / CONVERT TO ENGLISH
# ============================
@app.route("/interview_regen", methods=["POST"])
def interview_regen():
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    translate_to_english = data.get("translate_to_english", False)

    if not text:
        return jsonify({"answer": "(no text)"}), 400

    if translate_to_english:
        prompt = f"""You are ReadyBrain AI, an expert interview coach helping non-native English speakers ace their job interviews.

The user said the following during interview practice. This could be a question, brain teaser, scenario, or their own answer.

Your job: Write the BEST possible 2-3 sentence interview-style response in English.

If it's a question or brain teaser, give a smart, confident answer to it.
If it's already an answer, rewrite it to sound more professional and impressive.

The response will be spoken out loud to a real interviewer, so make it:
- Natural and fluent English
- Confident and clear
- Professional but not robotic
- Free of filler words

What the user said:
\"\"\"{text}\"\"\"

Output ONLY the final English response. Nothing else."""
    else:
        prompt = f"""You are ReadyBrain AI, an expert interview coach.
Rewrite the following into a better 2-3 sentence interview answer.
Make it clearer, more confident, and more professional.
Output ONLY the improved answer.

\"\"\"{text}\"\"\""""

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