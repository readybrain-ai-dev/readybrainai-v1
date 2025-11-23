let mediaRecorder;
let audioChunks = [];
let currentMimeType = null;

// ===========================
// CHOOSE BEST MIME TYPE (GLOBAL SUPPORT)
// ===========================
function chooseMimeType() {
    const mimeTypes = [
        "audio/webm;codecs=opus",
        "audio/webm",
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

// ===========================
// START LISTENING
// ===========================
async function startListening() {
    audioChunks = [];

    document.getElementById("startBtn").style.display = "none";
    document.getElementById("stopBtn").style.display = "inline-block";

    const status = document.getElementById("status");
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
        status.innerText = "Recording not supported on this device.";
        return;
    }

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

    if (!mediaRecorder || mediaRecorder.state === "inactive") {
        status.innerText = "Idle";
        return;
    }

    mediaRecorder.stop();

    mediaRecorder.onstop = async () => {

        // Wait a moment for all chunks to finalize
        await new Promise(r => setTimeout(r, 250));

        const blob = new Blob(audioChunks, { type: currentMimeType });

        console.log("Recorded blob size:", blob.size, "type:", currentMimeType);

        // Detect empty Android recording
        if (blob.size < 800) {
            status.innerText = "No audio detected.";
            document.getElementById("question").innerText = "(no voice captured)";
            document.getElementById("answer").innerText = "(no answer)";
            return;
        }

        const formData = new FormData();
        const fileExt = currentMimeType.includes("webm") ? "webm" : "mp4";
        formData.append("audio", blob, "speech." + fileExt);

        let data;
        try {
            const response = await fetch("/interview_listen", {
                method: "POST",
                body: formData
            });

            data = await response.json();
        } catch (err) {
            console.error("Server error:", err);
            status.innerText = "Idle";
            document.getElementById("question").innerText = "(server error)";
            document.getElementById("answer").innerText = "Could not connect.";
            return;
        }

        // SHOW RESULTS
        document.getElementById("question").innerText =
            data.question ?? "(no text)";

        document.getElementById("answer").innerText =
            data.answer ?? "(no answer)";

        status.innerText = "Idle";
    };
}
