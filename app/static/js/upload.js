// 화면1 — 3단계 위저드(업로드 → 마스킹 결과 확인 → 진로/자기신고 설정).
// 2026-08-21 전면 개편: 원래는 업로드와 설정이 한 화면에 다 있었는데, Upload.mov 레퍼런스대로
// "한 번에 하나씩" 흐름으로 바꾸고 마스킹 결과를 사용자가 눈으로 확인하는 단계를 넣었다.
// 다음 화면(대시보드)이 쓸 상태는 sessionStorage에 저장해 넘긴다.

const PROJECT_FORM_TYPES = [
  { id: "team", label: "팀" },
  { id: "solo", label: "개인" },
];

let CONFIG = null;
let uploadedCourses = [];
let detectedAdmissionYear = null;

// --- 단계 전환: 나가는 섹션을 위로 페이드아웃 → 들어오는 섹션을 아래에서 페이드인 ---
function goToStep(fromId, toId) {
  const from = document.getElementById(fromId);
  const to = document.getElementById(toId);

  from.classList.add("is-leave");
  setTimeout(() => {
    from.hidden = true;
    from.classList.remove("is-leave");

    to.hidden = false;
    to.classList.add("is-enter");
    // 다음 프레임에 클래스를 떼야 transition이 실제로 재생된다
    // (hidden 해제와 같은 프레임에 떼면 브라우저가 시작값을 못 잡는다).
    requestAnimationFrame(() => requestAnimationFrame(() => to.classList.remove("is-enter")));

    window.scrollTo({ top: 0, behavior: "smooth" });
  }, 380);
}

// ============================================================
// STEP 1 — 업로드 + 진행률
// ============================================================

function setProgress(pct, title, sub) {
  document.getElementById("upBarFill").style.width = `${pct}%`;
  if (title) document.getElementById("upTitle").textContent = title;
  if (sub !== undefined) document.getElementById("upSub").textContent = sub;
}

function showUploadError(message) {
  const box = document.getElementById("upError");
  box.textContent = message;
  box.hidden = false;
  document.getElementById("upBarFill").style.background = "var(--red)";
  document.getElementById("upTitle").textContent = "업로드 실패";
  document.getElementById("upSub").textContent = "다른 파일로 다시 시도해주세요.";
  document.getElementById("dropzone").classList.remove("is-disabled");
}

function resetProgressUi() {
  document.getElementById("uploadProgress").hidden = false;
  document.getElementById("upError").hidden = true;
  document.getElementById("upCheck").hidden = true;
  document.getElementById("upBarFill").style.background = "var(--blue-600)";
  setProgress(0, "업로드 중...", "0%");
}

/**
 * 업로드 구간은 XHR의 실제 진행률(0~40%)을 쓰고, 그 뒤 서버가 마스킹·과목 인식(Gemini 호출)을
 * 하는 동안은 실제 진행률을 알 수 없으므로 40~90%를 시간 기반으로 채운다.
 * 단계 문구는 서버가 실제로 수행하는 순서(마스킹 → 인젝션 검사 → 과목 구조화) 그대로다.
 */
function uploadFile(file) {
  if (!file) return;
  if (file.type !== "application/pdf") {
    resetProgressUi();
    showUploadError("PDF 파일만 업로드할 수 있습니다.");
    return;
  }

  resetProgressUi();
  document.getElementById("dropzone").classList.add("is-disabled");

  const formData = new FormData();
  formData.append("file", file);

  const xhr = new XMLHttpRequest();
  let serverTimer = null;

  xhr.upload.addEventListener("progress", (e) => {
    if (!e.lengthComputable) return;
    const pct = Math.round((e.loaded / e.total) * 40);
    setProgress(pct, "성적표 업로드 중", `${pct}%`);
  });

  // 업로드가 끝나면 서버 처리 구간으로 넘어간다
  xhr.upload.addEventListener("load", () => {
    let pct = 40;
    setProgress(pct, "이름·학번 마스킹 중", "개인정보를 지우고 있습니다");
    serverTimer = setInterval(() => {
      pct = Math.min(90, pct + 2);
      if (pct > 65) {
        setProgress(pct, "과목 인식 중", "마스킹된 본문에서 이수 과목을 읽고 있습니다");
      } else {
        setProgress(pct, "이름·학번 마스킹 중", "개인정보를 지우고 있습니다");
      }
    }, 220);
  });

  xhr.addEventListener("load", () => {
    if (serverTimer) clearInterval(serverTimer);

    let body = {};
    try {
      body = JSON.parse(xhr.responseText);
    } catch (_) {
      showUploadError("서버 응답을 해석하지 못했습니다.");
      return;
    }

    if (xhr.status !== 200) {
      showUploadError(body.detail || "업로드에 실패했습니다.");
      return;
    }

    setProgress(100, "완료", "마스킹 결과를 확인해주세요");
    document.getElementById("upCheck").hidden = false;

    uploadedCourses = body.courses || [];
    detectedAdmissionYear = body.admission_year || null;
    const chip = document.getElementById("admissionYearChip");
    chip.textContent = detectedAdmissionYear
      ? `${detectedAdmissionYear}학번 · 소프트웨어학과`
      : "학번 확인 불가 · 소프트웨어학과"; // 개발 모드(과목 미인식) 등 수강년도를 못 얻은 경우
    renderMaskResult(body);
    setTimeout(() => goToStep("stepUpload", "stepMasked"), 700);
  });

  xhr.addEventListener("error", () => {
    if (serverTimer) clearInterval(serverTimer);
    showUploadError("네트워크 오류로 업로드하지 못했습니다.");
  });

  xhr.open("POST", "/api/upload");
  xhr.send(formData);
}

