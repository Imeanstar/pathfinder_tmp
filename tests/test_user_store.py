from app.user_store import get_latest_plan, save_latest_plan


# --- Firestore 우선 + 로컬 SQLite 대체 (2026-08-21, Cloud Run 배포 준비) ---
# Cloud Run은 무상태 컨테이너라 로컬 SQLite 파일이 재배포·스케일다운 사이에 유실될 수
# 있어 Firestore를 기본 저장소로 쓴다. 로컬 개발엔 GCP 인증정보가 없어 실제 Firestore를
# 못 쓰므로, 이 더블(Fake)들로 "Firestore를 실제로 쓰는 경로"와 "Firestore가 안 될 때
# SQLite로 조용히 대체하는 경로"를 인증정보 없이도 각각 검증한다.

class _FakeFirestoreDoc:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return self._data


class _FakeFirestoreDocRef:
    def __init__(self, store, key):
        self._store = store
        self._key = key

    def set(self, data):
        self._store[self._key] = data

    def get(self):
        return _FakeFirestoreDoc(self._store.get(self._key))


class _FakeFirestoreCollection:
    def __init__(self, store):
        self._store = store

    def document(self, key):
        return _FakeFirestoreDocRef(self._store, key)


class FakeFirestoreClient:
    """실제 google-cloud-firestore 없이 Firestore 경로를 검증하기 위한 인메모리 더블."""

    def __init__(self):
        self._collections: dict = {}

    def collection(self, name):
        self._collections.setdefault(name, {})
        return _FakeFirestoreCollection(self._collections[name])


class RaisingFirestoreClient:
    """Firestore를 쓸 수 없는 상황(네트워크 장애·권한 없음 등)을 흉내낸다."""

    def collection(self, name):
        raise RuntimeError("firestore unavailable")


def test_get_latest_plan_returns_none_when_never_saved(tmp_path):
    db_path = tmp_path / "user_plans.db"
    assert get_latest_plan("some-hash", db_path=db_path) is None


def test_save_then_get_latest_plan_roundtrips(tmp_path):
    db_path = tmp_path / "user_plans.db"
    save_latest_plan(
        "hash-a", form_state={"track": "백엔드"}, plan={"audit": {"ok": True}}, db_path=db_path
    )
    record = get_latest_plan("hash-a", db_path=db_path)
    assert record["form_state"] == {"track": "백엔드"}
    assert record["plan"] == {"audit": {"ok": True}}
    assert "updated_at" in record


def test_save_latest_plan_overwrites_not_appends(tmp_path):
    """계정당 최신 1건만 유지 — 전체 히스토리를 쌓지 않는다(2026-08-21 설계 결정,
    비용보다는 "이어보기"에 필요한 게 최신 1건뿐이라는 실사용 이유가 크다)."""
    db_path = tmp_path / "user_plans.db"
    save_latest_plan("hash-a", form_state={"track": "백엔드"}, plan={"n": 1}, db_path=db_path)
    save_latest_plan("hash-a", form_state={"track": "AI·데이터"}, plan={"n": 2}, db_path=db_path)

    record = get_latest_plan("hash-a", db_path=db_path)
    assert record["plan"] == {"n": 2}
    assert record["form_state"] == {"track": "AI·데이터"}


def test_different_accounts_do_not_overwrite_each_other(tmp_path):
    db_path = tmp_path / "user_plans.db"
    save_latest_plan("hash-a", form_state={}, plan={"who": "a"}, db_path=db_path)
    save_latest_plan("hash-b", form_state={}, plan={"who": "b"}, db_path=db_path)

    assert get_latest_plan("hash-a", db_path=db_path)["plan"] == {"who": "a"}
    assert get_latest_plan("hash-b", db_path=db_path)["plan"] == {"who": "b"}


def test_save_and_get_uses_injected_firestore_client_when_available(tmp_path):
    fake = FakeFirestoreClient()
    db_path = tmp_path / "unused.db"  # SQLite로는 절대 안 가야 함을 간접 확인용

    save_latest_plan(
        "hash-fs", form_state={"track": "AI·데이터"}, plan={"n": 1},
        db_path=db_path, firestore_client=fake,
    )
    record = get_latest_plan("hash-fs", db_path=db_path, firestore_client=fake)

    assert record["plan"] == {"n": 1}
    assert record["form_state"] == {"track": "AI·데이터"}
    assert not db_path.exists()  # SQLite 파일이 생성되지 않았어야 함(Firestore로만 처리됨)


def test_get_latest_plan_returns_none_when_firestore_has_no_document(tmp_path):
    fake = FakeFirestoreClient()
    db_path = tmp_path / "unused.db"
    assert get_latest_plan("never-saved-hash", db_path=db_path, firestore_client=fake) is None
    assert not db_path.exists()


def test_falls_back_to_sqlite_when_firestore_unavailable(tmp_path):
    db_path = tmp_path / "user_plans.db"
    raising = RaisingFirestoreClient()

    save_latest_plan(
        "hash-fallback", form_state={"track": "보안"}, plan={"n": 42},
        db_path=db_path, firestore_client=raising,
    )
    record = get_latest_plan("hash-fallback", db_path=db_path, firestore_client=raising)

    assert record["plan"] == {"n": 42}
    assert db_path.exists()  # 이번엔 실제로 SQLite에 떨어져야 함
