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

    input_lang = request.form.get("language", "auto")          # from dropdown
    output_lang = request.form.get("output_language", "same")  # from dropdown

    print("🌍 User selected input:", input_lang)
    print("🌐 User selected output:", output_lang)

    # -------------------------
    # CHECK AUDIO
    # -------------------------
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
        # -------------------------
        # SAVE TEMP INPUT FILE
        # -------------------------
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as temp:
            audio.save(temp.name)
            input_path = temp.name

        # -------------------------
        # CONVERT TO WAV 16kHz MONO
        # -------------------------
        wav_path = input_path.replace(f".{ext}", ".wav")

        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
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
            print("🎛 FFmpeg conversion OK")
        except Exception as e:
            print("❌ FFmpeg failed:", e)
            return jsonify({
                "question": "",
                "answer": "Audio conversion failed.",
                "detected_language": None
            }), 500

        # -------------------------
        # 🔊 TRANSCRIBE
        # -------------------------
        def transcribe(language_hint=None):
            with open(wav_path, "rb") as f:
                return client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    response_format="verbose_json",
                    temperature=0,
                    language=language_hint
                )

        try:
            lang_hint = None if input_lang == "auto" else input_lang
            print(f"🔊 Transcribing with whisper-1 (lang_hint={lang_hint})")

            result = transcribe(lang_hint)
            spoken_text = (result.text or "").strip()
            detected_lang = getattr(result, "language", None) or input_lang or "unknown"

            print("🗣 Speech:", spoken_text)
            print("🌐 Detected:", detected_lang)

            # If very short + Burmese hint requested
            if len(spoken_text) < 2 and input_lang == "my":
                print("⚠ Short transcript, retrying with Burmese hint...")
                result = transcribe("my")
                spoken_text = (result.text or "").strip()
                detected_lang = getattr(result, "language", None) or "my"
                print("🗣 Burmese retry speech:", spoken_text)
                print("🌐 Burmese retry detected:", detected_lang)

        except Exception as e:
            print("❌ Transcription error:", e)
            return jsonify({
                "question": "(error)",
                "answer": "Transcription failed.",
                "detected_language": None
            })

        # -------------------------
        # SIMPLE UNCLEAR AUDIO CHECK (FIXED)
        # -------------------------
        if not spoken_text or spoken_text.strip() == "" or len(spoken_text.strip()) < 4:
            return jsonify({
                "question": "(unclear)",
                "answer": "Unclear. Please try again.",
                "detected_language": detected_lang
            })

        # -------------------------
        # OUTPUT LANGUAGE DECISION
        # -------------------------
        if output_lang == "same":
            if detected_lang and detected_lang != "unknown":
                final_lang = detected_lang
            elif input_lang != "auto":
                final_lang = input_lang
            else:
                final_lang = "en"
        else:
            final_lang = output_lang

        final_lang_name = lang_to_name(final_lang)

        print("🎯 Final output language code:", final_lang)
        print("📝 Final output language name:", final_lang_name)

        # -------------------------
        # GENERATE ANSWER
        # -------------------------
        rewrite_prompt = f"""
You are ReadyBrain AI.

Rewrite the following into a short, confident 2–3 sentence interview answer.
Write the FINAL version in {final_lang_name}.

Original text:
\"\"\"{spoken_text}\"\"\"

Rules:
- Keep original meaning
- Simple and confident
- No new ideas
- Output ONLY the final answer
"""

        try:
            ai = client.responses.create(
                model="gpt-4o-mini",
                input=rewrite_prompt
            )
            ai_output = ai.output_text.strip()

        except Exception as e:
            print("❌ AI error:", e)
            return jsonify({
                "question": spoken_text,
                "answer": "There was an error generating the answer.",
                "detected_language": detected_lang
            })

        # -------------------------
        # RETURN JSON
        # -------------------------
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
                except Exception:
                    pass


# ============================
# TEXT MODE (TYPE ANSWER)
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
    except Exception:
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
    except Exception:
        return jsonify({"answer": "Error regenerating answer."})


# ============================
# LOCAL DEV
# ============================
if __name__ == "__main__":
    app.run(debug=True)
