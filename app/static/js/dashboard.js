// 화면2·3·4 통합 대시보드. Design Reference 3번 이미지 구조(현황+역량진단 / 로드맵 / 상담을
// 페이지 이동 없이 한 화면에)를 따른다. docs/plans Task 5-2~5-4.

let PLAN = null;
let FORM_STATE = null;
let CHAT_HISTORY = [];

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = String(text);
  return div.innerHTML;
}

function loadState() {
  const planRaw = sessionStorage.getItem("pathfinder:planResult");
  const formRaw = sessionStorage.getItem("pathfinder:formState");
  if (!planRaw || !formRaw) {
    window.location.href = "upload.html";
    return false;
  }
  PLAN = JSON.parse(planRaw);
  FORM_STATE = JSON.parse(formRaw);
  return true;
}

// --- 학기 라벨: admission_year + "grade-semester" -> "2026-2" 식 달력 표기 ---
function termSortKey(term) {
  const [grade, sem] = term.split("-").map(Number);
  return grade * 10 + sem;
}
function calendarLabel(term, admissionYear) {
  const [grade, sem] = term.split("-").map(Number);
  const year = admissionYear + (grade - 1);
  return `${year}-${sem}`;
}

// --- 헤더 ---
// 화면1 드롭다운의 기본 라벨 표기와 맞춘다("서비스 IT 기업"/"선택 안 함", upload.js
// updateOverlayField()와 동일 규칙) — 관심 산업을 실제로 고르지 않았어도 화면1에
// 보였던 기본 라벨 그대로 헤더에 노출한다(2026-08-21 요청).
function currentOverlayLabel() {
  const isGrad = FORM_STATE.track === "대학원_연구";
  const value = isGrad ? FORM_STATE.grad_lab_cluster : FORM_STATE.domain_overlay;
  if (!value) return isGrad ? "선택 안 함" : "서비스 IT 기업";
  return value.replace(/_/g, " ").replace(/연구실$/, " 연구실").trim();
}

function renderHeader() {
  document.getElementById("headerContext").textContent =
    `${FORM_STATE.admission_year}학번 소프트웨어학과 · ${FORM_STATE.track} · ${currentOverlayLabel()}`;
}

// --- 졸업 현황 ---
function statusDotClass(kind) {
  return { ok: "ok", warn: "warn", bad: "bad", unknown: "unknown" }[kind] || "unknown";
}

