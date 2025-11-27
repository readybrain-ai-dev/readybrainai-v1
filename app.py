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
    ext = filename.split(".")[-1]

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
        # CONVERT TO WAV 16kHz
        # -------------------------
        wav_path = input_path.replace(f".{ext}", ".wav")

        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", input_path,
                 "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                 wav_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
            print("🎛 FFmpeg conversion OK")
        except Exception as e:
            print("❌ FFmpeg failed:", e)
            return jsonify({"question": "", "answer": "Audio conversion failed."}), 500

        # -------------------------
        # 🎧 TRANSCRIBE (auto-detect language)
        # -------------------------
        try:
            print("🔊 Transcribing with: whisper-1")

            with open(wav_path, "rb") as f:
                result = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    response_format="verbose_json"
                )

            spoken_text = result.text.strip()
            detected_lang = result.language

            print("🗣 Speech:", spoken_text)
            print("🌐 Detected:", detected_lang)

        except Exception as e:
            print("❌ Transcription error:", e)
            return jsonify({
                "question": "(error)",
                "answer": "Transcription failed.",
                "detected_language": None
            })

        # -------------------------
        # CHECK IF CLEAR SPEECH
        # -------------------------
        if len(spoken_text) < 2:
            return jsonify({
                "question": "(unclear)",
                "answer": "I couldn't hear anything clearly.",
                "detected_language": detected_lang
            })

        # -------------------------
        # OUTPUT LANGUAGE DECISION
        # -------------------------
        if output_lang == "same":
            final_lang = detected_lang
        else:
            final_lang = output_lang

        final_lang_name = lang_to_name(final_lang)

        print("🎯 Final output language:", final_lang_name)

        # -------------------------
        # GENERATE ANSWER
        # -------------------------
        rewrite_prompt = f"""
Rewrite the following into a short, confident 2–3 sentence interview answer.
Write the FINAL version in {final_lang_name}.

Text:
\"\"\"{spoken_text}\"\"\"

Rules:
- Keep original meaning
- Simple and confident
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
                except:
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
Write a short 2–3 sentence interview answer in clear, confident language.

Question: "{question}"
Job role: "{job_role}"
Background: "{background}"

Output ONLY the answer.
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
Rewrite this in 2–3 confident, clean sentences:

\"\"\"{text}\"\"\"

Output ONLY the improved answer.
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
