import pytest

from app.auth import InvalidDomainError, hash_email, verify_google_id_token


def _payload(email="student@ajou.ac.kr", email_verified=True, name="홍길동"):
    return {"email": email, "email_verified": email_verified, "name": name}


def test_verify_google_id_token_accepts_ajou_domain():
    result = verify_google_id_token(
        "fake-credential", client_id="dummy-client-id", decode_fn=lambda cred: _payload()
    )
    assert result["email"] == "student@ajou.ac.kr"
    assert result["name"] == "홍길동"
    assert result["email_hash"] == hash_email("student@ajou.ac.kr")


def test_verify_google_id_token_rejects_non_ajou_domain():
    with pytest.raises(InvalidDomainError):
        verify_google_id_token(
            "fake-credential",
            client_id="dummy-client-id",
            decode_fn=lambda cred: _payload(email="student@gmail.com"),
        )


def test_verify_google_id_token_rejects_unverified_email():
    with pytest.raises(InvalidDomainError):
        verify_google_id_token(
            "fake-credential",
            client_id="dummy-client-id",
            decode_fn=lambda cred: _payload(email_verified=False),
        )


def test_verify_google_id_token_is_case_insensitive_on_domain():
    result = verify_google_id_token(
        "fake-credential",
        client_id="dummy-client-id",
        decode_fn=lambda cred: _payload(email="Student@AJOU.AC.KR"),
    )
    assert result["email_hash"] == hash_email("student@ajou.ac.kr")


def test_hash_email_is_deterministic_and_never_reversible_looking():
    h1 = hash_email("student@ajou.ac.kr")
    h2 = hash_email("student@ajou.ac.kr")
    assert h1 == h2
    assert "@" not in h1
    assert len(h1) == 64  # sha256 hex digest


# --- pepper(HMAC 비밀키) 강화 (2026-08-21) ---
# 평문 SHA-256(이메일)만 쓰면, DB가 유출됐을 때 "학번@ajou.ac.kr"처럼 예측 가능한 패턴을
# 미리 해시해둔 사전(dictionary)과 대조해 원래 이메일을 역산할 수 있다 — 진짜 익명화가
# 아니다. 서버만 아는 비밀값(pepper)을 섞은 HMAC-SHA256으로 바꿔 pepper 없이는 사전
# 공격이 안 통하게 한다(사용자 요청, Cloud Run 배포 전 강화).

def test_hash_email_differs_with_different_pepper():
    h1 = hash_email("student@ajou.ac.kr", pepper="secret-a")
    h2 = hash_email("student@ajou.ac.kr", pepper="secret-b")
    assert h1 != h2


def test_hash_email_same_pepper_is_deterministic():
    h1 = hash_email("student@ajou.ac.kr", pepper="secret-a")
    h2 = hash_email("student@ajou.ac.kr", pepper="secret-a")
    assert h1 == h2


def test_hash_email_reads_pepper_from_env_when_not_passed_explicitly(monkeypatch):
    monkeypatch.setenv("EMAIL_HASH_PEPPER", "env-secret-1")
    h_env1 = hash_email("student@ajou.ac.kr")

    monkeypatch.setenv("EMAIL_HASH_PEPPER", "env-secret-2")
    h_env2 = hash_email("student@ajou.ac.kr")

    assert h_env1 != h_env2
    assert h_env1 == hash_email("student@ajou.ac.kr", pepper="env-secret-1")


def test_verify_google_id_token_hash_matches_hash_email_under_same_pepper(monkeypatch):
    monkeypatch.setenv("EMAIL_HASH_PEPPER", "test-pepper")
    result = verify_google_id_token(
        "fake-credential", client_id="dummy-client-id", decode_fn=lambda cred: _payload()
    )
    assert result["email_hash"] == hash_email("student@ajou.ac.kr", pepper="test-pepper")
