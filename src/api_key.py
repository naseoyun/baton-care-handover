"""공공데이터포털(data.go.kr) 인증키 불러오기.

찾는 순서
  1) 환경변수 DATA_GO_KR_SERVICE_KEY
  2) 프로젝트 폴더의 .env 파일 (DATA_GO_KR_SERVICE_KEY=...)
  3) 원자료 폴더의 「OpenAPI 활용가이드 … 사회복지시설정보 … .docx」 첫머리에 적힌 키 ("내 key: ...")

키는 화면에 앞 4자리·뒤 4자리만 보여 준다. 코드·결과 파일에는 저장하지 않는다.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, find_raw  # noqa: E402

ENV_NAME = "DATA_GO_KR_SERVICE_KEY"


def _from_env_file() -> str | None:
    env = ROOT / ".env"
    if not env.exists():
        return None
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(ENV_NAME + "="):
            v = line.split("=", 1)[1].strip().strip('"').strip("'")
            return v or None
    return None


def _from_docx() -> str | None:
    try:
        import docx
        path = find_raw("api_guide_docx")
    except Exception:
        return None
    d = docx.Document(str(path))
    for p in d.paragraphs[:15]:
        m = re.search(r"key\s*[:：]\s*(\S+)", p.text, flags=re.I)
        if m:
            return m.group(1).strip()
    return None


def mask(key: str) -> str:
    return key[:4] + "…" + key[-4:] if key and len(key) > 10 else "****"


def load_service_key() -> str:
    for source, getter in (("환경변수", lambda: os.environ.get(ENV_NAME)), (".env", _from_env_file),
                           ("API 활용가이드 docx", _from_docx)):
        key = getter()
        if key:
            # 포털의 '인코딩' 키(%2B 등 포함)를 넣었으면 한 번 풀어서 requests가 다시 인코딩하게 한다
            if "%" in key:
                key = unquote(key)
            print(f"[API 키] {source}에서 불러옴: {mask(key)}")
            return key
    raise RuntimeError(
        "data.go.kr 인증키를 찾지 못했습니다.\n"
        f"  - 프로젝트 폴더에 .env 파일을 만들고 {ENV_NAME}=발급받은키 를 적거나\n"
        "  - 원자료 폴더의 API 활용가이드 docx 첫 줄에 '내 key: 발급받은키' 를 적어 두세요."
    )


if __name__ == "__main__":
    load_service_key()
