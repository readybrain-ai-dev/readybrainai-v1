let mediaRecorder;
let audioChunks = [];
let currentMimeType = null;
let lastAnswer = "";
let lastQuestion = "";

// =====================================================
// REAL-TIME TRANSCRIPTION (Web Speech API)
// =====================================================
let recognition = null;
let liveTranscript = "";

function startLiveTranscription() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        console.warn("Web Speech API not supported on this browser.");
        return;
    }

    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    const qBox = document.getElementById("question");

    recognition.onresult = (event) => {
        let interim = "";
        let final = "";

        for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
                final += transcript;
            } else {
                interim += transcript;
            }
        }

        if (final) liveTranscript += final;

        // Show live text with interim in gray
        qBox.innerHTML = `<span style="color:#e8eaed">${liveTranscript}</span><span style="color:#6b7280">${interim}</span>`;
    };

    recognition.onerror = (e) => {
        console.warn("Speech recognition error:", e.error);
    };

    recognition.start();
    console.log("🎤 Live transcription started");
}

function stopLiveTranscription() {
    if (recognition) {
        recognition.stop();
        recognition = null;
    }
}

// =====================================================
// CHOOSE THE BEST MIME TYPE
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
            console.log("Using MIME:", t);
            return t;
        }
    }

    console.warn("⚠ No supported MIME type found. Using empty fallback.");
    return "";
}

// =====================================================
// RESET UI
// =====================================================
function resetUI() {
    document.getElementById("question").innerText = "";
    document.getElementById("answer").innerText = "";
    lastAnswer = "";
    lastQuestion = "";
    liveTranscript = "";

    const englishBox = document.getElementById("englishBox");
    const englishEl = document.getElementById("answerEnglish");
    const copyEnWrapper = document.getElementById("copyEnWrapper");
    const convertBtn = document.getElementById("convertEnBtn");
    const detectedEl = document.getElementById("detectedLang");

    if (englishBox) englishBox.style.display = "none";
    if (englishEl) englishEl.innerText = "";
    if (copyEnWrapper) copyEnWrapper.style.display = "none";
    if (convertBtn) convertBtn.style.display = "none";
    if (detectedEl) detectedEl.innerText = "";
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
    status.innerText = "🎙 Listening… Speak clearly";

    let stream;
    try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
        status.innerText = "❌ Microphone blocked.";
        return;
    }

    // Start live transcription
    startLiveTranscription();

    currentMimeType = chooseMimeType();
    let options = {};
    if (currentMimeType) options.mimeType = currentMimeType;

    try {
        mediaRecorder = new MediaRecorder(stream, options);
    } catch (err) {
        console.warn("Main MIME failed. Trying ogg…");
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

    mediaRecorder.start();
    console.log("🎧 Recording started");
}

// =====================================================
// STOP LISTENING
// =====================================================
async function stopListening() {
    const startBtn = document.getElementById("startBtn");
    const stopBtn  = document.getElementById("stopBtn");
    const status   = document.getElementById("status");
    const qBox     = document.getElementById("question");
    const aBox     = document.getElementById("answer");

    stopBtn.style.display  = "none";
    startBtn.style.display = "inline-block";
    status.innerText = "⏳ Processing… Please wait";

    // Stop live transcription
    stopLiveTranscription();

    if (!mediaRecorder || mediaRecorder.state === "inactive") {
        status.innerText = "Idle";
        return;
    }

    mediaRecorder.stop();

    mediaRecorder.onstop = async () => {
        await new Promise(r => setTimeout(r, 200));

        let blob;
        try {
            blob = new Blob(audioChunks, { type: currentMimeType });
        } catch (err) {
            blob = new Blob(audioChunks, { type: "audio/ogg" });
            currentMimeType = "audio/ogg";
        }

        if (blob.size < 800) {
            status.innerText = "❌ No clear voice detected.";
            qBox.innerText = "(unclear)";
            aBox.innerText = "Unclear. Please try again.";
            return;
        }

        let ext = "webm";
        if (currentMimeType.includes("ogg")) ext = "ogg";
        if (currentMimeType.includes("mp4")) ext = "mp4";
        if (currentMimeType.includes("mpeg")) ext = "mp3";

        const formData = new FormData();
        formData.append("audio", blob, "speech." + ext);

        const inputLang = document.getElementById("languageSelect")?.value || "auto";
        formData.append("language", inputLang);

        let data;
        try {
            const res = await fetch("/interview_listen", {
                method: "POST",
                body: formData
            });
            data = await res.json();
        } catch (err) {
            status.innerText = "Idle";
            qBox.innerText = "(server error)";
            aBox.innerText = "Could not connect to server.";
            return;
        }

        if (data.error === "limit_reached") {
            document.getElementById("premiumPopup").style.display = "flex";
            status.innerText = "Idle";
            return;
        }

        qBox.innerText = data.question ?? "(unclear)";
        aBox.innerText = data.answer ?? "(unclear)";

        lastQuestion = data.question ?? "";
        lastAnswer = data.answer ?? "";

        status.innerText = "Idle";

        const detectedEl = document.getElementById("detectedLang");
        if (detectedEl && data.detected_language) {
            detectedEl.innerText = "Detected language: " + data.detected_language;
        }

        const convertBtn = document.getElementById("convertEnBtn");
        if (convertBtn && lastAnswer) {
            convertBtn.style.display = "inline-block";
            convertBtn.innerText = "🇺🇸 Convert to English";
            convertBtn.disabled = false;
        }
    };
}

// =====================================================
// CONVERT TO ENGLISH
// =====================================================
async function convertToEnglish() {
    const textToConvert = lastQuestion || lastAnswer;
    if (!textToConvert) return;

    const convertBtn = document.getElementById("convertEnBtn");
    const englishBox = document.getElementById("englishBox");
    const englishEl = document.getElementById("answerEnglish");
    const copyEnWrapper = document.getElementById("copyEnWrapper");

    convertBtn.innerText = "Generating…";
    convertBtn.disabled = true;

    try {
        const response = await fetch("/interview_regen", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: textToConvert, translate_to_english: true })
        });
        const data = await response.json();

        if (data.answer) {
            englishEl.innerText = data.answer;
            englishBox.style.display = "block";
            if (copyEnWrapper) copyEnWrapper.style.display = "block";
        }
    } catch (e) {
        englishEl.innerText = "Could not generate. Please try again.";
        englishBox.style.display = "block";
    }

    convertBtn.innerText = "🇺🇸 Convert to English";
    convertBtn.disabled = false;
}

// =====================================================
// COPY FUNCTIONS
// =====================================================
function copyAnswer() {
    const ans = document.getElementById("answer").innerText.trim();
    if (!ans) return;
    navigator.clipboard.writeText(ans);
}

function copyEnglish() {
    const text = document.getElementById("answerEnglish").innerText.trim();
    if (text) navigator.clipboard.writeText(text);
}

// =====================================================
// REGENERATE ANSWER
// =====================================================
async function regenerateAnswer() {
    const spoken = document.getElementById("question").innerText.trim();
    const aBox = document.getElementById("answer");

    if (!spoken) {
        aBox.innerText = "(no text to regenerate)";
        return;
    }

    aBox.innerText = "⏳ Regenerating…";

    try {
        const res = await fetch("/interview_regen", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ text: spoken })
        });
        const data = await res.json();
        aBox.innerText = data.answer || "(no answer)";
        lastAnswer = data.answer || "";
    } catch {
        aBox.innerText = "(server error)";
    }
}