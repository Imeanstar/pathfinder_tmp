FROM python:3.12-slim

WORKDIR /app

COPY requirements-runtime.txt .
RUN pip install --no-cache-dir -r requirements-runtime.txt

COPY app/ app/
COPY serve.py .

# 서비스가 실제로 읽는 데이터 파일만 명시적으로 넣는다(app/*.py의 DATA_DIR 참조 기준) —
# data/programs_raw.json(스크래핑 중간 산출물)·data/user_plans.db(런타임에 생성되는
# 로그인 계정별 저장소, 이미지에 미리 구워 넣으면 안 됨)는 제외.
COPY data/courses.json data/programs.json data/graduation_requirements.json data/yoram_chunks.jsonl data/
COPY data_pipeline/competency.yaml data_pipeline/

# 사전계산된 RAG 임베딩 캐시(비용/레이턴시 최적화, 2026-08-24) — 없으면
# GeminiEncoder.fit()이 콜드스타트마다 코퍼스 전체를 API로 재임베딩한다.
# data_pipeline/04_precompute_embeddings.py로 생성·커밋해둔 것을 그대로 넣는다.
# 코퍼스가 바뀌면(계층 2 자동 PR 등) 지문이 안 맞아 자동으로 무시되고 실시간 계산으로
# 안전하게 폴백하므로, 이 파일이 없어도 서비스 자체는 깨지지 않는다.
COPY data/embeddings/ data/embeddings/

# Cloud Run이 PORT를 주입한다(기본 8080). serve.py가 그 값을 읽는다.
ENV PORT=8080
EXPOSE 8080

CMD ["python", "serve.py"]
