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

# Simple language map for nicer control
LANG_MAP = {
    "en": "English",
    "my": "Burmese",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "es": "Spanish",
    "hi": "Hindi",
}


def lang_name_from_code(code: str) -> str:
    """Map language code to human-readable name, with a safe fallback."""
    if not code:
        return "the same language as this text"
    return LANG_MAP.get(code, "the same language as this text")


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
# MAIN INTERVIEW LISTEN (GLOBAL)
# ============================
@app.route("/interview_listen", methods=["POST"])
def interview_listen():
    print("\n===== 🎤 /interview_listen START =====")

    input_lang = request.form.get("language", "auto")          # from dropdown
    output_lang_choice = request.form.get("output_language", "same")  # "same" or lang code

    print("🌍 Input language selected:", input_lang)
    print("🌐 Output language selected:", output_lang_choice)

    # -------------------------
    # 1. CHECK AUDIO
    # -------------------------
    if "audio" not in request.files:
        return jsonify({
            "question": "(no audio)",
            "answer": "No audio detected.",
            "detected_language": None
        }), 400

    audio_file = request.files["audio"]
    filename = (audio_file.filename or "").lower()
    ext = filename.split(".")[-1] if "." in filename else "webm"

    input_path = None
    wav_path = None

    try:
        # Save input to temp
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as temp_file:
            audio_file.save(temp_file.name)
            input_path = temp_file.name

        # -------------------------
        # 2. CONVERT TO WAV (16k mono)
        # -------------------------
        wav_path = input_path.replace(f".{ext}", ".wav")

        try:
            ffmpeg_proc = subprocess.run(
                ["ffmpeg", "-y", "-i", input_path, "-ar", "16000", "-ac", "1", wav_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
            print("🎛 FFmpeg conversion OK")
        except Exception as e:
            print("❌ FFmpeg error:", e)
            return jsonify({"question": "(ffmpeg error)", "answer": "Audio conversion failed."}), 500

        # -------------------------
        # 3. TRANSCRIBE WITH GPT-4O-TRANSCRIBE
        # -------------------------
        try:
            print("🔊 Transcribing with gpt-4o-transcribe...")

            with open(wav_path, "rb") as f:
                whisper_result = client.audio.transcriptions.create(
                    model="gpt-4o-transcribe",
                    file=f,
                    # If user chose auto, let model detect; otherwise force language
                    language=None if input_lang == "auto" else input_lang
                )

            spoken_text = (whisper_result.text or "").strip()
            detected_lang = getattr(whisper_result, "language", None) or "unknown"

            print("🗣️ Transcript:", spoken_text)
            print("🌐 Detected Language:", detected_lang)

        except Exception as e:
            print("❌ Transcription error:", e)
            return jsonify({"question": "(whisper error)", "answer": "Transcription failed."}), 500

        # Empty / unclear speech
        if len(spoken_text) < 3:
            return jsonify({
                "question": "(unclear)",
                "answer": "I couldn't hear anything clearly.",
                "detected_language": detected_lang
            })

        # -------------------------
        # 4. DETERMINE OUTPUT LANGUAGE CODE
        # -------------------------
        # Source language code from model (preferred), else input setting
        source_lang_code = detected_lang if detected_lang != "unknown" else (
            input_lang if input_lang != "auto" else "en"
        )

        if output_lang_choice == "same":
            final_lang_code = source_lang_code
        else:
            final_lang_code = output_lang_choice

        final_lang_name = lang_name_from_code(final_lang_code)

        print("🎯 Final answer language code:", final_lang_code)
        print("📝 Final answer language name:", final_lang_name)

        # -------------------------
        # 5. REWRITE INTO SHORT, CONFIDENT ANSWER
        # -------------------------
        rewrite_prompt = f"""
You are ReadyBrain AI.

The user just spoke their interview answer.

Your job:
1. Understand the meaning.
2. Rewrite it into a short, confident answer (2–3 short sentences).
3. Write the final answer in {final_lang_name}.

Original text:
\"\"\"{spoken_text}\"\"\"

Rules:
- Keep the original meaning.
- Make it clear and confident.
- Simple language.
- Do NOT add new ideas.
- Do NOT give explanations, only the final answer.
"""

        try:
            ai_output = client.responses.create(
                model="gpt-4o-mini",
                input=rewrite_prompt
            )
            improved_text = ai_output.output_text.strip()
            print("✨ Final Answer:", improved_text)

        except Exception as e:
            print("❌ AI rewrite error:", e)
            return jsonify({
                "question": spoken_text,
                "answer": "There was an error generating the answer.",
                "detected_language": detected_lang
            }), 500

        # -------------------------
        # 6. RETURN JSON RESPONSE
        # -------------------------
        return jsonify({
            "question": spoken_text,
            "answer": improved_text,
            "detected_language": detected_lang,
            "output_language": final_lang_code
        })

    finally:
        # Clean up temp files
        for path in (input_path, wav_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
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
        return jsonify({"answer": "Please type the question."})

    prompt = f"""
You are ReadyBrain AI.

Write a short interview answer (2–3 sentences) for:

Question: "{question}"
Job role: "{job_role}"
User background: "{background}"

Rules:
- Simple.
- Confident.
- Clear.
- No long explanations.
Just output the final answer.
"""

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=prompt
        )
        return jsonify({"answer": response.output_text.strip()})
    except Exception as e:
        print("❌ Text mode error:", e)
        return jsonify({"answer": "There was an error generating the answer."})


# ============================
# REGENERATE ANSWER
# ============================
@app.route("/interview_regen", methods=["POST"])
def interview_regen():
    data = request.get_json() or {}
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"answer": "(no text)"}), 400

    regen_prompt = f"""
You are ReadyBrain AI.

Rewrite this answer into 2–3 confident, simple sentences.
Keep the same meaning.

Text:
\"\"\"{text}\"\"\"

Output only the improved answer.
"""

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=regen_prompt
        )
        return jsonify({"answer": response.output_text.strip()})
    except Exception as e:
        print("❌ Regen error:", e)
        return jsonify({"answer": "There was an error regenerating the answer."})


# ============================
# LOCAL DEV
# ============================
if __name__ == "__main__":
    app.run(debug=True)
