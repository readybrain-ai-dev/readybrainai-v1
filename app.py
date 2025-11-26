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
# MAIN INTERVIEW LISTEN ROUTE
# ============================

@app.route("/interview_listen", methods=["POST"])
def interview_listen():
    print("==== /interview_listen START ====")

    # 1. Check audio
    if "audio" not in request.files:
        print("❌ No audio file found")
        return jsonify({"question": "(no audio)", "answer": "Please try again."}), 400

    audio_file = request.files["audio"]
    print("📌 Received audio:", audio_file.filename)

    # ⭐ FIX: detect correct extension (ogg, webm, mp4, wav, etc.)
    file_ext = audio_file.filename.split(".")[-1].lower()

    # ⭐ Save with correct extension
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as temp_in:
        audio_file.save(temp_in.name)
        input_path = temp_in.name

    print("📌 Saved input file:", input_path)

    # ⭐ Convert ANY format → WAV
    wav_path = input_path.replace(f".{file_ext}", ".wav")
    print("📌 Converting to WAV:", wav_path)

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, wav_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
    except Exception as e:
        print("❌ FFmpeg error:", e)
        return jsonify({"question": "(error)", "answer": f"ffmpeg error: {e}"}), 500

    # 4. Silence detection
    silence_check = subprocess.run(
        ["ffmpeg", "-i", wav_path,
         "-af", "silencedetect=noise=-35dB:d=0.4",
         "-f", "null", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    print("📌 Silence detection log:")
    print(silence_check.stderr)

    if "silence_start" in silence_check.stderr and "silence_end" not in silence_check.stderr:
        print("❌ Entire audio was silence")
        return jsonify({
            "question": "(silence)",
            "answer": "I didn’t hear anything — try again."
        })

    # 5. Whisper Transcription
    print("📌 Transcribing with Whisper...")

    try:
        with open(wav_path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="en"
            )
        text = transcript.text.strip()
        print("📌 Whisper text:", text)
    except Exception as e:
        print("❌ Whisper error:", e)
        return jsonify({"question": "(error)", "answer": f"whisper error: {e}"}), 500

    lower_text = text.lower()

    # 6. Noise / streamer hallucination filters
    streamer_phrases = [
        "thanks for watching", "thank you for watching", "thanks everyone",
        "thank you so much", "subscribe", "video", "watching",
        "hello guys", "welcome back"
    ]

    if any(h in lower_text for h in streamer_phrases):
        print("❌ Blocked streamer hallucination")
        return jsonify({
            "question": "(noise)",
            "answer": "I heard noise but no real speech."
        })

    # 7. URL hallucinations
    url_patterns = [
        r"www\.", r"http", r"https",
        r"\.com", r"\.org", r"\.gov",
        r"\.net", r"\.edu"
    ]

    if any(re.search(p, lower_text) for p in url_patterns):
        print("❌ Blocked URL hallucination")
        return jsonify({
            "question": "(noise)",
            "answer": "I heard background noise. Try again."
        })

    # 8. Too short speech
    if len(text) < 5 or len(text.split()) <= 2:
        print("❌ Speech too short / unclear")
        return jsonify({
            "question": "(unclear)",
            "answer": "I couldn’t catch that clearly."
        })

    # 9. Generate AI answer (UPDATED PROMPT ONLY)
    print("📌 Asking GPT for answer...")

    prompt = f"""
You are ReadyBrain AI, an interview answer improver.

Rewrite the user's spoken answer into a short, confident, simple-English interview response.

Rules:
- Do NOT sound like a therapist.
- No emotional tone.
- No comforting phrases.
- No explanations.
- No long sentences.
- No soft words (“it's okay”, “I understand”, etc.)
- No extra comments.

Style:
- Direct and professional.
- Easy English.
- 2–3 sentences max.
- Sounds like a student answering an internship interview.

User said: "{text}"

Output ONLY the improved answer.
"""

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=prompt
        )
        answer = response.output_text.strip()

        print("📌 GPT answer:", answer)
        print("==== /interview_listen END ====")

        return jsonify({"question": text, "answer": answer})

    except Exception as e:
        print("❌ AI error:", e)
        return jsonify({"question": text, "answer": f'AI error: {e}'}), 500


# ============================
# TEXT INTERVIEW ANSWER ROUTE
# ============================

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

Write a simple, friendly, 2–3 sentence answer.
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
# LOCAL DEV SERVER
# ============================

if __name__ == "__main__":
    app.run(debug=True)
