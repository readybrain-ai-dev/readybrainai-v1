let mediaRecorder;
let audioChunks = [];
let currentMimeType = null;

// ======================================
// CHOOSE BEST MIME TYPE (GLOBAL SUPPORT)
// ======================================
function chooseMimeType() {
    const mimeTypes = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/ogg",
        "audio/mp4",
        "audio/mpeg",
        "audio/wav"
    ];

    for (const type of mimeTypes) {
        if (MediaRecorder.isTypeSupported(type)) {
            console.log("Using MIME type:", type);
            return type;
        }
    }

    console.warn("⚠ No supported MIME type found. Using fallback.");
    return "";
}

// ======================================
// CLEAN UI BEFORE NEW RECORDING
// ======================================
function resetUI() {
    document.getElementById("question").innerText = "";
    document.getElementById("answer").innerText = "";

    const old = document.getElementById("detectedLang");
    if (old) old.remove();
}

// ======================================
// START LISTENING
// ======================================
async function startListening() {
    resetUI();
    audioChunks = [];

    const startBtn = document.getElementById("startBtn");
    const stopBtn = document.getElementById("stopBtn");
    const status = document.getElementById("status");

    startBtn.style.display = "none";
    stopBtn.style.display = "inline-block";
    status.innerText = "🎙 Listening… Speak clearly";

    let stream;
    try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
        status.innerText = "❌ Microphone blocked. Enable permission.";
        return;
    }

    currentMimeType = chooseMimeType();
    let options = {};
    if (currentMimeType) options.mimeType = currentMimeType;

    try {
        mediaRecorder = new MediaRecorder(stream, options);
    } catch (err) {
        // Android webm → ogg fallback
        try {
            mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/ogg" });
            currentMimeType = "audio/ogg";
        } catch (err2) {
            status.innerText = "❌ Recording not supported on this device.";
            return;
        }
    }

    mediaRecorder.ondataavailable = e => {
        if (e.data && e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstart = () => console.log("🎧 Recording started");
    mediaRecorder.start();
}

// ======================================
// STOP LISTENING
// ======================================
async function stopListening() {
    const startBtn = document.getElementById("startBtn");
    const stopBtn = document.getElementById("stopBtn");
    const status = document.getElementById("status");
    const questionBox = document.getElementById("question");
    const answerBox = document.getElementById("answer");

    stopBtn.style.display = "none";
    startBtn.style.display = "inline-block";
    status.innerText = "⏳ Processing… Please wait";

    if (!mediaRecorder || mediaRecorder.state === "inactive") {
        status.innerText = "Idle";
        return;
    }

    mediaRecorder.stop();

    mediaRecorder.onstop = async () => {
        // Wait for audio chunks
        await new Promise(r => setTimeout(r, 250));

        let blob;
        try {
            blob = new Blob(audioChunks, { type: currentMimeType });
        } catch {
            blob = new Blob(audioChunks, { type: "audio/ogg" });
            currentMimeType = "audio/ogg";
        }

        if (blob.size < 800) {
            status.innerText = "❌ No audio detected.";
            questionBox.innerText = "(no voice captured)";
            answerBox.innerText = "(no answer)";
            return;
        }

        const formData = new FormData();
        let ext = "webm";
        if (currentMimeType.includes("ogg")) ext = "ogg";
        if (currentMimeType.includes("mp4")) ext = "mp4";

        formData.append("audio", blob, "speech." + ext);

        // INPUT LANG
        const lang = document.getElementById("languageSelect")?.value || "auto";
        formData.append("language", lang);

        // OUTPUT LANG
        const outLang = document.getElementById("outputLanguage")?.value || "same";
        formData.append("output_language", outLang);

        // Send to backend
        let data;
        try {
            const response = await fetch("/interview_listen", {
                method: "POST",
                body: formData
            });
            data = await response.json();
        } catch {
            status.innerText = "Idle";
            questionBox.innerText = "(server error)";
            answerBox.innerText = "Could not connect.";
            return;
        }

        // Write results
        questionBox.innerText = data.question ?? "(no text)";
        answerBox.innerText = data.answer ?? "(no answer)";
        status.innerText = "Idle";

        // Show detected language
        if (data.detected_language) {
            const tag = document.createElement("div");
            tag.id = "detectedLang";
            tag.style.fontSize = "12px";
            tag.style.color = "#64748b";
            tag.style.marginTop = "4px";
            tag.innerText = "Detected language: " + data.detected_language;
            questionBox.parentNode.insertBefore(tag, questionBox);
        }
    };
}

// ===============================================
// COPY ANSWER BUTTON
// ===============================================
function copyAnswer() {
    const answer = document.getElementById("answer").innerText.trim();
    if (!answer) return;
    navigator.clipboard.writeText(answer);
}

// ===============================================
// REGENERATE ANSWER
// ===============================================
async function regenerateAnswer() {
    const spoken = document.getElementById("question").innerText.trim();
    const answerBox = document.getElementById("answer");

    if (!spoken) {
        answerBox.innerText = "(no text to regenerate)";
        return;
    }

    answerBox.innerText = "⏳ Regenerating…";

    try {
        const res = await fetch("/interview_regen", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ text: spoken })
        });

        const data = await res.json();
        answerBox.innerText = data.answer || "(no answer)";
    } catch {
        answerBox.innerText = "(server error)";
    }
}

// ===============================================
// TEXT MODE
// ===============================================
async function generateTextAnswer() {
    const question = document.getElementById("textQuestion").value.trim();
    const jobRole = document.getElementById("textJobRole").value.trim();
    const background = document.getElementById("textBackground").value.trim();
    const statusEl = document.getElementById("textStatus");
    const answerBox = document.getElementById("answer");

    if (!question) {
        statusEl.innerText = "Please type the interview question first.";
        return;
    }

    statusEl.innerText = "⏳ Generating…";

    try {
        const res = await fetch("/interview_answer", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ question, job_role: jobRole, background })
        });

        const data = await res.json();
        answerBox.innerText = data.answer || "(no answer)";
        statusEl.innerText = "Done.";
    } catch {
        statusEl.innerText = "Error: could not generate answer.";
    }
}
