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
            "answer": "No audio detected.",
            "detected_language": None
        }), 400

    audio = request.files["audio"]
    filename = audio.filename or "speech.webm"
    ext = filename.split(".")[-1] if "." in filename else "webm"

    input_path = None
    wav_path = None

    try:
        # -------------------------
        # SAVE TEMP FILE
        # -------------------------
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as temp:
            audio.save(temp.name)
            input_path = temp.name

        # -------------------------
        # CONVERT → WAV (16kHz mono)
        # -------------------------
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
                "question": "(ffmpeg)",
                "answer": "Audio conversion failed.",
                "detected_language": None
            }), 500

        # -------------------------
        # 🎧 TRANSCRIBE USING GPT-4o-TRANSCRIBE
        # -------------------------
        def transcribe_with(lang_hint=None):
            print(f"🔊 Transcribing (hint={lang_hint})")
            with open(wav_path, "rb") as f:
                return client.audio.transcriptions.create(
                    model="gpt-4o-transcribe",
                    language=None if lang_hint == "auto" else lang_hint,
                    file=f,
                    temperature=0,
                    response_format="json"
                )

        # First attempt (auto or user-selected language)
        try:
            lang_hint = None if input_lang == "auto" else input_lang
            whisper = transcribe_with(lang_hint)

            spoken_text = whisper.text.strip()
            detected_lang = whisper.language or input_lang or "unknown"

            print("🗣 Transcript:", spoken_text)
            print("🌐 Detected:", detected_lang)

        except Exception as e:
            print("❌ Initial transcription failed:", e)
            spoken_text = ""
            detected_lang = None

        # If Burmese is selected or auto-detect failed → retry Burmese
        if len(spoken_text) < 2:
            print("⚠ Retrying Burmese mode...")
            try:
                whisper = transcribe_with("my")
                spoken_text = whisper.text.strip()
                detected_lang = whisper.language or "my"
                print("🗣 Burmese retry:", spoken_text)
            except:
                return jsonify({
                    "question": "(error)",
                    "answer": "Transcription failed.",
                    "detected_language": None
                })

        # -------------------------
        # No speech detected
        # -------------------------
        if len(spoken_text) < 2:
            return jsonify({
                "question": "(unclear)",
                "answer": "I couldn't hear anything clearly.",
                "detected_language": detected_lang
            })

        # -------------------------
        # DECIDE OUTPUT LANGUAGE
        # -------------------------
        if output_lang == "same":
            final_lang = detected_lang or input_lang or "en"
        else:
            final_lang = output_lang

        final_lang_name = lang_to_name(final_lang)

        print("🎯 Final output language:", final_lang)

        # -------------------------
        # GENERATE IMPROVED ANSWER
        # -------------------------
        rewrite_prompt = f"""
You are ReadyBrain AI.

Rewrite this into a short, confident 2–3 sentence interview answer.
Write the final answer in {final_lang_name}.

Original:
\"\"\"{spoken_text}\"\"\" 

Rules:
- keep meaning
- simple and confident
- no new ideas
- output ONLY the final answer
"""

        try:
            ai = client.responses.create(
                model="gpt-4o-mini",
                input=rewrite_prompt
            )
            final_answer = ai.output_text.strip()
        except Exception as e:
            print("❌ AI error:", e)
            return jsonify({
                "question": spoken_text,
                "answer": "There was an error generating the answer.",
                "detected_language": detected_lang
            })

        # -------------------------
        # RETURN SUCCESS
        # -------------------------
        return jsonify({
            "question": spoken_text,
            "answer": final_answer,
            "detected_language": detected_lang,
            "output_language": final_lang
        })

    finally:
        # Clean up temp files
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
    job = data.get("job_role", "").strip()
    bg = data.get("background", "").strip()

    if not question:
        return jsonify({"answer": "Please type a question."})

    prompt = f"""
You are ReadyBrain AI.
Write a confident 2–3 sentence answer.

Question: "{question}"
Job role: "{job}"
Background: "{bg}"

Output only the final answer.
"""

    try:
        ai = client.responses.create(
            model="gpt-4o-mini",
            input=prompt
        )
        return jsonify({"answer": ai.output_text.strip()})
    except:
        return jsonify({"answer": "Error generating answer."})


# ============================
# REGENERATE
# ============================
@app.route("/interview_regen", methods=["POST"])
def interview_regen():
    text = (request.get_json() or {}).get("text", "").strip()

    if not text:
        return jsonify({"answer": "(no text)"}), 400

    prompt = f"""
Rewrite into 2–3 simple, confident sentences.
\"\"\"{text}\"\"\"
Output only the improved answer.
"""

    try:
        ai = client.responses.create(
            model="gpt-4o-mini",
            input=prompt
        )
        return jsonify({"answer": ai.output_text.strip()})
    except:
        return jsonify({"answer": "Error regenerating answer."})


# ============================
# LOCAL DEV
# ============================
if __name__ == "__main__":
    app.run(debug=True)