function renderCreditCard() {
  const a = PLAN.audit;
  const req = PLAN.requirements_summary;
  const pct = Math.min(100, Math.round((a.total_credit_earned / req.total_credit_required) * 100));

  const items = [];

  const missingCount = a.missing_required_major_courses.length;
  const majorOk = a.required_major_completed;
  items.push({
    kind: majorOk ? "ok" : "warn",
    name: "전공필수",
    value: `${req.required_major_course_count - missingCount}/${req.required_major_course_count}개 이수`,
    detail: majorOk ? null : `미이수: ${a.missing_required_major_courses.join(", ")}`,
  });

  items.push({
    kind: a.elective_major_certified ? "ok" : "warn",
    name: "전공선택",
    value: `${a.elective_major_credit_earned}/${req.elective_major_credit_required}학점`,
    // 현장실습 학점 상한은 학번마다 다르다(21·22학번은 상한 없음, 23·24학번은
    // 12학점, 25·26학번은 6학점) — 하드코딩하지 않고 요청 시점 요람 기준값을
    // 그대로 쓴다(2026-08-22).
    detail:
      a.elective_major_certified || req.elective_fieldwork_cap_credit == null
        ? null
        : `현장실습군은 최대 ${req.elective_fieldwork_cap_credit}학점까지만 인정됩니다.`,
  });

  if (req.major_foundation_credit_required !== undefined) {
    items.push({
      kind: a.major_foundation_certified ? "ok" : "warn",
      name: "전공기초",
      value: `${a.major_foundation_credit_earned}/${req.major_foundation_credit_required}학점`,
      detail: null,
    });
  }

  items.push({
    kind: a.industry_project_certified ? "ok" : "warn",
    name: "산학프로젝트 인증",
    value: `${a.industry_project_count}/${req.industry_project_min_courses}과목`,
    detail: null,
  });

  if (a.programming_competency_certified !== null || a.unresolved.includes("programming_competency")) {
    items.push({
      kind: a.programming_competency_certified === true ? "ok"
        : a.programming_competency_certified === false ? "bad" : "unknown",
      name: "프로그래밍 역량 인증",
      value: "TOPCIT 190점 이상",
      selfReportReason: a.unresolved.includes("programming_competency") ? "programming_competency" : null,
    });
  }

  // 사용자가 화면1에서 어학 성적을 직접 신고했으면 그 시험을 그대로 보여준다 —
  // 예전엔 TOEIC 기준만 고정 표시해서 TOEIC Speaking을 신고해도 "TOEIC 730점 이상"이라
  // 떠 무슨 근거로 판정됐는지 알 수 없었다(2026-08-21 수정).
  const reported = FORM_STATE.language_score;
  items.push({
    kind: a.language_ok === true ? "ok" : a.language_ok === false ? "bad" : "unknown",
    name: "어학요건",
    value: reported
      ? `${reported.exam.replace(/_/g, " ")} ${reported.score}`
      : `TOEIC ${req.language_requirement.TOEIC}점 이상`,
    selfReportReason: a.unresolved.includes("language_requirement") ? "language_requirement" : null,
  });

  if (a.unresolved.includes("double_major_or_minor_out_of_scope")) {
    items.push({
      kind: "unknown",
      name: "복수전공/부전공",
      value: "서비스 범위 밖",
      detail: "일반·복수과정은 학사팀에 직접 문의하세요.",
    });
  }

  const citationByItem = Object.fromEntries((PLAN.citations || []).map((c) => [c.item, c.citation]));

  document.getElementById("creditCard").innerHTML = `
    <p class="card-subtitle">${FORM_STATE.admission_year}학년도 학사요람 · ${FORM_STATE.track_type}</p>
    <div class="credit-big">${a.total_credit_earned}<span class="of"> / ${req.total_credit_required}</span></div>
    <div class="progress-bar"><div style="width:${pct}%"></div></div>
    <div class="remaining-terms">남은 학기 ${Object.keys(PLAN.roadmap.schedule).length}학기</div>
    <ul class="req-list">
      ${items
        .map((it) => {
          const citations = it.name === "전공필수" && !majorOk
            ? renderCitations(a.missing_required_major_courses, citationByItem)
            : "";
          // "챗봇에서 알려주세요" 대신 이 카드 안에서 바로 입력할 수 있는 링크(2026-08-21
          // 사용자 요청) — 챗봇은 더 이상 이 두 항목을 먼저 묻지 않는다.
          const addLink = it.selfReportReason
            ? `<div class="req-detail"><a href="#" class="add-selfreport-link" data-reason="${it.selfReportReason}">+ 추가하기</a></div>
               <div class="selfreport-slot" data-reason-slot="${it.selfReportReason}" hidden></div>`
            : "";
          return `
        <li>
          <span class="req-dot ${statusDotClass(it.kind)}"></span>
          <div style="flex:1">
            <span class="req-name">${it.name}</span>
            ${it.detail ? `<div class="req-detail">${it.detail}${citations}</div>` : ""}
            ${addLink}
          </div>
          <span class="req-value">${it.value}</span>
        </li>`;
        })
        .join("")}
    </ul>
  `;
}

function renderCitations(missingNames, citationByItem) {
  // 미이수 과목이 9개여도 전공필수 조항은 하나라 같은 근거가 9번 반복된다 — 중복을 제거하고
  // 접힌 상태로 보여준다. 이전엔 과목마다 조항 전문을 그대로 펼쳐 왼쪽 칸이 화면 몇 배
  // 길이로 늘어나 레이더 차트가 한참 아래로 밀렸다(2026-08-21 실제 화면에서 발견).
  const unique = [...new Set(missingNames.map((n) => citationByItem[n]).filter(Boolean))];
  if (unique.length === 0) return "";
  return unique
    .map(
      (text) =>
        `<details class="citation-details"><summary>요람 근거 보기</summary><p>${text}</p></details>`
    )
    .join("");
}

// --- 졸업 현황 카드의 "+ 추가하기" 인라인 자기신고 폼 ---
// 챗봇을 거치지 않고 화면1의 어학/프로그래밍 역량 드롭다운과 같은 입력을 카드 안에서
// 바로 받는다(2026-08-21 요청). 카드는 renderCreditCard()가 통째로 다시 그리므로,
// 클릭·변경 리스너는 #creditCard 컨테이너 자체에 한 번만 위임 바인딩해야 매번 살아있다.
const SR_TOEFL_SUBTYPES = [
  { value: "TOEFL_PBT", label: "PBT" },
  { value: "TOEFL_CBT", label: "CBT" },
  { value: "TOEFL_iBT", label: "IBT" },
];
const SR_GTELP_SUBTYPES = [
  { value: "GTELP_Lv2", label: "Level 2" },
  { value: "GTELP_Lv3", label: "Level 3" },
];
// (NEW) TOEIC Speaking과 OPIc은 등급 체계가 다르다(2026-08-22 사용자 지시) — OPIc은
// AH/AM 등급이 없다. IM은 세부적으로 IM1~IM3로 나뉘어 성적표에 그대로 찍힌다.
const SR_TOEIC_SPEAKING_NEW_GRADES = ["AH", "AM", "AL", "IH", "IM3", "IM2", "IM1", "IL", "NH", "NM", "NL"];
const SR_OPIC_GRADES = ["AL", "IH", "IM3", "IM2", "IM1", "IL", "NH", "NM", "NL"];

