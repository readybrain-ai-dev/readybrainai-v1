let mediaRecorder;
let audioChunks = [];
let currentMimeType = null;
let lastAnswer = "";
let lastQuestion = "";

// =====================================================
// MODES & STATE
// =====================================================
let recognition = null;
let liveTranscript = "";
let silenceTimer = null;
let isRecording = false;
let continuousMode = false;
let autoRestartTimer = null;
const SILENCE_DELAY = 3000;   // 3s silence = auto submit
const AUTO_RESTART_DELAY = 6000; // 6s after answer = auto restart
const MAX_RECORD_TIME = 30000; // 30s max recording time

let maxRecordTimer = null;

// =====================================================
// TOGGLE CONTINUOUS MODE
// =====================================================
function toggleContinuousMode() {
    continuousMode = !continuousMode;
    const btn = document.getElementById("continuousBtn");
    if (continuousMode) {
        btn.innerText = "🔄 Continuous: ON";
        btn.style.background = "var(--green)";
        btn.style.color = "var(--black)";
        if (!isRecording) startListening();
    } else {
        btn.innerText = "🔄 Continuous: OFF";
        btn.style.background = "var(--gray-mid)";
        btn.style.color = "var(--text)";
        if (autoRestartTimer) {
            clearTimeout(autoRestartTimer);
            autoRestartTimer = null;
        }
    }
}

// =====================================================
// REAL-TIME TRANSCRIPTION (Web Speech API)
// =====================================================
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
    const status = document.getElementById("status");

    recognition.onresult = (event) => {
        let interimTranscript = "";

        for (let i = 0; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
                if (!liveTranscript.includes(transcript.trim())) {
                    liveTranscript += transcript + " ";
                }
            } else {
                interimTranscript = transcript;
            }
        }

        qBox.innerHTML = `<span style="color:#e8eaed">${liveTranscript}</span><span style="color:#6b7280">${interimTranscript}</span>`;

        if (silenceTimer) clearTimeout(silenceTimer);
        silenceTimer = setTimeout(() => {
            if (isRecording && liveTranscript.trim()) {
                status.innerText = "🔄 Auto-processing...";
                stopListening();
            }
        }, SILENCE_DELAY);
    };

    recognition.onspeechend = () => {
        if (silenceTimer) clearTimeout(silenceTimer);
        silenceTimer = setTimeout(() => {
            if (isRecording && liveTranscript.trim()) {
                status.innerText = "🔄 Auto-processing...";
                stopListening();
            }
        }, SILENCE_DELAY);
    };

    recognition.onerror = (e) => {
        console.warn("Speech recognition error:", e.error);
        if (e.error === "no-speech" && isRecording && liveTranscript.trim()) {
            stopListening();
        }
    };

    recognition.onend = () => {
        if (isRecording) {
            try { recognition.start(); } catch(e) {}
        }
    };

    recognition.start();
}

// =====================================================
// SILENCE DETECTION VIA AUDIO LEVELS
// =====================================================
let audioContext = null;
let analyser = null;
let silenceCheckInterval = null;

function startSilenceDetection(stream) {
    try {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioContext.createAnalyser();
        analyser.fftSize = 512;
        const source = audioContext.createMediaStreamSource(stream);
        source.connect(analyser);

        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        let silenceStart = null;

        silenceCheckInterval = setInterval(() => {
            if (!isRecording) return;
            analyser.getByteFrequencyData(dataArray);
            const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;

            if (avg < 5) {
                // Silence detected
                if (!silenceStart) silenceStart = Date.now();
                const silenceDuration = Date.now() - silenceStart;
                if (silenceDuration >= SILENCE_DELAY && liveTranscript.trim()) {
                    document.getElementById("status").innerText = "🔄 Auto-processing...";
                    stopListening();
                }
            } else {
                // Sound detected — reset silence timer
                silenceStart = null;
                if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
            }
        }, 200);
    } catch(e) {
        console.warn("Audio context error:", e);
    }
}

function stopSilenceDetection() {
    if (silenceCheckInterval) { clearInterval(silenceCheckInterval); silenceCheckInterval = null; }
    if (audioContext) { audioContext.close(); audioContext = null; }
    analyser = null;
}

// =====================================================
// CHOOSE MIME TYPE
// =====================================================
function chooseMimeType() {
    const mimeTypes = [
        "audio/webm;codecs=opus", "audio/webm", "audio/ogg",
        "audio/mp4", "audio/mpeg", "audio/wav"
    ];
    for (const t of mimeTypes) {
        if (MediaRecorder.isTypeSupported(t)) return t;
    }
    return "";
}

// =====================================================
// RESET UI
// =====================================================
function resetUI() {
    document.getElementById("question").innerHTML = '<span class="output-placeholder">Your words will appear here as you speak…</span>';
    document.getElementById("answer").innerHTML = '<span class="output-placeholder">AI-improved answer will appear here…</span>';
    lastAnswer = "";
    lastQuestion = "";
    liveTranscript = "";

    const englishBox = document.getElementById("englishBox");
    const englishEl = document.getElementById("answerEnglish");
    const convertBtn = document.getElementById("convertEnBtn");
    const detectedEl = document.getElementById("detectedLang");

    if (englishBox) englishBox.style.display = "none";
    if (englishEl) englishEl.innerText = "";
    if (convertBtn) convertBtn.style.display = "none";
    if (detectedEl) detectedEl.innerText = "";
}

