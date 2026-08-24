"""개발 서버 진입점.

호스팅 환경(Cloud Run, 프리뷰 서버 등)이 PORT 환경변수로 포트를 지정하므로 그것을 따른다.
(1차 프로젝트와 동일 패턴)
"""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.api:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        log_level="warning",
    )