function buildLanguageSelfReportForm() {
  return `<div class="selfreport-form">
    <select class="sr-lang-exam">
      <option value="">시험 선택</option>
      <option value="TOEIC">TOEIC</option>
      <option value="TEPS">TEPS</option>
      <option value="TEPS_NEW">(NEW) TEPS</option>
      <option value="TOEFL">TOEFL</option>
      <option value="GTELP">G-TELP</option>
      <option value="IELTS">IELTS</option>
      <option value="TOEIC_Speaking_OLD">TOEIC Speaking</option>
      <option value="TOEIC_Speaking">(NEW) TOEIC Speaking</option>
      <option value="OPIc">OPIc</option>
    </select>
    <span class="sr-lang-sub-slot" hidden><select class="sr-lang-sub"></select></span>
    <span class="sr-lang-score-slot" hidden><input type="number" class="sr-lang-score" placeholder="점수 입력" min="0" /></span>
    <span class="sr-lang-grade-slot" hidden><select class="sr-lang-grade"></select></span>
    <button type="button" class="sr-submit-btn" data-reason="language_requirement">확인</button>
    <div class="sr-error" hidden></div>
  </div>`;
}

function buildProgrammingSelfReportForm() {
  return `<div class="selfreport-form">
    <select class="sr-prog-cert">
      <option value="">인증 종류 선택</option>
      <option value="topcit">TOPCIT 점수</option>
      <option value="apc">APC 대회 1문제 이상 정답</option>
      <option value="contest">SW 관련 전국대회 입상</option>
    </select>
    <span class="sr-prog-topcit-slot" hidden><input type="number" class="sr-prog-topcit" placeholder="TOPCIT 점수" min="0" /></span>
    <button type="button" class="sr-submit-btn" data-reason="programming_competency">확인</button>
    <div class="sr-error" hidden></div>
  </div>`;
}

function updateSrLanguageFields(formEl) {
  const exam = formEl.querySelector(".sr-lang-exam").value;
  const subSlot = formEl.querySelector(".sr-lang-sub-slot");
  const scoreSlot = formEl.querySelector(".sr-lang-score-slot");
  const gradeSlot = formEl.querySelector(".sr-lang-grade-slot");
  subSlot.hidden = true;
  scoreSlot.hidden = true;
  gradeSlot.hidden = true;
  if (!exam) return;

  if (exam === "TOEFL" || exam === "GTELP") {
    const subtypes = exam === "TOEFL" ? SR_TOEFL_SUBTYPES : SR_GTELP_SUBTYPES;
    const subSelect = formEl.querySelector(".sr-lang-sub");
    subSelect.innerHTML =
      `<option value="">${exam === "TOEFL" ? "유형" : "등급"} 선택</option>` +
      subtypes.map((s) => `<option value="${s.value}">${s.label}</option>`).join("");
    subSlot.hidden = false;
    // 유형·점수를 함께 보여준다 — 유형 선택 후 별도로 다시 채워지길 기다리면
    // 아래 change 리스너가 exam 변경 시에만 이 함수를 부르므로 점수 칸이 영영
    // 안 나타난다(2026-08-22 버그 수정: 예전엔 sub-select의 change에도 이 함수가
    // 다시 걸려 있어서, 유형을 고르자마자 옵션이 재생성되며 선택이 즉시 초기화됐다).
    scoreSlot.hidden = false;
    return;
  }

  if (exam === "TOEIC_Speaking" || exam === "OPIc") {
    const grades = exam === "TOEIC_Speaking" ? SR_TOEIC_SPEAKING_NEW_GRADES : SR_OPIC_GRADES;
    const gradeSelect = formEl.querySelector(".sr-lang-grade");
    gradeSelect.innerHTML =
      `<option value="">등급 선택</option>` +
      grades.map((g) => `<option value="${g}">${g}</option>`).join("");
    gradeSlot.hidden = false;
    return;
  }

  scoreSlot.hidden = false;
}

