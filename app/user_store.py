"""
로그인한 계정의 "가장 최근 로드맵 진단"만 저장한다(2026-08-21). 계정 식별자는
app/auth.py가 계산한 이메일 해시뿐 — 이메일 원문은 여기 어디에도 남지 않는다.

전체 히스토리 대신 계정당 최신 1건만 덮어쓰는 이유: 스냅샷 하나가 수십KB라 전체
이력을 다 쌓아도 이 서비스 규모(교내 데모)에선 비용이 사실상 안 들지만, 실제로
쓰이는 기능은 "이어보기"(가장 최근 진단으로 돌아가기)뿐이라 이력 목록·삭제 정책까지
만들 이유가 없다 — 비용이 아니라 불필요한 복잡도가 이 결정의 진짜 이유.

저장소: Firestore 우선, 로컬 SQLite는 대체 경로(2026-08-21, Cloud Run 배포 준비 중
재설계). Cloud Run은 무상태 컨테이너라 로컬 파일에 쓴 데이터가 재배포·스케일다운·
다중 인스턴스 사이에서 유실되거나 인스턴스마다 달라질 수 있다 — Firestore(GCP
관리형, 기본 암호화 저장, get/set by key만 필요한 이 용도에 딱 맞음)를 기본으로 쓰고,
Firestore를 쓸 수 없는 환경(로컬 개발 — 인증정보 없음, google-cloud-firestore 미설치
등)에서는 조용히 SQLite로 대체한다 — "AI 경로엔 항상 대체 경로가 있어야 한다"는 이
프로젝트의 기존 원칙(app/llm.py, app/retrieval.py)을 저장소 계층에도 그대로 적용.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "user_plans.db"
FIRESTORE_COLLECTION = "user_plans"

_firestore_client_cache = None
_firestore_checked = False


def _get_firestore_client():
    """Firestore 클라이언트를 지연 생성하고 실패 여부를 캐시한다. 로컬 개발엔 GCP
    인증정보가 없어 매번 시도하면 매 요청마다 인증정보 탐색 지연이 반복되므로,
    한 번 실패하면 이후엔 재시도 없이 바로 None(=SQLite 대체 경로)을 돌려준다."""
    global _firestore_client_cache, _firestore_checked
    if _firestore_checked:
        return _firestore_client_cache
    _firestore_checked = True
    try:
        from google.cloud import firestore

        _firestore_client_cache = firestore.Client()
    except Exception:
        _firestore_client_cache = None
    return _firestore_client_cache


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS user_plans ("
        "email_hash TEXT PRIMARY KEY, form_state TEXT NOT NULL, plan TEXT NOT NULL, "
        "updated_at TEXT NOT NULL)"
    )
    return conn


def save_latest_plan(
    email_hash: str,
    form_state: dict,
    plan: dict,
    db_path: Optional[Path] = None,
    firestore_client=None,
) -> None:
    updated_at = datetime.now(timezone.utc).isoformat()

    client = firestore_client if firestore_client is not None else _get_firestore_client()
    if client is not None:
        try:
            client.collection(FIRESTORE_COLLECTION).document(email_hash).set(
                {"form_state": form_state, "plan": plan, "updated_at": updated_at}
            )
            return
        except Exception:
            pass  # Firestore 호출 실패(네트워크·권한 등) — SQLite로 대체

    # db_path 기본값을 함수 정의 시점에 고정하지 않고 호출 시점에 모듈 전역 DB_PATH를
    # 읽는다 — 그래야 테스트에서 `app.user_store.DB_PATH`를 monkeypatch했을 때 이미
    # import된 함수도 실제로 바뀐 경로를 본다(기본 인자값으로 고정하면 import 시점
    # 값이 그대로 굳어버려 monkeypatch가 안 먹는 흔한 함정).
    conn = _connect(db_path or DB_PATH)
    try:
        conn.execute(
            "INSERT INTO user_plans (email_hash, form_state, plan, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(email_hash) DO UPDATE SET "
            "form_state=excluded.form_state, plan=excluded.plan, updated_at=excluded.updated_at",
            (
                email_hash,
                json.dumps(form_state, ensure_ascii=False),
                json.dumps(plan, ensure_ascii=False),
                updated_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_plan(
    email_hash: str, db_path: Optional[Path] = None, firestore_client=None
) -> Optional[dict]:
    client = firestore_client if firestore_client is not None else _get_firestore_client()
    if client is not None:
        try:
            doc = client.collection(FIRESTORE_COLLECTION).document(email_hash).get()
            return doc.to_dict() if doc.exists else None
        except Exception:
            pass  # Firestore 자체가 지금 안 되면 SQLite로 대체 시도

    conn = _connect(db_path or DB_PATH)
    try:
        row = conn.execute(
            "SELECT form_state, plan, updated_at FROM user_plans WHERE email_hash = ?",
            (email_hash,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    form_state, plan, updated_at = row
    return {"form_state": json.loads(form_state), "plan": json.loads(plan), "updated_at": updated_at}