function setupDropzone() {
  const dz = document.getElementById("dropzone");
  const input = document.getElementById("fileInput");

  dz.addEventListener("click", () => input.click());
  input.addEventListener("change", () => uploadFile(input.files[0]));

  ["dragover", "dragenter"].forEach((evt) =>
    dz.addEventListener(evt, (e) => {
      e.preventDefault();
      dz.classList.add("is-dragover");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dz.addEventListener(evt, (e) => {
      e.preventDefault();
      dz.classList.remove("is-dragover");
    })
  );
  dz.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  });
}

// ============================================================
// STEP 2 — 마스킹 결과
// ============================================================

function renderMaskResult(body) {
  document.getElementById("maskPreview").textContent =
    body.masked_preview || "(표시할 본문이 없습니다)";

  const countEl = document.getElementById("maskCourseCount");
  const courseSection = document.getElementById("courseSection");

  if (body.warning) {
    // API 키가 없어 과목 구조화를 건너뛴 개발 모드 — 없는 결과를 있는 척하지 않는다.
    countEl.textContent = body.warning;
    courseSection.hidden = true;
    return;
  }

  courseSection.hidden = false;
  countEl.textContent = `과목 ${uploadedCourses.length}건 인식`;
  document.getElementById("courseTableBody").innerHTML = uploadedCourses
    .map(
      (c) => `<tr>
        <td>${escapeHtml(c.name ?? "")}</td>
        <td>${c.credit ?? ""}</td>
        <td>${escapeHtml(c.category ?? "")}</td>
      </tr>`
    )
    .join("");
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = String(text);
  return div.innerHTML;
}

// ============================================================
// STEP 3 — 진로 목표 + 자기신고
// ============================================================

async function loadConfig() {
  const res = await fetch("/api/config");
  CONFIG = await res.json();

  const trackSelect = document.getElementById("track");
  trackSelect.innerHTML = CONFIG.tracks
    .map((t) => `<option value="${t.id}">${t.label}</option>`)
    .join("");
  trackSelect.addEventListener("change", updateOverlayField);

  document.getElementById("trackTypeGroup").innerHTML = CONFIG.track_types
    .map(
      (tt, i) => `
      <label>
        <input type="radio" name="trackType" value="${tt}" ${i === 0 ? "checked" : ""} />
        ${tt}
      </label>`
    )
    .join("");

  updateOverlayField();
  addProjectRow();
}

function updateOverlayField() {
  const track = document.getElementById("track").value;
  const overlaySelect = document.getElementById("overlay");
  const isGrad = track === "대학원_연구";

  const options = isGrad ? CONFIG.grad_lab_clusters : CONFIG.domain_overlays;
  document.getElementById("overlayLabel").textContent = isGrad
    ? "관심 연구실 (선택)"
    : "관심 산업 (선택)";
  // 소프트웨어학과는 특별한 관심 산업이 없으면 서비스 IT 기업을 희망하는 게 보통이라
  // 기본값 라벨만 그렇게 보여준다(2026-08-21 사용자 요청) — value=""는 그대로라
  // 실제로 선택 안 한 것과 로직·결과는 완전히 동일하다(domain_overlay: null 그대로 전송).
  overlaySelect.innerHTML =
    `<option value="">${isGrad ? "선택 안 함" : "서비스 IT 기업"}</option>` +
    options.map((name) => `<option value="${name}">${formatOverlayLabel(name)}</option>`).join("");
}

function formatOverlayLabel(name) {
  return name.replace(/_/g, " ").replace(/연구실$/, " 연구실").trim();
}

