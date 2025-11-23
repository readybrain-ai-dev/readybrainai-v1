import os
import tempfile
import subprocess
import re
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from openai import OpenAI

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
    if "audio" not in request.files:
        return jsonify({"error": "no_audio"}), 400

    audio_file = request.files["audio"]

    # Save file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_in:
        audio_file.save(temp_in.name)
        webm_path = temp_in.name

    # Convert to WAV
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

    # Transcribe: ENGLISH ONLY
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

    # ===== NOISE FILTERS =====

    # 1. Too short → noise
    if len(text) < 5:
        return jsonify({
            "question": "(no speech detected)",
            "answer": "I couldn't hear you clearly. Try again."
        })

    # 2. Remove Korean/Japanese hallucinations
    if re.search(r'[ㄱ-ㅎㅏ-ㅣ가-힣]', text) or re.search(r'[\u3040-\u30ff]', text):
        return jsonify({
            "question": "(background noise)",
            "answer": "There was too much noise. Try again."
        })

    # 3. URL hallucinations fix
    if "www." in text.lower() or "http" in text.lower():
        return jsonify({
            "question": "(background noise)",
            "answer": "Too much noise — try speaking again."
        })

    # 4. Low word count → noise
    if len(text.split()) <= 2:
        return jsonify({
            "question": "(background noise)",
            "answer": "I couldn't hear clear speech. Try again."
        })

    # ===== AI ANSWER =====

    prompt = (
        f"The speaker said: '{text}'.\n"
        f"Give a simple, helpful 1–2 sentence response."
    )

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=prompt
        )
        answer = response.output_text.strip()
        return jsonify({"question": text, "answer": answer})

    except Exception as e:
        return jsonify({"error": f"gpt_error: {e}"}), 500


if __name__ == "__main__":
    app.run(debug=True)