// =====================================================
// START LISTENING
// =====================================================
async function startListening() {
    resetUI();
    audioChunks = [];
    isRecording = true;

    const startBtn = document.getElementById("startBtn");
    const stopBtn  = document.getElementById("stopBtn");
    const status   = document.getElementById("status");

    startBtn.style.display = "none";
    stopBtn.style.display  = "flex";
    status.innerText = continuousMode
        ? "🎙 Listening… (continuous mode — auto-submits after silence)"
        : "🎙 Listening… Speak clearly — auto-submits after silence";

    let stream;
    try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
        status.innerText = "❌ Microphone blocked.";
        isRecording = false;
        return;
    }

    startLiveTranscription();
    startSilenceDetection(stream);

    // Auto-stop after 30 seconds max
    maxRecordTimer = setTimeout(() => {
        if (isRecording) {
            document.getElementById("status").innerText = "🔄 Auto-processing...";
            stopListening();
        }
    }, MAX_RECORD_TIME);

    currentMimeType = chooseMimeType();
    let options = {};
    if (currentMimeType) options.mimeType = currentMimeType;

    try {
        mediaRecorder = new MediaRecorder(stream, options);
    } catch (err) {
        try {
            mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/ogg" });
            currentMimeType = "audio/ogg";
        } catch (err2) {
            status.innerText = "❌ Recording not supported.";
            isRecording = false;
            return;
        }
    }

    mediaRecorder.ondataavailable = e => {
        if (e.data && e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.start();
}

// =====================================================
// STOP LISTENING
// =====================================================
async function stopListening() {
    if (!isRecording) return;
    isRecording = false;

    const startBtn = document.getElementById("startBtn");
    const stopBtn  = document.getElementById("stopBtn");
    const status   = document.getElementById("status");
    const qBox     = document.getElementById("question");
    const aBox     = document.getElementById("answer");

    stopBtn.style.display  = "none";
    startBtn.style.display = "flex";
    status.innerText = "⏳ Processing… Please wait";

    stopLiveTranscription();
    stopSilenceDetection();
    if (maxRecordTimer) { clearTimeout(maxRecordTimer); maxRecordTimer = null; }

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
            if (!qBox.innerText.trim()) qBox.innerText = "(unclear)";
            aBox.innerText = "Unclear. Please try again.";
            scheduleAutoRestart(status);
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
            const res = await fetch("/interview_listen", { method: "POST", body: formData });
            data = await res.json();
        } catch (err) {
            status.innerText = "Idle";
            qBox.innerText = "(server error)";
            aBox.innerText = "Could not connect to server.";
            scheduleAutoRestart(status);
            return;
        }

        if (data.error === "limit_reached") {
            document.getElementById("premiumPopup").style.display = "flex";
            status.innerText = "Idle";
            return;
        }

        const question = data.question ?? "";
        const answer = data.answer ?? "";

        if (question && question !== "(unclear)") {
            qBox.innerText = question;
            lastQuestion = question;
        } else if (liveTranscript.trim()) {
            qBox.innerText = liveTranscript.trim();
            lastQuestion = liveTranscript.trim();
        }

        const showAnswer = (ans) => {
            aBox.innerText = ans;
            lastAnswer = ans;
            const convertBtn = document.getElementById("convertEnBtn");
            if (convertBtn) {
                convertBtn.style.display = "inline-block";
                convertBtn.innerText = "🇺🇸 Convert to English";
                convertBtn.disabled = false;
            }
            status.innerText = "Idle";
            scheduleAutoRestart(status);
        };

        if (answer && answer !== "Unclear. Please try again.") {
            showAnswer(answer);
        } else if (lastQuestion) {
            aBox.innerText = "⏳ Getting answer…";
            fetch("/interview_regen", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text: lastQuestion })
            }).then(r => r.json()).then(d => {
                if (d.answer) showAnswer(d.answer);
                else { aBox.innerText = "Could not get answer."; scheduleAutoRestart(status); }
            }).catch(() => {
                aBox.innerText = "Could not get answer.";
                scheduleAutoRestart(status);
            });
        } else {
            status.innerText = "Idle";
            scheduleAutoRestart(status);
        }

        const detectedEl = document.getElementById("detectedLang");
        if (detectedEl && data.detected_language) {
            detectedEl.innerText = "Detected language: " + data.detected_language;
        }
    };
}

// =====================================================
// AUTO RESTART IN CONTINUOUS MODE
// =====================================================
function scheduleAutoRestart(status) {
    if (!continuousMode) return;
    if (autoRestartTimer) clearTimeout(autoRestartTimer);

    let countdown = AUTO_RESTART_DELAY / 1000;
    const interval = setInterval(() => {
        countdown--;
        if (status) status.innerText = `🔄 Next question in ${countdown}s…`;
        if (countdown <= 0) clearInterval(interval);
    }, 1000);

    autoRestartTimer = setTimeout(() => {
        clearInterval(interval);
        if (continuousMode) startListening();
    }, AUTO_RESTART_DELAY);
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
    if (!spoken) { aBox.innerText = "(no text to regenerate)"; return; }
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