function collectSrLanguageScore(formEl) {
  const exam = formEl.querySelector(".sr-lang-exam").value;
  if (!exam) return null;

  if (exam === "TOEIC_Speaking" || exam === "OPIc") {
    const grade = formEl.querySelector(".sr-lang-grade").value;
    return grade ? { exam, score: grade } : null;
  }

  if (exam === "TOEFL" || exam === "GTELP") {
    const sub = formEl.querySelector(".sr-lang-sub").value;
    const scoreRaw = formEl.querySelector(".sr-lang-score").value;
    if (!sub || scoreRaw === "") return null;
    return { exam: sub, score: Number(scoreRaw) };
  }

  const scoreRaw = formEl.querySelector(".sr-lang-score").value;
  return scoreRaw === "" ? null : { exam, score: Number(scoreRaw) };
}

function collectSrProgrammingCompetency(formEl) {
  const kind = formEl.querySelector(".sr-prog-cert").value;
  if (!kind) return null;
  if (kind === "topcit") {
    const raw = formEl.querySelector(".sr-prog-topcit").value;
    return raw === "" ? null : { topcit_score: Number(raw) };
  }
  if (kind === "apc") return { apc_pass: true };
  if (kind === "contest") return { contest_award: true };
  return null;
}

async function submitSelfReport(reason, formEl) {
  const errEl = formEl.querySelector(".sr-error");
  errEl.hidden = true;

  const payload = { audit: PLAN.audit, admission_year: FORM_STATE.admission_year };
  if (reason === "language_requirement") {
    const value = collectSrLanguageScore(formEl);
    if (!value) {
      errEl.textContent = "값을 입력해주세요.";
      errEl.hidden = false;
      return;
    }
    payload.language_score = value;
  } else {
    const value = collectSrProgrammingCompetency(formEl);
    if (!value) {
      errEl.textContent = "값을 입력해주세요.";
      errEl.hidden = false;
      return;
    }
    payload.programming_competency = value;
  }

  const btn = formEl.querySelector(".sr-submit-btn");
  btn.disabled = true;
  btn.textContent = "확인 중...";

  try {
    const res = await fetch("/api/audit/selfreport", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const updatedAudit = await res.json();

    PLAN.audit = updatedAudit;
    if (reason === "language_requirement") {
      FORM_STATE.language_score = payload.language_score;
    } else {
      FORM_STATE.programming_competency = payload.programming_competency;
    }
    // 새로고침해도 방금 입력한 값이 사라지지 않도록 즉시 다시 저장한다(2026-08-21 요청).
    sessionStorage.setItem("pathfinder:planResult", JSON.stringify(PLAN));
    sessionStorage.setItem("pathfinder:formState", JSON.stringify(FORM_STATE));

    renderCreditCard();
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "확인";
    errEl.textContent = "반영하지 못했습니다. 잠시 후 다시 시도해주세요.";
    errEl.hidden = false;
  }
}

function setupSelfReportDelegation() {
  const card = document.getElementById("creditCard");

  card.addEventListener("click", (e) => {
    const link = e.target.closest(".add-selfreport-link");
    if (link) {
      e.preventDefault();
      const reason = link.dataset.reason;
      const slot = card.querySelector(`.selfreport-slot[data-reason-slot="${reason}"]`);
      if (slot.hidden) {
        slot.innerHTML =
          reason === "language_requirement" ? buildLanguageSelfReportForm() : buildProgrammingSelfReportForm();
        slot.hidden = false;
        link.textContent = "닫기";
      } else {
        slot.hidden = true;
        slot.innerHTML = "";
        link.textContent = "+ 추가하기";
      }
      return;
    }

    const submitBtn = e.target.closest(".sr-submit-btn");
    if (submitBtn) {
      e.preventDefault();
      submitSelfReport(submitBtn.dataset.reason, submitBtn.closest(".selfreport-form"));
    }
  });

  card.addEventListener("change", (e) => {
    // exam(시험 종류) 변경에만 반응한다 — sub(유형/등급) 변경에도 반응하면 이
    // 함수가 sub-select의 옵션 목록을 다시 그리면서 방금 고른 값이 바로
    // 초기화된다(2026-08-22 버그: "유형 선택이 안 되는 것처럼 보임").
    if (e.target.matches(".sr-lang-exam")) {
      updateSrLanguageFields(e.target.closest(".selfreport-form"));
    }
    if (e.target.matches(".sr-prog-cert")) {
      const formEl = e.target.closest(".selfreport-form");
      formEl.querySelector(".sr-prog-topcit-slot").hidden = e.target.value !== "topcit";
    }
  });
}

// --- 역량 레이더 (SVG) ---
// 2026-08-21 최초 설계, 2026-08-22 점수 체계 재설계(사용자 요청). 예전엔 과목 1개만
// 태깅돼도 그 축이 "충족"으로 뜨는 게 너무 낙관적이라는 지적을 받았다 — 백엔드가
// 수업 이수율(0~1)·자격증(1개당 0.5점)·실전참여[프로젝트·교내프로그램](1회당 0.5점)·
// 수상 경력(1회당 1점)을 합산한 점수로 5단계(매우만족~매우부족)를 판정해
// 내려주므로(competency_levels), 레이더의 "현재" 선도 연속 비율이 아니라 이 점수를
// "매우 만족" 문턱값(2.5)으로 정규화해 그린다 — 과목 하나로 육각형이 꽉 차 보이던
// 문제의 근본 해결. "동아리"는 역량 근거로 부적절하다는 판단에 따라 뺐다.

const RADAR_AXIS_COUNT = 6;
const RADAR_SCORE_CAP = 2.5; // "매우 만족" 문턱값 — 이 이상이면 레이더가 꽉 찬다

const LEVEL_COLOR = {
  "매우 만족": "#0f6e42",
  "만족": "#1e8e5a",
  "보통": "#b8860b",
  "부족": "#d9822b",
  "매우 부족": "#d33f3f",
};
const FACTOR_LABELS = { course: "수업", activity: "실전 참여", certification: "자격증", award: "수상 경력" };

function buildRadarAxes() {
  const target = PLAN.competency_target || {};
  const levels = PLAN.competency_levels || {};

  return Object.keys(target)
    .filter((id) => target[id] > 0 && levels[id])
    .map((id) => ({
      id,
      label: id.replace(/_/g, "·"),
      target: target[id],
      level: levels[id].level,
      score: levels[id].score,
      factors: levels[id].factors,
    }))
    .sort((a, b) => b.target - a.target)
    .slice(0, RADAR_AXIS_COUNT);
}

function polarPoint(cx, cy, r, angle) {
  return [
    +(cx + r * Math.sin(angle)).toFixed(2),
    +(cy - r * Math.cos(angle)).toFixed(2),
  ];
}

function renderRadarSvg(axes) {
  const n = axes.length;
  if (n === 0) {
    return "<p class='card-subtitle'>이 진로에 설정된 역량 목표가 없습니다.</p>";
  }

  // 라벨(최대 8글자 한글 ≈ 70px)이 양옆으로 뻗으므로 뷰박스를 넉넉히 잡는다
  const W = 340, H = 250, cx = W / 2, cy = 118, maxR = 70;
  const angleOf = (i) => (i / n) * 2 * Math.PI;
  const toPath = (pts) => pts.map((p) => p.join(",")).join(" ");

  // 배경 격자(4단계 = 0/4~4/4)와 축 스포크 — 없으면 다각형이 그냥 덩어리로 보인다
  const rings = [0.25, 0.5, 0.75, 1]
    .map((ratio) => {
      const pts = axes.map((_, i) => polarPoint(cx, cy, maxR * ratio, angleOf(i)));
      return `<polygon points="${toPath(pts)}" fill="none" stroke="#eceff5" stroke-width="1" />`;
    })
    .join("");

  const spokes = axes
    .map((_, i) => {
      const [x, y] = polarPoint(cx, cy, maxR, angleOf(i));
      return `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="#eceff5" stroke-width="1" />`;
    })
    .join("");

  const targetPts = axes.map((_, i) => polarPoint(cx, cy, maxR, angleOf(i)));
  // "현재" 선은 점수를 "매우 만족" 문턱값(2.5)으로 정규화해 그린다 — 연속 수치가
  // 아니라 5단계 판정과 완전히 같은 기준이어야 육각형과 목록이 안 어긋난다. 2.5를
  // 넘겨도(고득점) 육각형이 문턱을 넘어가지 않게 1로 클램프한다.
  const currentPts = axes.map((a, i) =>
    polarPoint(cx, cy, maxR * Math.min(1, a.score / RADAR_SCORE_CAP), angleOf(i))
  );

  const labels = axes
    .map((a, i) => {
      const angle = angleOf(i);
      const [x, y] = polarPoint(cx, cy, maxR + 16, angle);
      const sin = Math.sin(angle);
      const anchor = sin > 0.25 ? "start" : sin < -0.25 ? "end" : "middle";
      return `<text x="${x}" y="${y + 3}" font-size="10" font-weight="600"
        fill="${LEVEL_COLOR[a.level] || "#6b7280"}" text-anchor="${anchor}">${a.label}</text>`;
    })
    .join("");

  return `
    <svg width="100%" height="${H}" viewBox="0 0 ${W} ${H}" role="img"
         aria-label="역량 레이더 차트">
      ${rings}${spokes}
      <polygon points="${toPath(targetPts)}" fill="none" stroke="#9aa6bf"
               stroke-width="1.2" stroke-dasharray="4,3" />
      <polygon points="${toPath(currentPts)}" fill="rgba(47,95,218,0.22)"
               stroke="#2f5fda" stroke-width="2" stroke-linejoin="round" />
      ${labels}
    </svg>
  `;
}

// "전부 충족"이 근거 없이 뜬다는 지적(2026-08-21) — 축마다 근거가 무엇이고 없는지,
// 실제로 어떤 과목·활동 때문인지를 접힌 목록으로 확인할 수 있게 한다.
// 2026-08-22: 실전참여·자격증·수상 경력이 O/X에서 "개수당 점수"로 바뀌어 칩도 그에
// 맞춰 개수·점수를 함께 보여준다(백엔드 app/agents/competency.py의 배점과 반드시
// 같은 수치를 써야 한다 — 자격증·실전참여 0.5점/개, 수상 경력 1점/회).
const FACTOR_POINTS_PER_UNIT = { activity: 0.5, certification: 0.5, award: 1 };

function renderEvidenceDetails(items, factors) {
  // course 요소는 "커리큘럼상 지금 들을 수 있는 관련 전공필수 이수율"(0~1 비율) —
  // 2026-08-21 사용자 피드백: 과목 개수만으로 O/X를 가르는 게 너무 거칠다고 지적받아,
  // 요람 권장 학기·학년 기준 이수율로 바꿨다.
  const factorRow = Object.entries(factors || {})
    .map(([key, val]) => {
      if (key === "course") {
        const pct = Math.round(val * 100);
        return `<span class="factor-chip ${val >= 0.99 ? "on" : ""}">📘 수업 이수율 ${pct}%</span>`;
      }
      const points = val * FACTOR_POINTS_PER_UNIT[key];
      const unit = key === "award" ? "회" : key === "activity" ? "회" : "개";
      return `<span class="factor-chip ${val > 0 ? "on" : ""}">${FACTOR_LABELS[key]} ${val}${unit} (${points}점)</span>`;
    })
    .join("");

  if (!items || items.length === 0) {
    return `<div class="evidence-empty">${factorRow}<div>근거 없음 — 이 역량에 기여한 과목·활동이 아직 없습니다</div></div>`;
  }
  const typeLabel = { course: "과목", project: "프로젝트", award: "수상 경력", certification: "자격증", program: "프로그램" };
  const rows = items
    .map((e) => `<li><span class="evidence-badge ${e.type}">${typeLabel[e.type] || e.type}</span>${escapeHtml(e.name)}</li>`)
    .join("");
  return `<details class="citation-details evidence-details">
    <summary>근거 ${items.length}건 보기</summary>
    <div class="factor-row">${factorRow}</div>
    <ul class="evidence-list">${rows}</ul>
  </details>`;
}

function renderCompetencyCard() {
  const axes = buildRadarAxes();
  const evidenceMap = PLAN.competency_evidence || {};

  // 낮은 단계(매우부족)부터 보여준다 — 손 봐야 할 것부터 눈에 띄어야 한다
  const gapRows = axes
    .slice()
    .sort((a, b) => a.score - b.score)
    .map((a) => {
      const color = LEVEL_COLOR[a.level] || "#6b7280";
      return `
      <div class="gap-row">
        <div class="gap-label"><span>${a.label}</span><span style="color:${color};font-weight:700">${a.level}</span></div>
        <div class="gap-bar">
          <div style="width:${Math.min(100, (a.score / RADAR_SCORE_CAP) * 100)}%;background:${color}"></div>
        </div>
        ${renderEvidenceDetails(evidenceMap[a.id], a.factors)}
      </div>`;
    })
    .join("");

  const weakCount = axes.filter((a) => a.level === "부족" || a.level === "매우 부족").length;
  const summary =
    weakCount === 0
      ? "표시된 역량 대부분이 다양한 근거로 뒷받침되고 있습니다."
      : `보완이 필요한(부족·매우 부족) 역량이 ${weakCount}개 있습니다.`;

  document.getElementById("competencyCard").innerHTML = `
    <p class="card-title">역량 진단</p>
    <p class="card-subtitle">${summary} 과목·프로젝트·자격증·수상 경력을 종합해 판정합니다.</p>
    <div class="radar-legend">
      <span><span class="legend-swatch" style="background:#2f5fda"></span>현재(수업·실전참여·자격증·수상 경력 종합 점수)</span>
      <span><span class="legend-swatch" style="background:transparent;border:1px dashed #9aa6bf"></span>목표 트랙</span>
    </div>
    <div style="text-align:center">${renderRadarSvg(axes)}</div>
    <div class="gap-list">${gapRows}</div>
  `;
}

// --- 로드맵 ---
function itemCardHtml(item, kind) {
  if (kind === "course") {
    return `
      <div class="item-card">
        <div class="item-card-top">
          <span class="item-badge course">교과</span>
          <span class="item-name">${item.name}</span>
          <span class="item-meta">${item.category || ""} ${item.credit ?? ""}</span>
        </div>
        <div class="item-reason">${item.reason}</div>
      </div>`;
  }
  const deadline = item.apply_period ? item.apply_period.split("~")[1]?.trim() : "";
  const urlLink = item.url ? `<a href="${item.url}" target="_blank" rel="noopener">원문 보기 ↗</a>` : "";
  // 우리 프로그램 데이터는 특정 연도 한 시점 스냅샷이라, 미래 학기에 배치된 항목은
  // "그 해 그 시기에 실제로 열린다"가 아니라 "이맘때 이런 프로그램이 있었다"는 참고
  // 사례다(2026-08-21 사용자 요청 — 개설 여부 확인이 필요하다는 걸 명시해달라).
  const precedentNote = item.is_precedent
    ? `<div class="item-precedent">📌 과거에 이맘때 있었던 프로그램입니다 — 이번에도 열리는지는 아주허브에서 확인하세요</div>`
    : "";
  return `
    <div class="item-card">
      <div class="item-card-top">
        <span class="item-badge program">비교과</span>
        <span class="item-name">${item.name}</span>
      </div>
      <div class="item-sub">${item.org || ""}${deadline ? " · 신청 ~" + deadline : ""}</div>
      <div class="item-reason">${item.reason}</div>
      ${precedentNote}
      ${urlLink ? `<div style="margin-top:6px">${urlLink}</div>` : ""}
    </div>`;
}

function renderRoadmapCard() {
  const schedule = PLAN.roadmap.schedule;
  const warnings = PLAN.roadmap.warnings || [];
  const terms = Object.keys(schedule).sort((a, b) => termSortKey(a) - termSortKey(b));

  const warningHtml = warnings.length
    ? `<div class="warning-banner">⚠️ ${warnings.join("<br />⚠️ ")}</div>`
    : "";

  // 학기 블록을 좌(이수 과목)/우(교내 프로그램) 2열로 나눈다 — 예전엔 프로그램만
  // 세로로 쭉 나열돼 있어 "왜 과목은 안 알려주냐"는 지적을 받았다(2026-08-21).
  const termsHtml = terms
    .map((term, idx) => {
      const items = schedule[term];
      const totalCredit = items.courses.reduce((s, c) => s + (c.credit || 0), 0);
      const label =
        idx === 0 ? "이번 학기" : idx === terms.length - 1 ? "마지막 학기" : "다음 학기";
      const courseCol = items.courses.length
        ? items.courses.map((c) => itemCardHtml(c, "course")).join("")
        : '<p class="term-col-empty">추천할 과목이 없습니다.</p>';
      const programCol = items.programs.length
        ? items.programs.map((p) => itemCardHtml(p, "program")).join("")
        : '<p class="term-col-empty">추천할 프로그램이 없습니다.</p>';
      return `
        <div class="term-block">
          <div class="term-block-head">
            <span class="term-dot ${idx === 0 ? "current" : ""}"></span>
            <span class="term-label">${calendarLabel(term, FORM_STATE.admission_year)}</span>
            <span class="term-sub">${label}</span>
            <span class="term-credit">${totalCredit}학점</span>
          </div>
          <div class="term-columns">
            <div class="term-col">
              <div class="term-col-head">📘 이수 추천 과목</div>
              ${courseCol}
            </div>
            <div class="term-col">
              <div class="term-col-head">🎯 교내 프로그램</div>
              ${programCol}
            </div>
          </div>
        </div>`;
    })
    .join("");

  document.getElementById("roadmapCard").innerHTML = `
    <div class="roadmap-header">
      <h2>학기별 로드맵</h2>
      <span class="term-count-badge">${terms.length}개 학기</span>
    </div>
    ${warningHtml}
    ${termsHtml}
  `;
}

// --- 상담(챗봇) ---
function addChatBubble(text, who) {
  const el = document.createElement("div");
  el.className = `chat-bubble ${who === "user" ? "user" : ""}`;
  el.textContent = text;
  document.getElementById("chatMessages").appendChild(el);
  document.getElementById("chatMessages").scrollTop = 1e6;
}

// 어학·프로그래밍 역량은 이제 화면1 드롭다운이나 졸업 현황 카드의 "+ 추가하기"로만
// 입력받는다 — 챗봇이 먼저 캐묻지 않는다(2026-08-21 요청). 시작 인사도 항상 고정.
function renderChatIntro() {
  addChatBubble("진로에 관해 궁금한 게 있으신가요?", "bot");
}

// 한글 IME로 Enter를 눌러 조합을 확정할 때 keydown이 두 번 발화되는 브라우저가 있다
// (예: "없어" 입력 후 Enter → "없어"와 조합 중이던 잔여 글자 "어"가 따로 한 번 더
// 전송됨). 그 결과 PENDING_QUESTIONS.shift()가 짧은 시간 안에 두 번 불려 서로 다른
// 질문에 엉뚱한 답이 매칭되는 경쟁 상태가 실제로 발생했다(2026-08-21 실사용 중 발견).
// 전송 중 잠금(CHAT_BUSY)으로 두 문제를 한 번에 막는다 — IME 원인을 정확히 특정하지
// 않아도 "요청이 끝나기 전엔 다음 전송을 받지 않는다"는 방어로 충분하다.
let CHAT_BUSY = false;

async function sendChat() {
  if (CHAT_BUSY) return;
  const input = document.getElementById("chatInput");
  const text = input.value.trim();
  if (!text) return;

  CHAT_BUSY = true;
  addChatBubble(text, "user");
  input.value = "";
  input.style.height = "auto"; // 늘어난 입력창을 한 줄로 되돌린다

  try {
    await sendFreeFormQuestion(text);
  } finally {
    CHAT_BUSY = false;
  }
}

// 자유 질의 — 판정 데이터 + RAG 검색 결과를 근거로 Gemini가 답한다(app/agents/chat.py).
async function sendFreeFormQuestion(text) {
  const thinkingEl = document.createElement("div");
  thinkingEl.className = "chat-bubble";
  thinkingEl.textContent = "생각 중...";
  document.getElementById("chatMessages").appendChild(thinkingEl);
  document.getElementById("chatMessages").scrollTop = 1e6;

  try {
    const res = await fetch("/api/chat/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        audit: PLAN.audit,
        gap: PLAN.gap,
        competency_vector: PLAN.competency_vector,
        track: FORM_STATE.track,
        track_type: FORM_STATE.track_type,
        history: CHAT_HISTORY,
      }),
    });
    const body = await res.json();
    thinkingEl.remove();
    addChatBubble(body.reply, "bot");
    CHAT_HISTORY.push({ role: "user", content: text });
    CHAT_HISTORY.push({ role: "assistant", content: body.reply });
    if (body.blocked) refreshGuardrail();
  } catch (err) {
    thinkingEl.remove();
    addChatBubble("답변을 받아오지 못했습니다. 잠시 후 다시 시도해주세요.", "bot");
  }
}

