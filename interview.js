let mediaRecorder;
let audioChunks = [];
let lastAnswer = "";

// ===========================
// START LISTENING
// ===========================
async function startListening() {
    audioChunks = [];

    document.getElementById("startBtn").style.display = "none";
    document.getElementById("stopBtn").style.display = "inline-block";

    const status = document.getElementById("status");
    status.innerText = "Listening...";

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    let options = { mimeType: "audio/webm; codecs=opus" };
    if (!MediaRecorder.isTypeSupported(options.mimeType)) {
        options = { mimeType: "audio/webm" };
    }
    if (!MediaRecorder.isTypeSupported(options.mimeType)) {
        options = { mimeType: "audio/mp4" };
    }

    mediaRecorder = new MediaRecorder(stream, options);

    mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
            audioChunks.push(e.data);
        }
    };

    mediaRecorder.start();
}


// ===========================
// STOP LISTENING
// ===========================
async function stopListening() {
    const status = document.getElementById("status");
    status.innerText = "Processing...";

    document.getElementById("stopBtn").style.display = "none";
    document.getElementById("startBtn").style.display = "inline-block";

    mediaRecorder.stop();

    mediaRecorder.onstop = async () => {
        await new Promise(r => setTimeout(r, 300));

        const mimeType =
            MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/mp4";

        const blob = new Blob(audioChunks, { type: mimeType });
        const formData = new FormData();

        const langSelect = document.getElementById("languageSelect");
        formData.append("audio", blob, mimeType === "audio/webm" ? "audio.webm" : "audio.mp4");
        if (langSelect) formData.append("language", langSelect.value);

        let data;
        try {
            const response = await fetch("/interview_listen", {
                method: "POST",
                body: formData
            });
            data = await response.json();
        } catch (error) {
            document.getElementById("question").innerText = "(error)";
            document.getElementById("answer").innerText = "Could not reach server.";
            status.innerText = "Idle";
            return;
        }

        // Show transcription
        document.getElementById("question").innerText = data.question ?? "(no text)";

        // Show detected language
        const detectedEl = document.getElementById("detectedLang");
        if (detectedEl && data.detected_language) {
            detectedEl.innerText = "Detected language: " + data.detected_language;
        }

        // Show main answer
        const answerEl = document.getElementById("answer");
        answerEl.innerText = data.answer ?? "(no answer)";
        lastAnswer = data.answer ?? "";

        // Hide English box and reset
        const englishBox = document.getElementById("englishBox");
        const englishEl = document.getElementById("answerEnglish");
        const copyEnWrapper = document.getElementById("copyEnWrapper");
        if (englishBox) englishBox.style.display = "none";
        if (englishEl) englishEl.innerText = "";
        if (copyEnWrapper) copyEnWrapper.style.display = "none";

        // Always show Convert to English button if there's an answer
        const convertBtn = document.getElementById("convertEnBtn");
        if (convertBtn && data.answer) {
            convertBtn.style.display = "inline-block";
            convertBtn.innerText = "🇺🇸 Convert to English";
            convertBtn.disabled = false;
        }

        status.innerText = "Idle";
    };
}

// ===========================
// CONVERT TO ENGLISH
// ===========================
async function convertToEnglish() {
    if (!lastAnswer) return;

    const convertBtn = document.getElementById("convertEnBtn");
    const englishBox = document.getElementById("englishBox");
    const englishEl = document.getElementById("answerEnglish");
    const copyEnWrapper = document.getElementById("copyEnWrapper");

    convertBtn.innerText = "Translating...";
    convertBtn.disabled = true;

    try {
        const response = await fetch("/interview_regen", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: lastAnswer, translate_to_english: true })
        });
        const data = await response.json();

        if (data.answer) {
            englishEl.innerText = data.answer;
            englishBox.style.display = "block";
            if (copyEnWrapper) copyEnWrapper.style.display = "block";
        }
    } catch (e) {
        englishEl.innerText = "Could not translate. Please try again.";
        englishBox.style.display = "block";
    }

    convertBtn.innerText = "🇺🇸 Convert to English";
    convertBtn.disabled = false;
}

// ===========================
// COPY FUNCTIONS
// ===========================
function copyAnswer() {
    const text = document.getElementById("answer").innerText;
    if (text) navigator.clipboard.writeText(text);
}

function copyEnglish() {
    const text = document.getElementById("answerEnglish").innerText;
    if (text) navigator.clipboard.writeText(text);
}