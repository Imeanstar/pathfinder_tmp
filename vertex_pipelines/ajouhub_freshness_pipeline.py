"""아주허브 프로그램 신선도 유지 — Vertex AI Pipelines 버전(서비스 고도화, 2026-08-24).

`.github/workflows/ajouhub-freshness.yml`(GitHub Actions, 주 1회 cron)과 **완전히
같은 목적**을 Vertex AI Pipelines로 구현했다 — 기존 GitHub Actions 자동화는
그대로 두는 **추가** 경로다. 여기서 안정적으로 도는 게 확인되면 나중에 갈아끼울
수 있게 하는 게 목적(사용자 요청)이라, 로직도 새로 설계하지 않고
`data_pipeline/01_fetch_programs.py`·`data_pipeline/03_tag_competency.py`의
검증된 로직을 그대로 옮겼다.

KFP 컴포넌트는 격리된 컨테이너에서 실행돼 이 저장소의 로컬 모듈(data_pipeline.*)을
import할 수 없다 — 그래서 각 컴포넌트 함수 본문 안에 필요한 로직을 전부 그대로
복사해 자기완결적으로 만들었다(원본 스크립트와 정확히 같은 정규식·임계값을 쓴다 —
"같은 로직을 두 곳에 유지"가 아니라 "원본을 컴포넌트 안으로 옮긴 것"에 가깝다).
표준 라이브러리만 쓰므로(urllib/re/json/html) 컴포넌트 컨테이너 이미지에 추가
패키지 설치가 필요 없다.

컴파일(로컬, GCP 리소스 생성 없음):
    python3 vertex_pipelines/ajouhub_freshness_pipeline.py
    # -> vertex_pipelines/ajouhub_freshness_pipeline.json 생성

제출(실제 Vertex AI Pipelines 실행 — 별도 venv 필요, README.md 참고):
    python3 vertex_pipelines/submit.py --project <GCP_PROJECT_ID> --bucket <STAGING_BUCKET>
"""
from kfp import compiler, dsl


@dsl.component(base_image="python:3.12-slim")
def fetch_new_programs(
    start_id: int,
    end_id: int,
    programs_raw: dsl.Output[dsl.Dataset],
) -> int:
    """data_pipeline/01_fetch_programs.py의 fetch()/strip_tags()/parse_program_detail()을
    그대로 옮겼다 — 유효 응답 임계값(10000바이트)·요청 간격(0.7초)·정규식까지 동일하다.
    반환값은 이번에 새로 수집된 프로그램 개수(다음 컴포넌트·요약에 씀)."""
    import html
    import json
    import re
    import time
    import urllib.error
    import urllib.request

    BASE_URL = "https://hub.ajou.ac.kr/ncrProgramAppl/a/m/getProgramDetail.do"
    VALID_SIZE_THRESHOLD = 10000
    REQUEST_INTERVAL_SEC = 0.7
    FIELD_LABELS = [
        "프로그램 구분", "모집기간", "활동기간", "참여 학과/학부", "참여학년",
        "참여대상", "장소", "실시유형", "운영부서", "문의전화",
    ]

    def fetch(npi_key_id: str) -> bytes | None:
        url = f"{BASE_URL}?npiKeyId=NCR{npi_key_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read()
        except urllib.error.URLError:
            return None

    def strip_tags(fragment: str) -> str:
        text = re.sub(r"<[^>]+>", " ", fragment)
        text = html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    def parse_program_detail(raw: bytes, npi_key_id: str) -> dict | None:
        text = raw.decode("utf-8", errors="replace")

        dt_match = re.search(
            r'<dl class="program_contentbox program_rightbox">\s*<dt>\s*<span>(.*?)</span>\s*<br>\s*(.*?)\s*<p>\s*(.*?)\s*</p>',
            text, re.S,
        )
        if not dt_match:
            return None

        category_raw, title, org_short = dt_match.groups()
        category_path = [strip_tags(c) for c in re.findall(r"<i>(.*?)</i>", category_raw)]
        title = strip_tags(title)
        org_short = strip_tags(org_short)

        fields = {}
        for label in FIELD_LABELS:
            m = re.search(rf"<strong>{re.escape(label)}</strong>\s*(.*?)\s*</dd>", text, re.S)
            if m:
                fields[label] = strip_tags(m.group(1))

        org = fields.get("운영부서", org_short)
        org = re.sub(r"\s*/\s*null\b", "", org).strip()

        return {
            "id": f"NCR{npi_key_id}",
            "title": title,
            "org": org,
            "category_path": category_path,
            "program_type": fields.get("프로그램 구분"),
            "apply_period": fields.get("모집기간"),
            "operate_period": fields.get("활동기간"),
            "target_dept": fields.get("참여 학과/학부"),
            "target_grade": fields.get("참여학년"),
            "target_audience": fields.get("참여대상"),
            "location": fields.get("장소"),
            "format": fields.get("실시유형"),
            "contact": fields.get("문의전화"),
            "url": f"{BASE_URL}?npiKeyId=NCR{npi_key_id}",
            "competency_tags": [],
        }

    collected = []
    for n in range(start_id, end_id):
        npi_key_id = f"{n:012d}"
        raw = fetch(npi_key_id)
        if raw is not None and len(raw) >= VALID_SIZE_THRESHOLD:
            parsed = parse_program_detail(raw, npi_key_id)
            if parsed:
                collected.append(parsed)
        time.sleep(REQUEST_INTERVAL_SEC)

    with open(programs_raw.path, "w", encoding="utf-8") as f:
        json.dump(collected, f, ensure_ascii=False, indent=2)

    return len(collected)


