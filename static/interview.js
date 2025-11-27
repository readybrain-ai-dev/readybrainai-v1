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
        "audio/ogg",       // ⭐ Android Fix
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
// START LISTENING
// ======================================
async function startListening() {
    audioChunks = [];

    const startBtn = document.getElementById("startBtn");
    const stopBtn = document.getElementById("stopBtn");
    const status = document.getElementById("status");

    if (!startBtn || !stopBtn || !status) {
        console.error("Missing DOM elements for start/stop/status.");
        return;
    }

    startBtn.style.display = "none";
    stopBtn.style.display = "inline-block";
    status.innerText = "Listening...";

    let stream;
    try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
        status.innerText = "Microphone blocked. Enable microphone.";
        console.error("Microphone permission error:", err);
        return;
    }

    currentMimeType = chooseMimeType();
    let options = {};

    if (currentMimeType) {
        options.mimeType = currentMimeType;
    }

    try {
        mediaRecorder = new MediaRecorder(stream, options);
    } catch (err) {
        console.error("MediaRecorder init error:", err);

        // ⭐ Emergency fallback for tough Android / browsers
        try {
            mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/ogg" });
            currentMimeType = "audio/ogg";
            console.warn("Fallback to audio/ogg for Android.");
        } catch (err2) {
            console.error("Second MediaRecorder init error:", err2);
            status.innerText = "Recording not supported on this device.";
            return;
        }
    }

    mediaRecorder.ondataavailable = (evt) => {
        if (evt.data && evt.data.size > 0) {
            audioChunks.push(evt.data);
        }
    };

    mediaRecorder.onstart = () => {
        console.log("🎙 Recording started — mime:", currentMimeType);
    };

    mediaRecorder.onerror = (err) => {
        console.error("MediaRecorder Error:", err);
        status.innerText = "Recording error.";
    };

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

    if (!startBtn || !stopBtn || !status || !questionBox || !answerBox) {
        console.error("Missing UI elements.");
        return;
    }

    status.innerText = "Processing...";

    stopBtn.style.display = "none";
    startBtn.style.display = "inline-block";

    if (!mediaRecorder || mediaRecorder.state === "inactive") {
        status.innerText = "Idle";
        return;
    }

    mediaRecorder.stop();

    mediaRecorder.onstop = async () => {
        // ⭐ Android-delivery wait
        await new Promise((r) => setTimeout(r, 250));

        // Build final blob
        let blob;
        try {
            blob = new Blob(audioChunks, { type: currentMimeType });
        } catch {
            blob = new Blob(audioChunks, { type: "audio/ogg" });
            currentMimeType = "audio/ogg";
        }

        console.log("🎧 Blob size:", blob.size, "| type:", currentMimeType);

        // If no voice detected
        if (blob.size < 800) {
            status.innerText = "No audio detected.";
            questionBox.innerText = "(no voice captured)";
            answerBox.innerText = "(no answer)";
            return;
        }

        const formData = new FormData();

        let fileExt = "webm";
        if (currentMimeType.includes("ogg")) fileExt = "ogg";
        if (currentMimeType.includes("mp4")) fileExt = "mp4";

        formData.append("audio", blob, "speech." + fileExt);

        // ⭐ Language selection (Auto detect included)
        const langSelect = document.getElementById("languageSelect");
        const lang = langSelect ? langSelect.value : "auto";
        formData.append("language", lang);

        let data;

        try {
            const response = await fetch("/interview_listen", {
                method: "POST",
                body: formData,
            });

            data = await response.json();
        } catch (err) {
            console.error("❌ Server error:", err);
            status.innerText = "Idle";
            questionBox.innerText = "(server error)";
            answerBox.innerText = "Could not connect.";
            return;
        }

        // Show API results
        questionBox.innerText = data.question ?? "(no text)";
        answerBox.innerText = data.answer ?? "(no answer)";

        status.innerText = "Idle";
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
// REGENERATE ANSWER BUTTON
// ===============================================
async function regenerateAnswer() {
    const spoken = document.getElementById("question").innerText.trim();
    const answerBox = document.getElementById("answer");

    if (!spoken) {
        answerBox.innerText = "(no text to regenerate)";
        return;
    }

    try {
        const res = await fetch("/interview_regen", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: spoken })
        });

        const data = await res.json();
        answerBox.innerText = data.answer || "(no answer)";
    } catch (err) {
        console.error("❌ Regen error:", err);
        answerBox.innerText = "(server error)";
    }
}

// ===============================================
// TEXT MODE (typing instead of voice)
// ===============================================
async function generateTextAnswer() {
    const questionEl = document.getElementById("textQuestion");
    const jobRoleEl = document.getElementById("textJobRole");
    const backgroundEl = document.getElementById("textBackground");
    const statusEl = document.getElementById("textStatus");
    const answerBox = document.getElementById("answer");

    const question = questionEl.value.trim();
    const jobRole = jobRoleEl.value.trim();
    const background = backgroundEl.value.trim();

    if (!question) {
        statusEl.textContent = "Please type the interview question first.";
        return;
    }

    statusEl.textContent = "Generating answer...";

    try {
        const res = await fetch("/interview_answer", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                question: question,
                job_role: jobRole,
                background: background
            })
        });

        const data = await res.json();
        answerBox.textContent = data.answer || "(no answer)";
        statusEl.textContent = "Done.";
    } catch (err) {
        console.error("Text mode error:", err);
        statusEl.textContent = "Error: could not generate answer.";
    }
}