// --- 어학 연쇄 드롭다운 ---
// 시험 종류 -> (하위 유형) -> 점수/등급. exam id는 graduation_requirements.json의 키와 맞춘다.
const TOEFL_SUBTYPES = [
  { value: "TOEFL_PBT", label: "PBT" },
  { value: "TOEFL_CBT", label: "CBT" },
  { value: "TOEFL_iBT", label: "IBT" },
];
const GTELP_SUBTYPES = [
  { value: "GTELP_Lv2", label: "Level 2" },
  { value: "GTELP_Lv3", label: "Level 3" },
];
// TOEIC Speaking·OPIc 등급(높은 것부터 나열해 고르기 쉽게)
const SPEAKING_GRADES = ["AH", "AM", "AL", "IH", "IM", "IL", "NH", "NM", "NL"];

function setSlot(slotId, visible) {
  document.getElementById(slotId).hidden = !visible;
}

function updateLanguageFields() {
  const exam = document.getElementById("langExam").value;
  const subSelect = document.getElementById("langSub");
  const gradeSelect = document.getElementById("langGrade");
  const note = document.getElementById("langNote");

  setSlot("langSubSlot", false);
  setSlot("langScoreSlot", false);
  setSlot("langGradeSlot", false);
  note.textContent = "";

  if (!exam) return;

  if (exam === "TOEFL" || exam === "GTELP") {
    const subtypes = exam === "TOEFL" ? TOEFL_SUBTYPES : GTELP_SUBTYPES;
    subSelect.innerHTML =
      `<option value="">${exam === "TOEFL" ? "유형" : "등급"} 선택</option>` +
      subtypes.map((s) => `<option value="${s.value}">${s.label}</option>`).join("");
    setSlot("langSubSlot", true);
    // 하위 유형을 고른 뒤에야 점수 칸이 열린다
    setSlot("langScoreSlot", Boolean(subSelect.value));
    return;
  }

  if (exam === "TOEIC_Speaking" || exam === "OPIc") {
    gradeSelect.innerHTML =
      `<option value="">등급 선택</option>` +
      SPEAKING_GRADES.map((g) => `<option value="${g}">${g}</option>`).join("");
    setSlot("langGradeSlot", true);
    note.textContent =
      exam === "TOEIC_Speaking"
        ? "졸업 기준: IM1 이상"
        : "졸업 기준: IL 이상";
    return;
  }

  // TOEIC / TEPS / TEPS_NEW / IELTS / TOEIC_Speaking_OLD — 바로 점수 입력
  setSlot("langScoreSlot", true);
  const NOTES = {
    TOEIC: "졸업 기준: 730점 이상",
    TEPS: "졸업 기준: 605점 이상(구 텝스)",
    TEPS_NEW: "졸업 기준: 329점 이상(뉴텝스)",
    IELTS: "졸업 기준: 5.5점 이상",
    TOEIC_Speaking_OLD: "졸업 기준: Level 5 이상(구버전)",
  };
  note.textContent = NOTES[exam] || "";
}

function collectLanguageScore() {
  const exam = document.getElementById("langExam").value;
  if (!exam) return null;

  if (exam === "TOEIC_Speaking" || exam === "OPIc") {
    const grade = document.getElementById("langGrade").value;
    return grade ? { exam, score: grade } : null;
  }

  const scoreRaw = document.getElementById("langScore").value;
  if (scoreRaw === "") return null;
  const score = Number(scoreRaw);

  if (exam === "TOEFL" || exam === "GTELP") {
    const sub = document.getElementById("langSub").value;
    return sub ? { exam: sub, score } : null;
  }
  return { exam, score };
}

function updateProgCertFields() {
  setSlot("topcitSlot", document.getElementById("progCert").value === "topcit");
}

function collectProgrammingCompetency() {
  const kind = document.getElementById("progCert").value;
  if (!kind) return null;
  if (kind === "topcit") {
    const raw = document.getElementById("topcitScore").value;
    return raw === "" ? null : { topcit_score: Number(raw) };
  }
  if (kind === "apc") return { apc_pass: true };
  if (kind === "contest") return { contest_award: true };
  return null;
}

// --- 개인 활동(프로젝트·동아리·자격증·교내프로그램) ---
// 2026-08-21: 역량 진단이 "과목 하나만 들어도 충족"으로 뜨는 게 너무 낙관적이라는
// 피드백에 따라, 판정 근거를 과목 외에 다양화하려고 활동 유형을 추가했다(app/agents/
// competency.py의 4요소 판정: 수업/실전참여/동아리/자격증).
const ACTIVITY_TYPES = [
  { id: "project", label: "프로젝트" },
  { id: "club", label: "동아리" },
  { id: "certification", label: "자격증" },
  { id: "program", label: "교내 프로그램" },
];

function projectFieldOptionsHtml() {
  return CONFIG.project_fields.map((f) => `<option value="${f.id}">${f.label}</option>`).join("");
}

