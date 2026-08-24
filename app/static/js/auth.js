// index.html/upload.html/dashboard.html 공통 — 구글 로그인(@ajou.ac.kr 전용), 계정
// 상태에 따른 헤더/오버레이 제어(2026-08-21 신설, 2026-08-24 세 페이지 공통 사용으로
// 확장). 로그인 오버레이·startBtn/resumeBtn·drawerMyRoadmapBtn처럼 일부 페이지에만
// 있는 요소는 전부 `?.addEventListener`로 방어해 세 페이지 어디서 로드돼도 에러 없이
// 동작한다. 로그인 상태는 localStorage에 {email, name, email_hash}만 저장한다 —
// 서버 세션·쿠키 없이 프론트에서만 "로그인했다"를 기억하는 가벼운 방식이다(해커톤 데모
// 범위를 벗어나는 실서비스라면 httpOnly 세션 쿠키가 더 안전하다). 구글 ID 토큰 자체는
// /api/auth/verify 검증 한 번에만 쓰고 버리며, 서버는 이메일 원문이 아니라 해시만 저장
// 한다(app/auth.py, app/user_store.py) — 이 프로젝트의 "PII 서버 저장 금지" 원칙을
// 로그인 기능에도 그대로 적용.

const AUTH_KEY = "pathfinder:auth";
let PENDING_AFTER_LOGIN = null; // "upload" | "resume"
// undefined = 아직 /api/config 응답 전. upload.html은 자체적으로 `let CONFIG`(진로/
// 자기신고 옵션)를 이미 쓰고 있어서, 같은 이름을 쓰면 같은 문서 안에서
// "Identifier 'CONFIG' has already been declared" 오류가 난다(2026-08-24 발견) —
// 그래서 이 파일에서만 접두사를 붙였다.
let AUTH_CONFIG;
let GOOGLE_BUTTON_RENDERED = false;

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = String(text);
  return div.innerHTML;
}

function getAuth() {
  try {
    return JSON.parse(localStorage.getItem(AUTH_KEY));
  } catch (_) {
    return null;
  }
}

function setAuth(auth) {
  localStorage.setItem(AUTH_KEY, JSON.stringify(auth));
}

function clearAuth() {
  localStorage.removeItem(AUTH_KEY);
}

function avatarInitial(auth) {
  return (auth.name || auth.email || "?").trim().charAt(0).toUpperCase();
}

// --- 헤더: 로그인 여부에 따라 [로그인] 버튼 / 계정 아이콘 토글 ---
// upload.html/dashboard.html은 로그인 없이도 쓸 수 있다(emailHash 없이 로드맵 저장만
// 건너뜀, app/static/js/upload.js 참고) — 그래서 로그인 안 된 상태여도 리다이렉트하지
// 않고 [로그인] 버튼만 보여준다. 그 페이지들엔 로그인 모달이 없어서, 누르면 로그인
// 모달이 있는 index.html로 이동시킨다.
function renderAuthSlot() {
  const auth = getAuth();
  const slot = document.getElementById("authSlot");
  if (!slot) return;
  if (!auth) {
    slot.innerHTML = `<button class="login-btn-header" id="headerLoginBtn">로그인</button>`;
    document.getElementById("headerLoginBtn").addEventListener("click", () => {
      if (document.getElementById("loginOverlay")) {
        openLoginOverlay(null);
      } else {
        window.location.href = "/index.html";
      }
    });
    return;
  }
  slot.innerHTML = `<button class="account-icon-btn" id="headerAccountBtn" aria-label="계정">${escapeHtml(avatarInitial(auth))}</button>`;
  document.getElementById("headerAccountBtn").addEventListener("click", openDrawer);
}

// --- 오버레이 공통 열기/닫기 (ease 트랜지션은 CSS의 .is-open 토글로 처리) ---
function openOverlay(id) {
  const overlay = document.getElementById(id);
  overlay.hidden = false;
  // hidden 해제와 같은 프레임에 is-open을 붙이면 트랜지션 시작값을 못 잡아 바로
  // 끝난 상태로 튄다 — 다음 프레임에 붙여야 ease-in이 실제로 재생된다.
  requestAnimationFrame(() => requestAnimationFrame(() => overlay.classList.add("is-open")));
}

function closeOverlay(id) {
  const overlay = document.getElementById(id);
  overlay.classList.remove("is-open");
  setTimeout(() => {
    overlay.hidden = true;
  }, 280);
}

// --- 로그인 오버레이 ---
function openLoginOverlay(pendingAction) {
  PENDING_AFTER_LOGIN = pendingAction;
  document.getElementById("loginError").hidden = true;
  openOverlay("loginOverlay");
  ensureGoogleButtonRendered();
}

function closeLoginOverlay() {
  closeOverlay("loginOverlay");
}

