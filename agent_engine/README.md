# Vertex AI Agent Engine 배포 (실험적 — Cloud Run과 별개)

`app/agents/supervisor.py`의 LangGraph 멀티에이전트 그래프(diagnose_competency ->
compute_gap -> course_reco/program_reco -> roadmap)를 [Vertex AI Agent
Engine](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/overview)에
그대로 얹는다.

**기존 Cloud Run 배포(`app/api.py`, `.github/workflows/deploy.yml`)는 그대로 둔다.**
이건 추가 배포 대상이다 — 여기서 정상 동작이 확인되면 나중에 Cloud Run 대신 이걸
메인으로 갈아끼울 수 있다. 그 전까진 두 배포가 동시에 존재하고, 서비스는 계속
Cloud Run 것을 쓴다.

**실제로 배포해서 검증함**(2026-08-25, `projects/783601922022/locations/
asia-northeast3/reasoningEngines/1514951101214883840`): 배포된 Agent Engine에
실제 쿼리(`{"courses":[{"name":"자료구조",...}], "track":"백엔드", ...}`)를
날려 로컬 Cloud Run 경로와 동일한 과목·프로그램 추천 결과를 받았다. 처음 두 번의
배포 시도는 실패했고 원인을 Cloud Logging에서 직접 찾아 고쳤다(아래
"배포 중 실제로 겪은 문제" 참고, `agent_engine/deploy.py`·
`agent_engine/requirements.txt`에 이미 반영됨).

### 배포 중 실제로 겪은 문제

1. **`ModuleNotFoundError: No module named 'agent_engine'`** — `extra_packages`에
   `agent_engine` 패키지 자체가 빠져 있었다. cloudpickle이 `PathfinderAgentEngine`
   인스턴스를 `agent_engine.pathfinder_agent` 모듈 경로로 참조해 저장하는데,
   원격에서 unpickle할 때 그 패키지가 없으면 기동 자체가 실패한다.
2. **`ModuleNotFoundError: No module named 'google.cloud.aiplatform'`** — 우리
   코드가 아니라 Agent Engine 프레임워크 자체(`telemetry_utils.py`의
   `resolve_project_id`)가 원격 컨테이너 안에서 이 패키지를 요구한다.
   `agent_engine/requirements.txt`에 `google-cloud-aiplatform`을 추가해서
   해결했다 — 이 컨테이너는 Cloud Run 배포와 완전히 분리된 별도 환경이라 여기서
   protobuf 6.x를 쓰는 건 Cloud Run 쪽에 영향이 없다.

둘 다 Cloud Logging(`gcloud logging read 'resource.type="aiplatform.googleapis.com/
ReasoningEngine" resource.labels.reasoning_engine_id="<ID>"'`)에서 정확한
트레이스백을 확인해서 찾았다 — `agent_engines.create()`가 던지는 에러 메시지
자체("failed to start and cannot serve traffic")는 원인을 안 알려준다.

## 왜 별도 venv가 필요한가

`google-cloud-aiplatform[agent_engines,langgraph]`는 `protobuf>=4.25.8,<8.0`을
요구하는데, 실제로 pip가 골라준 조합이 `protobuf==6.33.6`이었다(실측 확인,
2026-08-24). 이 프로젝트 메인 의존성(`google-genai`가 물고 오는
`google-ai-generativelanguage`)은 `protobuf<6.0`을 요구한다 — 이미 한 번 겪어서
`requirements.txt`/`requirements-runtime.txt`에 `google-cloud-firestore==2.20.2`로
버전을 고정해둔 것과 같은 종류의 충돌이다(2026-08-21). 메인 `.venv`에 같이 설치하면
Gemini 관련 기능이 깨질 위험이 있어, 배포 스크립트 실행용 venv를 완전히 분리한다.

실제로 배포되는 코드(`agent_engine/pathfinder_agent.py`)는 이 SDK를 전혀
import하지 않는다 — 순수 `app.*` + 표준 라이브러리만 쓴다. `tests/test_agent_engine.py`가
메인 venv에서 그대로 돌아가는 이유도 이것 때문이다.

## 배포 방법

```bash
# 1. 저장소 루트에서, 배포 전용 venv를 새로 만든다(메인 .venv와 별개)
cd ajou-pathfinder
python3 -m venv .venv-agent-engine
source .venv-agent-engine/bin/activate
pip install "google-cloud-aiplatform[agent_engines,langgraph]"

# 2. Vertex AI API 활성화 + 스테이징용 GCS 버킷(최초 1회)
gcloud services enable aiplatform.googleapis.com
gsutil mb -l asia-northeast3 gs://<프로젝트ID>-agent-engine-staging

# 3. 배포 — 반드시 저장소 루트에서 실행(상대경로가 데이터 파일 위치와 맞물림)
python3 agent_engine/deploy.py \
  --project <GCP_PROJECT_ID> \
  --location asia-northeast3 \
  --bucket <프로젝트ID>-agent-engine-staging
```

성공하면 `projects/.../locations/.../reasoningEngines/...` 형태의 resource name이
출력된다 — 이후 갱신할 땐 `--update-resource-name`으로 그 값을 넘기면 새로 만들지
않고 업데이트한다.

## 호출 확인

```python
import vertexai
from vertexai import agent_engines

vertexai.init(project="<GCP_PROJECT_ID>", location="asia-northeast3")
remote_agent = agent_engines.get("<위에서 나온 resource name>")

result = remote_agent.query(
    courses=[{"name": "자료구조", "credit": 3, "category": "전공필수"}],
    track="백엔드",
    taken_course_names=["자료구조"],
    taken_program_titles=[],
    remaining_terms=["3-1", "3-2"],
)
print(result["roadmap"])
```

`app/api.py`의 `/api/plan`이 호출하는 것과 완전히 같은 `run_full_plan()`을 그대로
위임하므로(`tests/test_agent_engine.py`가 두 경로의 결과가 같은지 직접 대조 검증),
Cloud Run 버전과 여기서 나오는 판정 결과는 항상 같아야 한다 — 다르면 배포 패키징
문제(데이터 파일 누락 등)를 의심할 것.

## 지금 다루는 범위 / 안 다루는 범위

`PathfinderAgentEngine.query()`는 `run_full_plan()`(역량진단·격차·추천·로드맵
배치)만 감싼다 — `/api/plan`이 그 앞뒤로 하는 졸업요건 판정(`audit_graduation`),
요람 근거 첨부(`attach_citation`), 추천 사유 자연어화(`soften_recommendation_reasons`)는
포함하지 않는다. 이유: 그 부분들은 Gemini(`google-genai`)를 직접 호출하는데,
그러면 이 배포도 결국 `google-genai`가 필요해져 위 protobuf 충돌을 다시 끌어들인다.
지금은 "LangGraph 멀티에이전트 그래프 자체가 Agent Engine에서 정상 동작하는가"를
증명하는 게 목적이라 이 범위로 충분하다 — 나중에 실제로 갈아끼우기로 결정하면
그때 이 경계를 다시 논의한다.

## 정리(리소스 삭제)

```bash
python3 -c "
import vertexai
from vertexai import agent_engines
vertexai.init(project='<GCP_PROJECT_ID>', location='asia-northeast3')
agent_engines.delete('<resource name>')
"
```
