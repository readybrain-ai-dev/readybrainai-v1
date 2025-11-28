let mediaRecorder;
let audioChunks = [];
let currentMimeType = null;

// =====================================================
// PICK BEST MIME TYPE (CROSS-PLATFORM)
// =====================================================
function chooseMimeType() {
    const mimeTypes = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/ogg",
        "audio/mp4",
        "audio/mpeg",
        "audio/wav"
    ];

    for (const t of mimeTypes) {
        if (MediaRecorder.isTypeSupported(t)) {
            console.log("✓ Using MIME:", t);
            return t;
        }
    }

    console.warn("⚠ No supported MIME type found — using fallback.");
    return "";
}

// =====================================================
// RESET UI FOR NEW RECORDING
// =====================================================
function resetUI() {
    document.getElementById("question").innerText = "";
    document.getElementById("answer").innerText = "";

    const oldTag = document.getElementById("detectedLang");
    if (oldTag) oldTag.remove();
}

// =====================================================
// START LISTENING
// =====================================================
async function startListening() {
    resetUI();
    audioChunks = [];

    const startBtn = document.getElementById("startBtn");
    const stopBtn  = document.getElementById("stopBtn");
    const status   = document.getElementById("status");

    startBtn.style.display = "none";
    stopBtn.style.display  = "inline-block";
    status.innerText = "🎙 Listening… please speak clearly.";

    let stream;
    try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
        status.innerText = "❌ Microphone access blocked.";
        return;
    }

    currentMimeType = chooseMimeType();
    let options = {};
    if (currentMimeType) options.mimeType = currentMimeType;

    try {
        mediaRecorder = new MediaRecorder(stream, options);
    } catch (err) {
        console.warn("Primary MIME failed — trying OGG fallback…");

        try {
            mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/ogg" });
            currentMimeType = "audio/ogg";
        } catch (err2) {
            status.innerText = "❌ Your device does not support recording.";
            return;
        }
    }

    mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.start();
    console.log("🎧 Recording started.");
}

// =====================================================
// STOP LISTENING & PROCESS
// =====================================================
async function stopListening() {
    const startBtn = document.getElementById("startBtn");
    const stopBtn  = document.getElementById("stopBtn");
    const status   = document.getElementById("status");
    const qBox     = document.getElementById("question");
    const aBox     = document.getElementById("answer");

    stopBtn.style.display  = "none";
    startBtn.style.display = "inline-block";
    status.innerText = "⏳ Processing audio… please wait.";

    if (!mediaRecorder || mediaRecorder.state === "inactive") {
        status.innerText = "Idle";
        return;
    }

    mediaRecorder.stop();

    mediaRecorder.onstop = async () => {
        await new Promise(r => setTimeout(r, 200)); // gather final chunks

        let blob;
        try {
            blob = new Blob(audioChunks, { type: currentMimeType });
        } catch {
            blob = new Blob(audioChunks, { type: "audio/ogg" });
            currentMimeType = "audio/ogg";
        }

        if (blob.size < 800) {
            status.innerText = "❌ No voice detected.";
            qBox.innerText = "(No speech detected)";
            aBox.innerText = "(No output)";
            return;
        }

        // Determine file extension
        let ext = "webm";
        if (currentMimeType.includes("ogg"))  ext = "ogg";
        if (currentMimeType.includes("mp4"))  ext = "mp4";
        if (currentMimeType.includes("mpeg")) ext = "mp3";

        const formData = new FormData();
        formData.append("audio", blob, "speech." + ext);

        // language settings
        const inputLang  = document.getElementById("languageSelect")?.value || "auto";
        const outputLang = document.getElementById("outputLanguage")?.value || "same";

        formData.append("language", inputLang);
        formData.append("output_language", outputLang);

        // fetch backend
        let data;
        try {
            const res = await fetch("/interview_listen", {
                method: "POST",
                body: formData
            });
            data = await res.json();
        } catch (err) {
            status.innerText = "Idle";
            qBox.innerText = "(Server error)";
            aBox.innerText = "Could not reach server.";
            return;
        }

        // display result
        qBox.innerText = data.question ?? "(No transcript)";
        aBox.innerText = data.answer ?? "(No improved answer)";
        status.innerText = "Idle";

        // detected language tag
        if (data.detected_language) {
            const tag = document.createElement("div");
            tag.id = "detectedLang";
            tag.style.fontSize = "12px";
            tag.style.color = "#64748b";
            tag.style.marginTop = "4px";
            tag.innerText = "Detected language: " + data.detected_language;
            qBox.parentNode.insertBefore(tag, qBox);
        }
    };
}

// =====================================================
// COPY ANSWER
// =====================================================
function copyAnswer() {
    const ans = document.getElementById("answer").innerText.trim();
    if (!ans) return;
    navigator.clipboard.writeText(ans);
}

// =====================================================
// REGENERATE ANSWER
// =====================================================
async function regenerateAnswer() {
    const spoken = document.getElementById("question").innerText.trim();
    const aBox = document.getElementById("answer");

    if (!spoken) {
        aBox.innerText = "(No text to regenerate)";
        return;
    }

    aBox.innerText = "⏳ Regenerating answer…";

    try {
        const res = await fetch("/interview_regen", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ text: spoken })
        });

        const data = await res.json();
        aBox.innerText = data.answer || "(No answer)";
    } catch {
        aBox.innerText = "(Server error)";
    }
}

// =====================================================
// TEXT MODE GENERATION
// =====================================================
async function generateTextAnswer() {
    const question = document.getElementById("textQuestion").value.trim();
    const jobRole  = document.getElementById("textJobRole").value.trim();
    const bg       = document.getElementById("textBackground").value.trim();
    const statusEl = document.getElementById("textStatus");
    const aBox     = document.getElementById("answer");

    if (!question) {
        statusEl.innerText = "Please enter your question first.";
        return;
    }

    statusEl.innerText = "⏳ Generating answer…";

    try {
        const res = await fetch("/interview_answer", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ question, job_role: jobRole, background: bg })
        });

        const data = await res.json();
        aBox.innerText = data.answer || "(No answer)";
        statusEl.innerText = "Done.";
    } catch {
        statusEl.innerText = "Error: Could not generate answer.";
    }
}
