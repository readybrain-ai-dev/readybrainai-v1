let mediaRecorder;
let audioChunks = [];

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

    // Safari FIX: use audio/mp4 instead of webm
    let options = { mimeType: "audio/webm; codecs=opus" };
    if (!MediaRecorder.isTypeSupported(options.mimeType)) {
        options = { mimeType: "audio/webm" };
    }
    if (!MediaRecorder.isTypeSupported(options.mimeType)) {
        // Final fallback for Safari
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

        // ⭐ IMPORTANT FIX: wait for all chunks to finish
        await new Promise(r => setTimeout(r, 300));

        // Safari FIX: detect Blob type
        const mimeType =
            MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/mp4";

        const blob = new Blob(audioChunks, { type: mimeType });
        const formData = new FormData();

        // Always send filename ending in webm or mp4
        formData.append(
            "audio",
            blob,
            mimeType === "audio/webm" ? "audio.webm" : "audio.mp4"
        );

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

        // ⭐ ALWAYS SHOW RESPONSE — EVEN SILENCE & NOISE ⭐
        document.getElementById("question").innerText =
            data.question ?? "(no text)";

        document.getElementById("answer").innerText =
            data.answer ?? "(no answer)";

        status.innerText = "Idle";
    };
}

