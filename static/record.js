// Field-scoring audio recorder. Records observation audio in the browser and
// submits it as a normal multipart form POST (via a hidden <input type=file>
// populated through DataTransfer) so the page follows the same full-page
// server-render flow as every other action in this app — no fetch/JSON glue.
(function () {
  "use strict";

  const startBtn = document.getElementById("rec-start");
  const stopBtn = document.getElementById("rec-stop");
  const status = document.getElementById("rec-status");
  const form = document.getElementById("transcribe-form");
  const fileInput = document.getElementById("audio-input");

  if (!startBtn || !stopBtn || !form || !fileInput) return;

  if (!navigator.mediaDevices || !window.MediaRecorder) {
    status.textContent = "Recording is not supported in this browser. Use the text narrative instead.";
    startBtn.disabled = true;
    return;
  }

  let mediaRecorder = null;
  let chunks = [];

  startBtn.addEventListener("click", async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.addEventListener("dataavailable", (e) => {
        if (e.data && e.data.size > 0) chunks.push(e.data);
      });
      mediaRecorder.addEventListener("stop", () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunks, { type: "audio/webm" });
        const file = new File([blob], "observation.webm", { type: "audio/webm" });
        const transfer = new DataTransfer();
        transfer.items.add(file);
        fileInput.files = transfer.files;
        status.textContent = "Transcribing and scoring — this can take a moment...";
        form.submit();
      });
      mediaRecorder.start();
      startBtn.disabled = true;
      stopBtn.disabled = false;
      status.textContent = "Recording...";
    } catch (err) {
      status.textContent = "Microphone access failed: " + err.message;
    }
  });

  stopBtn.addEventListener("click", () => {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }
    stopBtn.disabled = true;
  });
})();
