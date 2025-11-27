import os
import tempfile
import subprocess
import re
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from openai import OpenAI

# ============================
# INIT
# ============================

load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=API_KEY)

app = Flask(__name__)

# ============================
# ROUTES
# ============================

@app.route("/")
def landing():
    return render_template("index.html")

@app.route("/listen")
def listen_page():
    return render_template("listen.html")

# ============================
# HEALTH CHECK (REQUIRED FOR RENDER)
# ============================

@app.route("/health")
def health():
    return "ok", 200


# ============================
# MAIN INTERVIEW LISTEN ROUTE
# ============================

@app.route("/interview_listen", methods=["POST"])
def interview_listen():
    print("\n===== 🎤 /interview_listen START =====")

    # 1. Language selection
    lang = request.form.get("language", "auto")
    print("🌍 User selected:", lang)

    # 2. Check audio file
    if "audio" not in request.files:
        return jsonify({"question": "(no audio)", "answer": "Try again."}), 400

    audio_file = request.files["audio"]
    filename = audio_file.filename.lower()

    # Extension detection
    file_ext = filename.split(".")[-1] if "." in filename else "webm"

    # Save input file
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as temp_in:
        audio_file.save(temp_in.name)
        input_path = temp_in.name

    # Convert → WAV
    wav_path = input_path.replace(f".{file_ext}", ".wav")

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, wav_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
    except Exception as e:
        return jsonify({"question": "(ffmpeg error)", "answer": str(e)}), 500

    # Silence detection
    silence_result = subprocess.run(
        ["ffmpeg", "-i", wav_path,
         "-af", "silencedetect=noise=-35dB:d=0.4",
         "-f", "null", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if "silence_start" in silence_result.stderr and "silence_end" not in silence_result.stderr:
        return jsonify({"question": "(silence)", "answer": "I didn't hear anything."})

    # ============================
    # WHISPER TRANSCRIPTION
    # ============================
    try:
        with open(wav_path, "rb") as f:
            whisper_data = client.audio.transcriptions.create(
                model="whisper-1",
                file=f
            )
        spoken_text = whisper_data.text.strip()
        print("📝 Whisper text:", spoken_text)

    except Exception as e:
        return jsonify({"question": "(whisper error)", "answer": str(e)}), 500

    # Noise filters
    check_lower = spoken_text.lower()

    banned = ["thanks for watching", "subscribe", "video", "welcome back", "hello guys"]
    if any(x in check_lower for x in banned):
        return jsonify({"question": "(noise)", "answer": "I heard noise instead of speech."})

    url_filters = [r"http", r"www\.", r"\.com", r"\.net", r"\.edu"]
    if any(re.search(p, check_lower) for p in url_filters):
        return jsonify({"question": "(noise)", "answer": "Background noise detected."})

    if len(spoken_text) < 5:
        return jsonify({"question": "(unclear)", "answer": "I couldn’t catch that."})

    # ============================
    # TRANSLATE SPEECH → ENGLISH
    # ============================
    print("🌍 Translating speech → English...")

    translate_prompt = f"""
The user said: "{spoken_text}"

Translate this into clear English.
Do not add new ideas.
Just the meaning.
"""

    try:
        english_version = client.responses.create(
            model="gpt-4o-mini",
            input=translate_prompt
        ).output_text.strip()

        print("🔤 English version:", english_version)

    except Exception as e:
        return jsonify({"question": spoken_text, "answer": f"translation error: {e}"}), 500

    # ============================
    # IMPROVE ENGLISH ANSWER
    # ============================
    improve_prompt = f"""
You are ReadyBrain AI.

Rewrite the user's answer into a short, confident, simple-English interview answer.

Rules:
- Only 2–3 short sentences.
- No long explanations.
- No filler.
- Clear and professional.

User: "{english_version}"

Output ONLY the improved answer.
"""

    try:
        improved = client.responses.create(
            model="gpt-4o-mini",
            input=improve_prompt
        ).output_text.strip()

        print("⚡ Improved English:", improved)

    except Exception as e:
        return jsonify({"question": spoken_text, "answer": f"improve error: {e}"}), 500

    # ============================
    # TRANSLATE → SELECTED LANGUAGE
    # ============================

    LANG_MAP = {
        "en": "English",
        "my": "Burmese",
        "ja": "Japanese",
        "es": "Spanish",
        "hi": "Hindi",
        "zh": "Chinese"
    }

    final_answer = improved

    if lang != "auto" and lang != "en":
        target = LANG_MAP.get(lang, "English")

        out_prompt = f"""
Translate the following interview answer into {target}.
Keep it simple and confident.

Text: "{improved}"
"""

        try:
            final_answer = client.responses.create(
                model="gpt-4o-mini",
                input=out_prompt
            ).output_text.strip()

        except Exception:
            print("⚠ Translation failed — using English.")

    return jsonify({
        "question": spoken_text,
        "answer": final_answer
    })


# ============================
# TEXT MODE
# ============================

@app.route("/interview_answer", methods=["POST"])
def interview_answer():
    data = request.get_json()

    question = data.get("question", "").strip()
    job_role = data.get("job_role", "")
    background = data.get("background", "")

    if not question:
        return jsonify({"answer": "Please type the question."})

    prompt = f"""
Interview question: "{question}"
Job role: "{job_role}"
User background: "{background}"

Write a short 2–3 sentence answer. Simple English. Confident.
"""

    try:
        resp = client.responses.create(
            model="gpt-4o-mini",
            input=prompt
        ).output_text.strip()

        return jsonify({"answer": resp})

    except Exception as e:
        return jsonify({"answer": f"error: {e}"})


# ============================
# REGENERATE ANSWER
# ============================

@app.route("/interview_regen", methods=["POST"])
def interview_regen():
    data = request.get_json()
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"answer": "(no text)"}), 400

    prompt = f"""
Rewrite this interview answer into 2–3 short, confident, simple-English sentences.

Text: "{text}"

Output only the improved answer.
"""

    try:
        resp = client.responses.create(
            model="gpt-4o-mini",
            input=prompt
        ).output_text.strip()

        return jsonify({"answer": resp})

    except Exception as e:
        return jsonify({"answer": f"regen error: {e}"})


# ============================
# LOCAL DEV
# ============================

if __name__ == "__main__":
    app.run(debug=True)
