# Vertex AI Pipelines — 아주허브 신선도 유지 (실험적 — 기존 자동화와 별개)

`.github/workflows/ajouhub-freshness.yml`(GitHub Actions, 주 1회 cron으로 아주허브
신규 프로그램을 수집·태깅해 PR을 올림)과 **완전히 같은 목적**을 Vertex AI
Pipelines로도 구현했다.

**기존 GitHub Actions 자동화는 그대로 둔다.** 이건 추가 실행 경로다 — 여기서
안정적으로 도는 게 확인되면 나중에 이걸로 갈아끼울 수 있다. 그 전까진 실제 주간
자동화는 계속 GitHub Actions가 담당한다.

## 파이프라인 구성

```
fetch_new_programs(start_id, end_id)  -- 아주허브에서 신규 프로그램 상세 수집
        |
        v
tag_competency(programs_raw)          -- 역량 키워드/카테고리 태깅
        |
        v
summarize_new_programs(programs_tagged, new_count)  -- 신규 프로그램 요약(Markdown 아티팩트)
```

세 컴포넌트 모두 `data_pipeline/01_fetch_programs.py`·
`data_pipeline/03_tag_competency.py`·`.github/scripts/ajouhub_freshness.py`의
검증된 로직을 그대로 옮겼다(정규식·임계값·요청 간격까지 동일) — KFP 컴포넌트는
격리된 컨테이너에서 돌아 이 저장소의 로컬 모듈을 import할 수 없어서, 각 컴포넌트
함수 본문 안에 필요한 로직을 통째로 복사해 자기완결적으로 만들었다. 표준
라이브러리만 쓰므로(`urllib`/`re`/`json`/`html`) 컴포넌트 컨테이너에 추가 패키지
설치가 필요 없다.

**로컬에서 실제 아주허브 API + 태깅 규칙으로 직접 검증함**(2026-08-24, GCP
리소스는 안 건드림): `fetch_new_programs`는 실제 존재하는 프로그램 ID(NCR...2298,
"AJOU '26 취업 올 클리어 캠프")로 정확히 파싱했고, `tag_competency`는
"[미래자동차 Skill-UP]..." 제목을 `모빌리티_임베디드지식`으로 정확히 태깅했다 —
`data_pipeline/03_tag_competency.py`를 직접 돌렸을 때와 동일한 결과.

## 왜 별도 venv가 필요한가

`kfp`(파이프라인 컴파일용)와 `google-cloud-aiplatform`(제출용) 둘 다
`protobuf>=...,<8.0` 범위에서 실제로는 `protobuf==6.33.6`을 설치하려 한다(실측
확인). 이 프로젝트 메인 의존성(`google-genai`가 물고 오는
`google-ai-generativelanguage`)은 `protobuf<6.0`을 요구해서 충돌한다 —
`agent_engine/README.md`에 적은 것과 정확히 같은 문제다. 메인 `.venv`를 건드리지
않는다.

## 사용 방법

```bash
# 1. 저장소 루트에서, 파이프라인 전용 venv를 새로 만든다
cd ajou-pathfinder
python3 -m venv .venv-vertex-pipelines
source .venv-vertex-pipelines/bin/activate
pip install kfp google-cloud-aiplatform

# 2. 컴파일(로컬, GCP 리소스 생성 없음 — vertex_pipelines/ajouhub_freshness_pipeline.json 생성)
python3 vertex_pipelines/ajouhub_freshness_pipeline.py

# 3. Vertex AI Pipelines API 활성화 + 스테이징 버킷(최초 1회, agent_engine와 재사용 가능)
gcloud services enable aiplatform.googleapis.com
gsutil mb -l asia-northeast3 gs://<프로젝트ID>-pipelines-staging   # 이미 있으면 생략

# 4. 제출 — 반드시 저장소 루트에서 실행
python3 vertex_pipelines/submit.py \
  --project <GCP_PROJECT_ID> \
  --bucket <프로젝트ID>-pipelines-staging
```

`--start`/`--end`를 생략하면 `.github/scripts/ajouhub_freshness.py`와 같은 방식
(현재 `data/programs.json`의 최대 id+1 ~ +200)으로 자동 계산한다.

제출 후 출력되는 콘솔 링크(Vertex AI → Pipelines)에서 3개 컴포넌트가 순서대로
도는 걸 확인할 수 있다. `fetch_new_programs`가 200개 ID를 0.7초 간격으로 순회하므로
실행에 몇 분 걸린다(GitHub Actions cron 버전과 같은 소요시간).

## 지금 다루는 범위 / 안 다루는 범위

이 파이프라인은 "신규 프로그램을 찾아서 태깅하고 요약한다"까지만 한다.
GitHub Actions 버전이 하는 "실제 `data/programs.json`에 반영하는 PR을 자동으로
연다"는 포함하지 않는다 — Vertex AI Pipelines 실행 결과(요약 아티팩트)를 보고
사람이 직접 반영 여부를 판단하는 걸 전제로 한다. 자동 PR까지 필요해지면 그때
`google-cloud-pipeline-components`나 별도 Cloud Function으로 확장한다.