function ensureGoogleButtonRendered(attempt = 0) {
  const slot = document.getElementById("googleBtnSlot");
  if (GOOGLE_BUTTON_RENDERED) return;

  // /api/config 응답을 아직 못 받았거나, 구글이 준 gsi/client 스크립트가 아직 로드
  // 중이면(async라 DOMContentLoaded보다 늦게 끝날 수 있음) 잠깐 기다렸다 재시도한다.
  if (AUTH_CONFIG === undefined || typeof google === "undefined" || !google.accounts) {
    if (attempt > 25) {
      slot.innerHTML = `<p class="modal-error">로그인 화면을 불러오지 못했습니다. 새로고침 후 다시 시도해주세요.</p>`;
      return;
    }
    setTimeout(() => ensureGoogleButtonRendered(attempt + 1), 200);
    return;
  }

  if (!AUTH_CONFIG.google_client_id) {
    slot.innerHTML = `<p class="modal-error">구글 로그인이 아직 설정되지 않았습니다. 관리자에게 문의하세요.</p>`;
    return;
  }

  google.accounts.id.initialize({ client_id: AUTH_CONFIG.google_client_id, callback: handleCredentialResponse });
  google.accounts.id.renderButton(slot, {
    theme: "outline", size: "large", text: "signin_with", locale: "ko", width: 300,
  });
  GOOGLE_BUTTON_RENDERED = true;
}

async function handleCredentialResponse(response) {
  const errorEl = document.getElementById("loginError");
  errorEl.hidden = true;
  try {
    const res = await fetch("/api/auth/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential: response.credential }),
    });
    const body = await res.json();
    if (!res.ok) {
      errorEl.textContent = body.detail || "로그인에 실패했습니다. 다시 시도해주세요.";
      errorEl.hidden = false;
      return;
    }
    setAuth(body);
    renderAuthSlot();
    closeLoginOverlay();
    await continueAfterLogin();
  } catch (err) {
    errorEl.textContent = "로그인 확인 중 문제가 발생했습니다. 다시 시도해주세요.";
    errorEl.hidden = false;
  }
}

async function continueAfterLogin() {
  const action = PENDING_AFTER_LOGIN;
  PENDING_AFTER_LOGIN = null;
  if (action === "resume") {
    await goToMyRoadmap();
  } else {
    window.location.href = "/upload.html";
  }
}

// --- [내 로드맵 이어보기] / 드로어 [내 로드맵] 공통 동작 ---
async function goToMyRoadmap() {
  const auth = getAuth();
  if (!auth) {
    openLoginOverlay("resume");
    return;
  }
  try {
    const res = await fetch(`/api/plan/latest/${encodeURIComponent(auth.email_hash)}`);
    if (res.status === 404) {
      alert("아직 진단 기록이 없어요. 먼저 성적표를 올려 로드맵을 만들어보세요.");
      return;
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const body = await res.json();
    sessionStorage.setItem("pathfinder:formState", JSON.stringify(body.form_state));
    sessionStorage.setItem("pathfinder:planResult", JSON.stringify(body.plan));
    window.location.href = "/dashboard.html";
  } catch (err) {
    alert("로드맵을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.");
  }
}

// --- 계정 드로어 ---
function openDrawer() {
  const auth = getAuth();
  if (!auth) return;
  document.getElementById("drawerName").textContent = auth.name || "";
  document.getElementById("drawerEmail").textContent = auth.email || "";
  document.getElementById("drawerAvatar").textContent = avatarInitial(auth);
  openOverlay("drawerOverlay");
}

function closeDrawer() {
  closeOverlay("drawerOverlay");
}

function logout() {
  clearAuth();
  closeDrawer();
  // index.html(startBtn이 있는 유일한 페이지)에서는 제자리에서 헤더만 다시 그리고,
  // upload.html/dashboard.html에서는 index.html로 이동한다(2026-08-24 사용자 요청).
  if (document.getElementById("startBtn")) {
    renderAuthSlot();
  } else {
    window.location.href = "/index.html";
  }
}

// --- 초기화 ---
// index.html에만 있는 요소(startBtn/resumeBtn/loginOverlay 등)는 upload.html/
// dashboard.html에서 로드될 때 존재하지 않으므로 전부 `?.`로 방어한다(2026-08-24).
document.addEventListener("DOMContentLoaded", async () => {
  renderAuthSlot();

  // 구글 로그인 버튼 렌더링에 필요한 /api/config·gsi 스크립트는 로그인 모달이 있는
  // index.html에서만 필요하다.
  if (document.getElementById("loginOverlay")) {
    try {
      const res = await fetch("/api/config");
      AUTH_CONFIG = await res.json();
    } catch (_) {
      AUTH_CONFIG = { google_client_id: "" };
    }
  }

  document.getElementById("startBtn")?.addEventListener("click", () => {
    if (getAuth()) {
      window.location.href = "/upload.html";
    } else {
      openLoginOverlay("upload");
    }
  });

  document.getElementById("resumeBtn")?.addEventListener("click", () => {
    if (getAuth()) {
      goToMyRoadmap();
    } else {
      openLoginOverlay("resume");
    }
  });

  document.getElementById("loginCloseBtn")?.addEventListener("click", closeLoginOverlay);
  document.getElementById("loginOverlay")?.addEventListener("click", (e) => {
    if (e.target.id === "loginOverlay") closeLoginOverlay();
  });

  document.getElementById("drawerCloseBtn")?.addEventListener("click", closeDrawer);
  document.getElementById("drawerOverlay")?.addEventListener("click", (e) => {
    if (e.target.id === "drawerOverlay") closeDrawer();
  });
  document.getElementById("drawerLogoutBtn")?.addEventListener("click", logout);
  document.getElementById("drawerMyRoadmapBtn")?.addEventListener("click", () => {
    closeDrawer();
    goToMyRoadmap();
  });
});
