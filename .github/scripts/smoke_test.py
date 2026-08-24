"""배포본 스모크 테스트 — 운영 자동화 계층 3.

docs/superpowers/specs/2026-08-24-운영-자동화-design.md 4장. GitHub Actions
smoke.yml에서 호출하지만, 로컬에서 `python3 .github/scripts/smoke_test.py
<배포URL> [main최신SHA]`로 직접 돌려도 동작한다(외부 서비스라 pytest가 아니라
독립 스크립트로 둔다 — 항상 네트워크·배포 상태에 의존해 pytest 스위트에 넣으면
CI가 외부 요인으로 흔들린다).

실패 항목은 GITHUB_STEP_SUMMARY와 stdout에 함께 출력하고, 하나라도 실패하면
exit code 1 — 워크플로우가 이 코드로 이슈 생성 여부를 판단한다(이슈 생성 자체는
smoke.yml이 담당, 이 스크립트는 순수 판정만 한다).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

COLD_START_TIMEOUT_SEC = 60  # 실측 콜드스타트 17.7초(2026-08-24) 대비 여유

SAMPLE_PLAN_PAYLOAD = {
    "courses": [
        {"name": "자료구조", "credit": 3, "category": "전공필수", "year": 2021, "semester": "1학기"},
    ],
    "admission_year": 2021,
    "track_type": "심화과정",
    "track": "백엔드",
}


def _get_json(url: str, timeout: int) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_json(url: str, payload: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_health_with_retry(base_url: str) -> tuple[dict | None, list[str]]:
    """콜드스타트를 감안해 재시도한다. 성공하면 (응답 dict, []), 실패하면 (None, [사유])."""
    deadline = time.monotonic() + COLD_START_TIMEOUT_SEC
    last_error = "알 수 없는 오류"
    while time.monotonic() < deadline:
        try:
            body = _get_json(f"{base_url}/health", timeout=10)
            if body.get("status") == "ok":
                return body, []
            last_error = f"status != ok ({body.get('status')!r})"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_error = str(e)
        time.sleep(3)
    return None, [f"/health 실패(최대 {COLD_START_TIMEOUT_SEC}초 재시도): {last_error}"]


def check_version_drift(health_body: dict, expected_sha: str | None) -> list[str]:
    if not expected_sha:
        return []  # main SHA를 안 넘겼으면(로컬 수동 실행 등) 드리프트 판정 자체를 생략
    deployed = health_body.get("version", "unknown")
    if deployed == "unknown":
        return ["배포본 /health에 version이 없음(GIT_SHA 없이 배포됨 — docs/배포.md 3장 확인)"]
    if deployed != expected_sha:
        return [f"버전 드리프트: 배포본={deployed} / main 최신={expected_sha} — 재배포 필요"]
    return []


def check_config(base_url: str) -> list[str]:
    try:
        body = _get_json(f"{base_url}/api/config", timeout=10)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        return [f"/api/config 요청 실패: {e}"]
    tracks = body.get("tracks", [])
    if len(tracks) != 8:
        return [f"/api/config tracks 개수 이상(기대 8, 실제 {len(tracks)})"]
    return []


def check_gemini(base_url: str) -> list[str]:
    """Gemini 쿼터 초과·장애를 감지한다(2026-08-24 추가). 배포본은 항상
    GOOGLE_API_KEY가 Secret Manager로 설정돼 있어야 하므로, reachable=false는
    "개발 모드"가 아니라 실제 장애로 취급한다."""
    try:
        body = _get_json(f"{base_url}/api/diagnostics/gemini", timeout=15)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        return [f"/api/diagnostics/gemini 요청 실패: {e}"]
    if not body.get("reachable"):
        return [f"Gemini 응답 불가(쿼터 초과 가능성): {body.get('reason', '사유 없음')}"]
    return []


def check_plan(base_url: str) -> list[str]:
    try:
        body = _post_json(f"{base_url}/api/plan", SAMPLE_PLAN_PAYLOAD, timeout=30)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        return [f"/api/plan 요청 실패: {e}"]
    if "schedule" not in body.get("roadmap", {}):
        return ["/api/plan 응답에 roadmap.schedule이 없음"]
    return []


def main() -> int:
    if len(sys.argv) < 2:
        print("사용법: python3 smoke_test.py <배포URL> [main최신SHA]", file=sys.stderr)
        return 2
    base_url = sys.argv[1].rstrip("/")
    expected_sha = sys.argv[2] if len(sys.argv) > 2 else None

    failures: list[str] = []

    health_body, health_failures = check_health_with_retry(base_url)
    failures += health_failures

    if health_body is not None:
        failures += check_version_drift(health_body, expected_sha)
        failures += check_config(base_url)
        failures += check_gemini(base_url)
        failures += check_plan(base_url)

    report_lines = [f"## 스모크 테스트 — {base_url}"]
    if failures:
        report_lines.append("### ❌ 실패")
        report_lines += [f"- {f}" for f in failures]
    else:
        version = (health_body or {}).get("version", "unknown")
        report_lines.append(f"✅ 전부 통과 (배포본 version: {version})")
    report = "\n".join(report_lines)
    print(report)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(report + "\n")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
