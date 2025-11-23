import os
import tempfile
import subprocess
import re
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from openai import OpenAI

# Load API key
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=API_KEY)
app = Flask(__name__)

@app.route("/")
def home():
    return render_template("listen.html")

@app.route("/listen")
def listen_page():
    return render_template("listen.html")

@app.route("/interview_listen", methods=["POST"])
def interview_listen():
    # ============================
    # Check audio file exists
    # ============================
    if "audio" not in request.files:
        return jsonify({"error": "no_audio"}), 400

    audio_file = request.files["audio"]

    # ============================
    # Save .webm file
    # ============================
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_in:
        audio_file.save(temp_in.name)
        webm_path = temp_in.name

    # ============================
    # Convert .webm → .wav
    # ============================
    wav_path = webm_path.replace(".webm", ".wav")

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", webm_path, wav_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
    except Exception as e:
        return jsonify({"error": f"ffmpeg_error: {e}"}), 500

    # ============================
    # Whisper transcription
    # ============================
    try:
        with open(wav_path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="en"
            )
        text = transcript.text.strip()
    except Exception as e:
        return jsonify({"error": f"whisper_error: {e}"}), 500

    # Convert to lowercase for pattern checks
    lower_text = text.lower()

    # ============================
    # Silence / hallucination filter
    # ============================
    hallucination_starters = [
        r"^thanks",
        r"^okay",
        r"^ok",
        r"^well",
        r"^hello",
        r"^hi",
        r"^so",
        r"^um",
        r"^hmm",
        r"^hey",
        r"^thank"
    ]

    for pattern in hallucination_starters:
        if re.match(pattern, lower_text):
            return jsonify({
                "question": "(no real speech detected)",
                "answer": "I didn’t hear anything clearly. Please try speaking again."
            })

    # ============================
    # Noise filters
    # ============================

    # Too short → noise
    if len(text) < 5:
        return jsonify({
            "question": "(no speech detected)",
            "answer": "I couldn’t hear you. Try again."
        })

    # Remove Korean / Japanese hallucination
    if re.search(r'[ㄱ-ㅎㅏ-ㅣ가-힣]', text) or re.search(r'[\u3040-\u30ff]', text):
        return jsonify({
            "question": "(background noise)",
            "answer": "There was background noise — try speaking again."
        })

    # URL hallucination
    if "www." in lower_text or "http" in lower_text:
        return jsonify({
            "question": "(background noise)",
            "answer": "Noise detected — try again."
        })

    # Very low word count
    if len(text.split()) <= 2:
        return jsonify({
            "question": "(not enough speech)",
            "answer": "Please speak a full sentence for me to understand."
        })

    # ============================
    # AI Answer
    # ============================
    prompt = (
        f"The speaker said: '{text}'.\n"
        f"Give a simple, friendly 1–2 sentence response."
    )

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=prompt
        )
        answer = response.output_text.strip()

        return jsonify({
            "question": text,
            "answer": answer
        })

    except Exception as e:
        return jsonify({"error": f"gpt_error: {e}"}), 500


if __name__ == "__main__":
    app.run(debug=True)
