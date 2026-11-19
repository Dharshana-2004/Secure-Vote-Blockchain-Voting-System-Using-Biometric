
// --- CSRF helpers ---
function getCookie(name) {
  const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
  return m ? m.pop() : '';
}
const CSRF = getCookie('csrftoken');

// --- UI refs (IDs must match HTML exactly) ---
const faceStatus     = document.getElementById('faceStatus');      // ✅ correct ID
const voteButtons    = Array.from(document.querySelectorAll('.vote-btn'));
const voteForms      = Array.from(document.querySelectorAll('.vote-form'));

const voteSuccess    = document.getElementById('voteSuccess');      // ✅ camelCase
const multiFaceModal = document.getElementById('multiFaceModal');
const logoutForm     = document.getElementById('logoutForm');

// Guarded helpers (won’t crash if an element is missing)
function setStatus(text, ok=false, warn=false){
  if (!faceStatus) return;
  faceStatus.textContent = text;
  faceStatus.classList.remove('status-ok','status-warn');
  if (ok)   faceStatus.classList.add('status-ok');
  if (warn) faceStatus.classList.add('status-warn');
}
function disableVotes(){ voteButtons.forEach(b => b.disabled = true); }
function enableVotes(){  voteButtons.forEach(b => b.disabled = false); }

// Modal helpers
function openModal(el){ if (el) el.classList.add('open'); }
function closeModal(el){ if (el) el.classList.remove('open'); }

// Close warning / logout
document.getElementById('understand')?.addEventListener('click', () => closeModal(multiFaceModal));
document.getElementById('logoutNow')?.addEventListener('click', () => logoutForm?.submit());

// --- Camera + Face Detection ---
const videoEl = document.getElementById('cameraVideo');

async function startCamera(){
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false });
    videoEl.srcObject = stream;
  } catch (e) {
    setStatus('Camera permission denied', false, true);
  }
}

async function waitForMP(){
  // Wait until both globals are defined by CDN scripts
  const maxWaitMs = 5000;
  const started = performance.now();
  while (!(window.FaceDetection && window.Camera)) {
    await new Promise(r => setTimeout(r, 120));
    if (performance.now() - started > maxWaitMs) break;
  }
}

async function runFaceDetection(){
  await waitForMP();
  if (!(window.FaceDetection && window.Camera)) {
    setStatus('Could not load detection library', false, true);
    return;
  }

  const faceDetection = new window.FaceDetection({
    locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/face_detection/${file}`,
  });
  faceDetection.setOptions({ model: 'short', minDetectionConfidence: 0.6 });

  faceDetection.onResults((results) => {
    const n = (results?.detections || []).length;

    if (n === 1) {
      setStatus('1 person detected — you can vote', true, false);
      closeModal(multiFaceModal);
      enableVotes();
    } else if (n > 1) {
      setStatus(`${n} faces detected — voting disabled`, false, true);
      disableVotes();
      openModal(multiFaceModal);
    } else {
      setStatus('No face detected — hold still', false, false);
      disableVotes();
    }
  });

  const camera = new window.Camera(videoEl, {
    onFrame: async () => { await faceDetection.send({ image: videoEl }); },
    width: 640,
    height: 480
  });
  camera.start();
}

startCamera().then(runFaceDetection);

// --- AJAX vote (intercept form submit) ---
voteForms.forEach(form => {
  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const btn = form.querySelector('.vote-btn');
    if (!btn || btn.disabled) return;  // still blocked by face check

    const formData = new FormData(form);

    try{
      const res = await fetch(window.EV_CONFIG.voteUrl, {
        method: 'POST',
        headers: {
          'X-CSRFToken': CSRF,
          'X-Requested-With': 'XMLHttpRequest',
          'Accept': 'application/json'
        },
        body: formData
      });

      if (res.status === 409) {
        // already voted
        alert('You have already voted in this election.');
        window.location.href = window.EV_CONFIG.listUrl;
        return;
      }
      if (!res.ok) throw new Error('Vote failed');

      // success → show modal with animated check, then redirect
      openModal(voteSuccess);
      setTimeout(() => { window.location.href = window.EV_CONFIG.listUrl; }, 1500);
    }catch(err){
      alert('Could not cast vote. Please try again.');
    }
  });
});