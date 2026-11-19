(function () {
  const VIDEO_CONSTRAINTS = { video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } } };

  function setCardState(card, state) {
    if (!card) return;
    card.classList.remove('face-card--success', 'face-card--error');
    if (state === 'success') {
      card.classList.add('face-card--success');
    } else if (state === 'error') {
      card.classList.add('face-card--error');
    }
  }

  function stopStream(stream) {
    if (!stream) return;
    stream.getTracks().forEach((track) => {
      try {
        track.stop();
      } catch (_) {
        // ignore
      }
    });
  }

  function captureSnapshot(video, canvas) {
    if (!video || !canvas) return '';
    const width = video.videoWidth || 640;
    const height = video.videoHeight || 480;
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d');
    context.drawImage(video, 0, 0, width, height);
    return canvas.toDataURL('image/png');
  }

  function initFaceEnrollment(options) {
    const {
      cardSelector,
      statusSelector,
      startButtonSelector,
      captureButtonSelector,
      retakeButtonSelector,
      videoSelector,
      canvasSelector,
      previewSelector,
      snapshotFieldSelector,
      submitButtonSelector,
    } = options;

    const card = document.querySelector(cardSelector);
    if (!card) return;

    const statusEl = card.querySelector(statusSelector);
    const startBtn = card.querySelector(startButtonSelector);
    const captureBtn = card.querySelector(captureButtonSelector);
    const retakeBtn = card.querySelector(retakeButtonSelector);
    const video = card.querySelector(videoSelector);
    const canvas = card.querySelector(canvasSelector);
    const preview = card.querySelector(previewSelector);
    const snapshotField = document.querySelector(snapshotFieldSelector);
    const submitBtn = document.querySelector(submitButtonSelector);

    if (!statusEl || !startBtn || !captureBtn || !video || !canvas || !preview || !snapshotField || !submitBtn) {
      return;
    }

    let mediaStream = null;

    function resetState() {
      stopStream(mediaStream);
      mediaStream = null;
      video.srcObject = null;
      video.hidden = true;
      canvas.hidden = true;
      preview.hidden = true;
      snapshotField.value = '';
      captureBtn.disabled = true;
      submitBtn.disabled = true;
      setCardState(card, 'idle');
      statusEl.textContent = 'Start the camera to capture the voter\'s face.';
      if (retakeBtn) {
        retakeBtn.hidden = true;
        retakeBtn.disabled = false;
      }
    }

    async function startCamera() {
      try {
        stopStream(mediaStream);
        mediaStream = await navigator.mediaDevices.getUserMedia(VIDEO_CONSTRAINTS);
        video.srcObject = mediaStream;
        video.hidden = false;
        preview.hidden = true;
        captureBtn.disabled = false;
        setCardState(card, 'idle');
        statusEl.textContent = 'Align the voter\'s face inside the frame, then capture.';
        if (retakeBtn) {
          retakeBtn.hidden = true;
        }
      } catch (error) {
        setCardState(card, 'error');
        statusEl.textContent = 'Unable to access camera. Please enable permissions and retry.';
        captureBtn.disabled = true;
        if (retakeBtn) retakeBtn.hidden = true;
      }
    }

    function captureFace() {
      if (!mediaStream) {
        statusEl.textContent = 'Start the camera before capturing.';
        return;
      }
      const snapshot = captureSnapshot(video, canvas);
      if (!snapshot) {
        setCardState(card, 'error');
        statusEl.textContent = 'Capture failed. Please try again.';
        return;
      }
      snapshotField.value = snapshot;
      preview.src = snapshot;
      preview.hidden = false;
      video.hidden = true;
      setCardState(card, 'success');
      statusEl.textContent = 'Face captured successfully.';
      captureBtn.disabled = true;
      submitBtn.disabled = false;
      if (retakeBtn) {
        retakeBtn.hidden = false;
      }
      stopStream(mediaStream);
      mediaStream = null;
    }

    function handleRetake() {
      resetState();
      startCamera();
    }

    startBtn.addEventListener('click', startCamera);
    captureBtn.addEventListener('click', captureFace);
    if (retakeBtn) {
      retakeBtn.addEventListener('click', handleRetake);
    }

    resetState();
  }

  function initFaceSignin(options) {
    const {
      cardSelector,
      statusSelector,
      startButtonSelector,
      captureButtonSelector,
      retakeButtonSelector,
      videoSelector,
      canvasSelector,
      previewSelector,
      snapshotFieldSelector,
      submitButtonSelector,
      formSelector,
    } = options;

    const card = document.querySelector(cardSelector);
    if (!card) return;

    const statusEl = card.querySelector(statusSelector);
    const startBtn = card.querySelector(startButtonSelector);
    const captureBtn = card.querySelector(captureButtonSelector);
    const retakeBtn = card.querySelector(retakeButtonSelector);
    const video = card.querySelector(videoSelector);
    const canvas = card.querySelector(canvasSelector);
    const preview = card.querySelector(previewSelector);
    const snapshotField = document.querySelector(snapshotFieldSelector);
    const submitBtn = document.querySelector(submitButtonSelector);
    const form = document.querySelector(formSelector);

    if (!statusEl || !startBtn || !captureBtn || !video || !canvas || !preview || !snapshotField || !submitBtn || !form) {
      return;
    }

    let mediaStream = null;

    function resetState() {
      stopStream(mediaStream);
      mediaStream = null;
      video.srcObject = null;
      video.hidden = true;
      preview.hidden = true;
      snapshotField.value = '';
      captureBtn.disabled = true;
      submitBtn.disabled = true;
      setCardState(card, 'idle');
      statusEl.textContent = 'Start the camera to verify your identity.';
      if (retakeBtn) {
        retakeBtn.hidden = true;
        retakeBtn.disabled = false;
      }
    }

    async function startCamera() {
      try {
        stopStream(mediaStream);
        mediaStream = await navigator.mediaDevices.getUserMedia(VIDEO_CONSTRAINTS);
        video.srcObject = mediaStream;
        video.hidden = false;
        captureBtn.disabled = false;
        setCardState(card, 'idle');
        statusEl.textContent = 'Align your face inside the frame, then capture.';
        if (retakeBtn) {
          retakeBtn.hidden = true;
        }
      } catch (error) {
        setCardState(card, 'error');
        statusEl.textContent = 'Camera access denied. Allow camera permissions to continue.';
        captureBtn.disabled = true;
        if (retakeBtn) retakeBtn.hidden = true;
      }
    }

    function captureFace() {
      if (!mediaStream) {
        statusEl.textContent = 'Start the camera before capturing.';
        return;
      }
      const snapshot = captureSnapshot(video, canvas);
      if (!snapshot) {
        setCardState(card, 'error');
        statusEl.textContent = 'Capture failed. Please try again.';
        return;
      }
      snapshotField.value = snapshot;
      preview.src = snapshot;
      preview.hidden = false;
      video.hidden = true;
      setCardState(card, 'success');
      statusEl.textContent = 'Face captured. Click "Verify face & Login" to continue.';
      captureBtn.disabled = true;
      submitBtn.disabled = false;
      if (retakeBtn) {
        retakeBtn.hidden = false;
      }
      stopStream(mediaStream);
      mediaStream = null;
    }

    function handleRetake() {
      resetState();
      startCamera();
    }

    async function ensureSnapshotBeforeSubmit(event) {
      if (snapshotField.value) {
        return true;
      }
      event.preventDefault();
      if (!mediaStream) {
        await startCamera();
      }
      if (!mediaStream) {
        return false;
      }
      const snapshot = captureSnapshot(video, canvas);
      if (!snapshot) {
        setCardState(card, 'error');
        statusEl.textContent = 'Capture failed. Please press capture before logging in.';
        return false;
      }
      snapshotField.value = snapshot;
      preview.src = snapshot;
      preview.hidden = false;
      video.hidden = true;
      setCardState(card, 'success');
      statusEl.textContent = 'Face captured. Submitting...';
      captureBtn.disabled = true;
      submitBtn.disabled = true;
      if (retakeBtn) retakeBtn.hidden = false;
      stopStream(mediaStream);
      mediaStream = null;
      form.submit();
      return true;
    }

    startBtn.addEventListener('click', startCamera);
    captureBtn.addEventListener('click', captureFace);
    if (retakeBtn) {
      retakeBtn.addEventListener('click', handleRetake);
    }
    form.addEventListener('submit', ensureSnapshotBeforeSubmit);

    resetState();
  }

  window.initFaceEnrollment = window.initFaceEnrollment || initFaceEnrollment;
  window.initFaceSignin = window.initFaceSignin || initFaceSignin;
})();


