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
const SILENCE_DELAY = 3000;
const AUTO_RESTART_DELAY = 6000;
const MAX_RECORD_TIME = 30000;
let maxRecordTimer = null;

// =====================================================
// TOGGLE CONTINUOUS MODE
// =====================================================
function toggleContinuousMode() {
    continuousMode = !continuousMode;
    const btn = document.getElementById("continuousBtn");
    if (continuousMode) {
        btn.innerText = "🔄 Continuous: ON";
        btn.classList.add("active");
        if (!isRecording) startListening();
    } else {
        btn.innerText = "🔄 Continuous: OFF";
        btn.classList.remove("active");
        if (autoRestartTimer) { clearTimeout(autoRestartTimer); autoRestartTimer = null; }
    }
}

// =====================================================
// REAL-TIME TRANSCRIPTION (Web Speech API)
// =====================================================
function startLiveTranscription() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        console.warn("Web Speech API not supported.");
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
    };

    recognition.onerror = (e) => {
        console.warn("Speech recognition error:", e.error);
    };

    recognition.onend = () => {
        if (isRecording) {
            try { recognition.start(); } catch(e) {}
        }
    };

    recognition.start();
}

function stopLiveTranscription() {
    if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
    if (recognition) { recognition.stop(); recognition = null; }
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
                if (!silenceStart) silenceStart = Date.now();
                const silenceDuration = Date.now() - silenceStart;
                if (silenceDuration >= SILENCE_DELAY && liveTranscript.trim()) {
                    document.getElementById("status").innerText = "🔄 Auto-processing...";
                    stopListening();
                }
            } else {
                silenceStart = null;
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
    const types = ["audio/webm;codecs=opus","audio/webm","audio/ogg","audio/mp4","audio/mpeg","audio/wav"];
    for (const t of types) { if (MediaRecorder.isTypeSupported(t)) return t; }
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
    status.innerText = "🎙 Listening… Speak clearly";

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

    maxRecordTimer = setTimeout(() => {
        if (isRecording) {
            document.getElementById("status").innerText = "🔄 Auto-processing...";
            stopListening();
        }
    }, MAX_RECORD_TIME);

    currentMimeType = chooseMimeType();
    let options = currentMimeType ? { mimeType: currentMimeType } : {};

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
    status.innerText = "⏳ Getting answer…";

    stopLiveTranscription();
    stopSilenceDetection();
    if (maxRecordTimer) { clearTimeout(maxRecordTimer); maxRecordTimer = null; }

    if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
    }

    // ⚡ Use live transcript directly — no Whisper needed!
    await new Promise(r => setTimeout(r, 300));

    const transcript = liveTranscript.trim();

    if (!transcript) {
        status.innerText = "❌ No speech detected. Please try again.";
        aBox.innerHTML = '<span class="output-placeholder">AI-improved answer will appear here…</span>';
        scheduleAutoRestart(status);
        return;
    }

    qBox.innerText = transcript;
    lastQuestion = transcript;
    aBox.innerHTML = '<span style="color:#6b7280">⏳ Getting answer…</span>';

    const inputLang = document.getElementById("languageSelect")?.value || "auto";

    const showAnswer = (ans) => {
        aBox.innerText = ans;
        lastAnswer = ans;
        const convertBtn = document.getElementById("convertEnBtn");
        if (convertBtn) {
            convertBtn.style.display = "inline-block";
            convertBtn.innerText = "🇺🇸 Convert to English";
            convertBtn.disabled = false;
        }
        status.innerText = "✅ Done";
        scheduleAutoRestart(status);
    };

    try {
        const res = await fetch("/interview_regen", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: transcript, language: inputLang })
        });
        const data = await res.json();

        if (data.error === "limit_reached") {
            document.getElementById("premiumPopup").style.display = "flex";
            status.innerText = "Idle";
            return;
        }

        if (data.answer) showAnswer(data.answer);
        else { aBox.innerText = "Could not get answer. Please try again."; scheduleAutoRestart(status); }
    } catch (err) {
        aBox.innerText = "Server error. Please try again.";
        status.innerText = "Idle";
        scheduleAutoRestart(status);
    }
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
    const englishEl  = document.getElementById("answerEnglish");

    convertBtn.innerText = "Generating…";
    convertBtn.disabled = true;

    try {
        const res = await fetch("/interview_regen", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: textToConvert, translate_to_english: true })
        });
        const data = await res.json();
        if (data.answer) {
            englishEl.innerText = data.answer;
            englishBox.style.display = "block";
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
function copyQuestion() {
    const q = document.getElementById("question").innerText.trim();
    if (q) navigator.clipboard.writeText(q);
}

function copyAnswer() {
    const ans = document.getElementById("answer").innerText.trim();
    if (ans) navigator.clipboard.writeText(ans);
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
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: spoken })
        });
        const data = await res.json();
        aBox.innerText = data.answer || "(no answer)";
        lastAnswer = data.answer || "";
    } catch {
        aBox.innerText = "(server error)";
    }
}