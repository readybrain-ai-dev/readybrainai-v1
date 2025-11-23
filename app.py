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
        ["ffmpeg", "-i", wav_path,
         "-af", "silencedetect=noise=-35dB:d=0.4",
         "-f", "null", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if "silence_start" in silence_check.stderr and "silence_end" not in silence_check.stderr:
        return jsonify({
            "question": "(silence)",
            "answer": "I didn’t hear anything — try speaking closer to the mic."
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
    # BLOCK STREAMER / VIDEO HALLUCINATIONS
    # ============================
    streamer_phrases = [
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

    if any(h in lower_text for h in streamer_phrases):
        return jsonify({
            "question": "(noise detected)",
            "answer": "I heard background noise but no clear speech. Try again."
        })

    # ============================
    # BLOCK URL / WEBSITE HALLUCINATIONS
    # ============================
    url_patterns = [
        r"www\.", r"http", r"https",
        r"\.com", r"\.org", r"\.gov", r"\.net", r"\.edu",
        r"for more information", r"visit"
    ]

    if any(re.search(p, lower_text) for p in url_patterns):
        return jsonify({
            "question": "(background noise)",
            "answer": "I heard noise but not real speech — try again!"
        })

    # ============================
    # BLOCK TOO SHORT OR UNCLEAR SPEECH
    # ============================
    if len(text) < 5 or len(text.split()) <= 2:
        return jsonify({
            "question": "(unclear speech)",
            "answer": "I couldn’t catch that — try speaking more clearly."
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


# ======================================================
# NEW: INTERVIEW ANSWER ROUTE (FOR TEXT ANSWER WEBPAGE)
# ======================================================

@app.route("/interview_answer", methods=["POST"])
def interview_answer():
    data = request.get_json()

    question = data.get("question", "").strip()
    job_role = data.get("job_role", "").strip()
    background = data.get("background", "").strip()

    if not question:
        return jsonify({"answer": "Please enter the question first."})

    prompt = f"""
The interview question is: "{question}"

Job role: "{job_role}"
User background: "{background}"

Write a simple, friendly, 2–3 sentence answer that sounds human,
easy to understand, and not too professional.
"""

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=prompt
        )
        answer = response.output_text.strip()

        return jsonify({"answer": answer})

    except Exception as e:
        return jsonify({"answer": f"AI error: {e}"})


# ============================
# RUN LOCAL SERVER
# ============================

if __name__ == "__main__":
    app.run(debug=True)