@dsl.component(base_image="python:3.12-slim")
def tag_competency(
    programs_raw: dsl.Input[dsl.Dataset],
    competency_yaml_rules_json: str,
    category_rules_json: str,
    programs_tagged: dsl.Output[dsl.Dataset],
) -> None:
    """data_pipeline/03_tag_competency.py의 tag_by_keywords()/tag_programs()를 그대로
    옮겼다. 키워드/카테고리 규칙은 로컬 파일 import 대신 파이프라인 파라미터(JSON
    문자열)로 받는다 — submit.py가 data_pipeline/03_tag_competency.py의
    KEYWORD_RULES/CATEGORY_RULES를 그대로 읽어 넘긴다(규칙이 바뀌면 원본 파일만
    고치면 되고, 이 컴포넌트는 그대로 최신 규칙을 받는다)."""
    import json

    with open(programs_raw.path, encoding="utf-8") as f:
        programs = json.load(f)

    keyword_rules: dict = json.loads(competency_yaml_rules_json)
    category_rules: dict = json.loads(category_rules_json)

    def tag_by_keywords(text: str, rules: dict) -> list:
        tags = []
        for comp_id, keywords in rules.items():
            if any(kw in text for kw in keywords):
                tags.append(comp_id)
        return tags[:3]

    for p in programs:
        title_tags = tag_by_keywords(p.get("title", ""), keyword_rules)
        category_text = " ".join(p.get("category_path", []))
        category_tags = []
        for keyword, comp_ids in category_rules.items():
            if keyword in category_text:
                category_tags.extend(comp_ids)
        p["competency_tags"] = list(dict.fromkeys(title_tags + category_tags))[:3]

    with open(programs_tagged.path, "w", encoding="utf-8") as f:
        json.dump(programs, f, ensure_ascii=False, indent=2)


@dsl.component(base_image="python:3.12-slim")
def summarize_new_programs(
    programs_tagged: dsl.Input[dsl.Dataset],
    new_count: int,
    summary: dsl.Output[dsl.Markdown],
) -> None:
    """.github/scripts/ajouhub_freshness.py의 summarize_new_programs()와 같은 형식의
    보고서를 만든다 — GitHub Actions 버전은 PR 본문에, 이 버전은 파이프라인 실행
    아티팩트(Vertex AI 콘솔에서 확인 가능)에 남긴다."""
    import json

    with open(programs_tagged.path, encoding="utf-8") as f:
        programs = json.load(f)

    if new_count == 0:
        text = "새로 발견된 프로그램 없음."
    else:
        lines = [f"### 신규 프로그램 {new_count}건"]
        for p in programs[-new_count:]:
            tags = ", ".join(p.get("competency_tags", [])) or "태그 없음"
            lines.append(f"- **{p['title']}** ({p['id']}) — {tags}")
        text = "\n".join(lines)

    with open(summary.path, "w", encoding="utf-8") as f:
        f.write(text)


@dsl.pipeline(
    name="ajouhub-freshness",
    description=(
        "아주허브 신규 비교과 프로그램 수집 -> 역량 태깅 -> 요약. "
        ".github/workflows/ajouhub-freshness.yml과 같은 목적의 Vertex AI Pipelines 버전."
    ),
)
def ajouhub_freshness_pipeline(
    start_id: int,
    end_id: int,
    competency_yaml_rules_json: str,
    category_rules_json: str,
) -> None:
    fetch_task = fetch_new_programs(start_id=start_id, end_id=end_id)
    tag_task = tag_competency(
        programs_raw=fetch_task.outputs["programs_raw"],
        competency_yaml_rules_json=competency_yaml_rules_json,
        category_rules_json=category_rules_json,
    )
    summarize_new_programs(
        programs_tagged=tag_task.outputs["programs_tagged"],
        new_count=fetch_task.outputs["Output"],
    )


if __name__ == "__main__":
    from pathlib import Path

    out_path = Path(__file__).resolve().parent / "ajouhub_freshness_pipeline.json"
    compiler.Compiler().compile(ajouhub_freshness_pipeline, str(out_path))
    print(f"컴파일 완료: {out_path}")
