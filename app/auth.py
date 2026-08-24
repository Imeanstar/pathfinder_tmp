"""
Google 로그인 — @ajou.ac.kr 조직 계정만 허용(2026-08-21). ID 토큰 검증은 Google의
공개키로 서명을 확인하는 표준 절차라 프론트가 보낸 이메일 문자열을 그대로 믿는 게
아니라, 서명 검증을 통과한 토큰의 payload만 신뢰한다(google-auth는 google-genai의
의존성으로 이미 설치돼 있어 추가 설치 불필요). 이메일 자체는 저장하지 않고 해시만
계정 식별자로 쓴다(app/user_store.py) — "PII는 서버 저장 금지"라는 이 프로젝트의
핵심 설계 원칙을 로그인 기능에도 그대로 적용한 것.
"""
import hashlib
import hmac
import os
from typing import Callable, Optional

ALLOWED_DOMAIN = "ajou.ac.kr"

# 평문 SHA-256(이메일)만 쓰면, DB가 유출됐을 때 "학번@ajou.ac.kr"처럼 예측 가능한 패턴을
# 미리 해시해둔 사전과 대조해 원래 이메일을 역산할 수 있다(진짜 익명화가 아님, 2026-08-21
# 사용자 지적). 서버만 아는 비밀값(pepper)을 섞은 HMAC-SHA256으로 바꿔 pepper 없이는
# 사전 공격이 안 통하게 한다. 개발용 기본값은 배포 전 반드시 EMAIL_HASH_PEPPER로
# 덮어써야 한다 — GOOGLE_API_KEY와 같은 원칙(없어도 켜지지만, 진짜 배포엔 반드시 필요).
_DEV_DEFAULT_PEPPER = "ajou-pathfinder-dev-only-insecure-pepper-change-me"


class InvalidDomainError(Exception):
    """검증 자체는 통과했지만(진짜 구글 계정) 아주대 이메일이 아닌 경우."""


def hash_email(email: str, pepper: Optional[str] = None) -> str:
    if pepper is None:
        pepper = os.environ.get("EMAIL_HASH_PEPPER", _DEV_DEFAULT_PEPPER)
    normalized = email.strip().lower().encode("utf-8")
    return hmac.new(pepper.encode("utf-8"), normalized, hashlib.sha256).hexdigest()


def _default_decode(credential: str, client_id: str) -> dict:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    return google_id_token.verify_oauth2_token(credential, google_requests.Request(), client_id)


def verify_google_id_token(
    credential: str, client_id: str, decode_fn: Optional[Callable[[str], dict]] = None
) -> dict:
    """credential(구글이 서명한 ID 토큰 JWT)을 검증해 {email, name, email_hash}를 반환한다.
    아주대 이메일이 아니거나 이메일이 검증되지 않았으면 InvalidDomainError.
    decode_fn을 주입하면(테스트용) 실제 구글 네트워크 검증 없이 디코딩 결과를 흉내낼 수 있다."""
    payload = decode_fn(credential) if decode_fn else _default_decode(credential, client_id)

    email = payload.get("email", "")
    if not payload.get("email_verified") or not email.lower().endswith(f"@{ALLOWED_DOMAIN}"):
        raise InvalidDomainError(f"@{ALLOWED_DOMAIN} 계정만 로그인할 수 있습니다.")

    return {
        "email": email,
        "name": payload.get("name") or email.split("@")[0],
        "email_hash": hash_email(email),
    }
