import os
import tempfile
import subprocess
import re
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from openai import OpenAI

# Load API Key
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=API_KEY)

app = Flask(__name__)

# ============================
# ROUTES
# ============================

@app.route("/")
def home():
    return render_template("listen.html")

@app.route("/listen")
def listen_page():
    return render_template("listen.html")


# ============================
# MAIN INTERVIEW LISTEN ROUTE
# ============================

@app.route("/interview_listen", methods=["POST"])
def interview_listen():
    if "audio" not in request.files:
        return jsonify({"question": "(no audio)", "answer": "Please try again."}), 400

    audio_file = request.files["audio"]

    # Save temp .webm file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_in:
        audio_file.save(temp_in.name)
        webm_path = temp_in.name

    # Convert .webm → .wav
    wav_path = webm_path.replace(".webm", ".wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", webm_path, wav_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
    except Exception as e:
        return jsonify({"question": "(error)", "answer": f"ffmpeg error: {e}"}), 500

    # ============================
    # TRUE SILENCE DETECTION
    # ============================
    silence_check = subprocess.run(
        ["ffmpeg", "-i", wav_path, "-af", "silencedetect=noise=-35dB:d=0.4", "-f", "null", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # If silence_start appears but silence_end does NOT → everything was silence
    if "silence_start" in silence_check.stderr and "silence_end" not in silence_check.stderr:
        return jsonify({
            "question": "(silence)",
            "answer": "I didn’t hear anything. Try speaking closer to the mic."
        })

    # ============================
    # TRANSCRIBE WITH WHISPER
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
        return jsonify({"question": "(error)", "answer": f"whisper error: {e}"}), 500

    lower_text = text.lower()

    # ============================
    # BLOCK STREAMER HALLUCINATIONS
    # ============================
    hallucinations = [
        "thanks for watching",
        "thank you for watching",
        "thanks everyone",
        "thank you so much",
        "subscribe",
        "video",
        "watching",
        "hello guys",
        "welcome back"
    ]

    if any(h in lower_text for h in hallucinations):
        return jsonify({
            "question": "(noise detected)",
            "answer": "I heard background noise but no clear speech. Try again."
        })

    # ============================
    # BLOCK TOO SHORT OR UNCLEAR SPEECH
    # ============================
    if len(text) < 5 or len(text.split()) <= 2:
        return jsonify({
            "question": "(unclear speech)",
            "answer": "I couldn’t catch that. Please speak a bit more clearly."
        })

    # ============================
    # GENERATE AI ANSWER
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

        return jsonify({"question": text, "answer": answer})

    except Exception as e:
        return jsonify({"question": text, "answer": f'AI error: {e}'}), 500


# ============================
# RUN LOCAL SERVER
# ============================

if __name__ == "__main__":
    app.run(debug=True)
