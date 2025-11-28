import os
import tempfile
import subprocess
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
# LANGUAGE MAP (clean, no Burmese)
# ============================
LANGUAGE_NAMES = {
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "es": "Spanish"
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
    return render_template("listen.html")

@app.route("/health")
def health():
    return "ok", 200


# ============================
# 🎤 MAIN INTERVIEW LISTENER
# ============================
@app.route("/interview_listen", methods=["POST"])
def interview_listen():
    print("\n===== 🎤 /interview_listen START =====")

    input_lang = request.form.get("language", "auto")
    output_lang = request.form.get("output_language", "same")

    print("🌍 Input language:", input_lang)
    print("🌐 Output language:", output_lang)

    # -------------------------
    # CHECK AUDIO
    # -------------------------
    if "audio" not in request.files:
        return jsonify({
            "question": "(no audio)",
            "answer": "No audio received.",
            "detected_language": None
        }), 400

    audio = request.files["audio"]
    filename = audio.filename or "speech.webm"
    ext = filename.split(".")[-1] if "." in filename else "webm"

    input_path = None
    wav_path = None

    try:
        # SAVE TEMP FILE
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as temp:
            audio.save(temp.name)
            input_path = temp.name

        # CONVERT TO WAV 16kHz MONO
        wav_path = input_path.replace(f".{ext}", ".wav")

        try:
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
            print("🎛 FFmpeg OK")
        except Exception as e:
            print("❌ FFmpeg error:", e)
            return jsonify({
                "question": "",
                "answer": "Audio conversion failed.",
                "detected_language": None
            }), 500

        # -------------------------
        # 🔊 TRANSCRIBE
        # -------------------------
        def transcribe_hint(lang):
            with open(wav_path, "rb") as f:
                return client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    response_format="verbose_json",
                    temperature=0,
                    language=lang
                )

        lang_hint = None if input_lang == "auto" else input_lang

        print(f"🔊 Transcribing (hint={lang_hint})")

        try:
            result = transcribe_hint(lang_hint)
            spoken_text = (result.text or "").strip()
            detected_lang = getattr(result, "language", None) or "unknown"
        except Exception as e:
            print("❌ Whisper error:", e)
            return jsonify({
                "question": "(error)",
                "answer": "Transcription failed.",
                "detected_language": None
            })

        print("🗣 Text:", spoken_text)
        print("🌐 Detected lang:", detected_lang)

        if len(spoken_text) < 2:
            return jsonify({
                "question": "(unclear speech)",
                "answer": "I couldn't hear anything clearly.",
                "detected_language": detected_lang
            })

        # -------------------------
        # FINAL OUTPUT LANGUAGE
        # -------------------------
        if output_lang == "same":
            if detected_lang in LANGUAGE_NAMES:
                final_lang = detected_lang
            else:
                final_lang = "en"
        else:
            final_lang = output_lang

        final_lang_name = lang_to_name(final_lang)

        print("🎯 Final output:", final_lang)

        # -------------------------
        # AI REWRITE
        # -------------------------
        rewrite_prompt = f"""
You are ReadyBrain AI.

Rewrite the following interview answer into a short, confident 2–3 sentence response.
Write the final version in {final_lang_name}.
Keep the meaning. Keep it simple. Do not add new details.

Original:
\"\"\"{spoken_text}\"\"\"

Output ONLY the improved answer.
"""

        try:
            ai = client.responses.create(
                model="gpt-4o-mini",
                input=rewrite_prompt
            )
            ai_output = ai.output_text.strip()
        except Exception as e:
            print("❌ AI rewrite error:", e)
            return jsonify({
                "question": spoken_text,
                "answer": "There was an error generating the answer.",
                "detected_language": detected_lang
            })

        return jsonify({
            "question": spoken_text,
            "answer": ai_output,
            "detected_language": detected_lang,
            "output_language": final_lang
        })

    finally:
        # CLEAN TEMP
        for p in (input_path, wav_path):
            if p and os.path.exists(p):
                try: os.remove(p)
                except: pass


# ============================
# TEXT MODE ANSWER
# ============================
@app.route("/interview_answer", methods=["POST"])
def interview_answer():
    data = request.get_json() or {}
    question = data.get("question", "").strip()
    role = data.get("job_role", "").strip()
    bg = data.get("background", "").strip()

    if not question:
        return jsonify({"answer": "Please enter a question."})

    prompt = f"""
You are ReadyBrain AI.

Write a short 2–3 sentence interview answer in clear, confident language.
Only output the improved answer.

Question: "{question}"
Role: "{role}"
Background: "{bg}"
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
Rewrite this into a clean, confident 2–3 sentence interview answer.
Do not add new information.
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
# LOCAL DEV
# ============================
if __name__ == "__main__":
    app.run(debug=True)