function addProjectRow() {
  const container = document.getElementById("projectRows");
  const row = document.createElement("div");
  row.className = "project-row";
  row.innerHTML = `
    <select class="proj-activity-type">
      ${ACTIVITY_TYPES.map((t) => `<option value="${t.id}">${t.label}</option>`).join("")}
    </select>
    <input type="text" placeholder="제목 (예: 배달앱 클론 코딩, 정보처리기사)" class="proj-title" />
    <select class="proj-field">${projectFieldOptionsHtml()}</select>
    <select class="proj-type">
      ${PROJECT_FORM_TYPES.map((t) => `<option value="${t.id}">${t.label}</option>`).join("")}
    </select>
    <button type="button" class="remove" aria-label="삭제">×</button>
  `;
  row.querySelector(".remove").addEventListener("click", () => row.remove());
  container.appendChild(row);
}

function collectProjects() {
  return Array.from(document.querySelectorAll(".project-row"))
    .map((row) => ({
      title: row.querySelector(".proj-title").value.trim(),
      field: row.querySelector(".proj-field").value,
      is_team: row.querySelector(".proj-type").value === "team",
      activity_type: row.querySelector(".proj-activity-type").value,
    }))
    .filter((p) => p.title.length > 0);
}

// --- 제출 ---
async function handleSubmit(e) {
  e.preventDefault();
  const submitBtn = document.getElementById("submitBtn");
  submitBtn.disabled = true;
  submitBtn.textContent = "분석 중...";
  // 졸업판정+역량진단+추천(Gemini 사유 생성 포함)까지 한 번에 계산해 최대 1분 가까이
  // 걸린다 — 화면이 멈춘 것처럼 보이지 않게 전체 화면 오버레이로 진행 중임을 알린다.
  document.getElementById("loadingOverlay").hidden = false;

  const track = document.getElementById("track").value;
  const overlayValue = document.getElementById("overlay").value || null;
  const isGrad = track === "대학원_연구";

  // 로그인한 계정이면 email_hash를 같이 보내 서버가 "가장 최근 로드맵"으로 자동
  // 저장하게 한다(2026-08-21) — index.html의 [내 로드맵 이어보기]/계정 드로어가
  // 이 값을 그대로 다시 불러온다. 로그인 안 했으면 undefined라 그냥 저장을 건너뛴다.
  let emailHash;
  try {
    const auth = JSON.parse(localStorage.getItem("pathfinder:auth"));
    emailHash = auth ? auth.email_hash : undefined;
  } catch (_) {
    emailHash = undefined;
  }

  const payload = {
    courses: uploadedCourses,
    admission_year: CONFIG.admission_year,
    track_type: document.querySelector('input[name="trackType"]:checked').value,
    track: track,
    domain_overlay: isGrad ? null : overlayValue,
    grad_lab_cluster: isGrad ? overlayValue : null,
    projects: collectProjects(),
    language_score: collectLanguageScore(),
    programming_competency: collectProgrammingCompetency(),
    email_hash: emailHash,
  };

  try {
    const res = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const result = await res.json();

    // 서버가 성적표의 수강년도로 실제 판정에 쓴 입학년도를 되돌려준다 — 화면1에서
    // 보낸 admission_year(기본값 2025)는 폴백일 뿐이라, 응답값으로 덮어써야
    // 대시보드의 "OOOO학년도 학사요람" 표시와 자기신고 재판정이 정확해진다
    // (2026-08-22, 21~26학번 확장).
    if (result.admission_year) {
      payload.admission_year = result.admission_year;
    }

    sessionStorage.setItem("pathfinder:formState", JSON.stringify(payload));
    sessionStorage.setItem("pathfinder:planResult", JSON.stringify(result));
    window.location.href = "dashboard.html"; // 페이지 이동으로 오버레이도 자연히 사라짐
  } catch (err) {
    document.getElementById("loadingOverlay").hidden = true;
    submitBtn.disabled = false;
    submitBtn.textContent = "로드맵 만들기";
    alert("로드맵 생성에 실패했습니다. 잠시 후 다시 시도해주세요.");
  }
}

// ============================================================
document.addEventListener("DOMContentLoaded", () => {
  loadConfig();
  setupDropzone();

  document.getElementById("reuploadBtn").addEventListener("click", () => {
    document.getElementById("uploadProgress").hidden = true;
    document.getElementById("dropzone").classList.remove("is-disabled");
    document.getElementById("fileInput").value = "";
    goToStep("stepMasked", "stepUpload");
  });
  document.getElementById("confirmMaskBtn").addEventListener("click", () => {
    goToStep("stepMasked", "stepSettings");
  });

  document.getElementById("langExam").addEventListener("change", updateLanguageFields);
  document.getElementById("langSub").addEventListener("change", () => {
    setSlot("langScoreSlot", Boolean(document.getElementById("langSub").value));
  });
  document.getElementById("progCert").addEventListener("change", updateProgCertFields);

  document.getElementById("addProjectRow").addEventListener("click", addProjectRow);
  document.getElementById("planForm").addEventListener("submit", handleSubmit);
});