// --- 가드레일 토글 ---
async function refreshGuardrail() {
  const res = await fetch("/api/guardrail");
  const body = await res.json();
  document.getElementById("guardrailLabel").textContent =
    `가드레일 ${body.enabled ? "켜짐" : "꺼짐"} · 인젝션 방어 ${body.blocked_count}건 차단`;
  const toggle = document.getElementById("guardrailToggle");
  toggle.classList.toggle("on", body.enabled);
}

function setupGuardrailToggle() {
  document.getElementById("guardrailToggle").addEventListener("click", async () => {
    await fetch("/api/guardrail/toggle", { method: "POST" });
    refreshGuardrail();
  });
}

// --- 초기화 ---
document.addEventListener("DOMContentLoaded", () => {
  if (!loadState()) return;
  renderHeader();
  renderCreditCard();
  renderCompetencyCard();
  renderRoadmapCard();
  renderChatIntro();
  refreshGuardrail();
  setupGuardrailToggle();
  setupSelfReportDelegation();

  document.getElementById("chatSend").addEventListener("click", sendChat);
  const chatInputEl = document.getElementById("chatInput");
  chatInputEl.addEventListener("keydown", (e) => {
    // e.isComposing/keyCode 229 — 한글 조합 확정 Enter까지 전송으로 잡으면 안 된다.
    // Shift+Enter는 줄바꿈(문자메시지 앱과 동일한 관례) — Enter 단독일 때만 전송.
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      sendChat();
    }
  });
  // 입력창이 내용만큼 아래로 늘어나게 — 문자메시지 앱처럼 한 줄로 시작해 넘치면 확장.
  chatInputEl.addEventListener("input", () => {
    chatInputEl.style.height = "auto";
    chatInputEl.style.height = `${chatInputEl.scrollHeight}px`;
  });
  document.getElementById("restartBtn").addEventListener("click", () => {
    sessionStorage.removeItem("pathfinder:planResult");
    sessionStorage.removeItem("pathfinder:formState");
    window.location.href = "upload.html";
  });
});
