"""바톤 프로젝트 공통 설정: 경로, 원자료 찾기, 시도 이름, 한글 글꼴."""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 원자료(PDF·CSV·xlsx·zip·docx)는 기본적으로 프로젝트 폴더의 상위 폴더(바탕화면\사회보장)에 있다고 본다.
RAW_DIR = Path(os.environ.get("BATON_RAW_DIR", ROOT.parent))
PROCESSED = ROOT / "data" / "processed"
API_DIR = ROOT / "data" / "api"
FIG_DIR = ROOT / "outputs" / "figures"
for _d in (PROCESSED, API_DIR, FIG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

RAW_PATTERNS = {
    "ilam_pdf": "*장애인복지시설*일람표*.pdf",
    "nblsa_pdf": "*국민기초생활보장*사업안내*.pdf",
    "registered_csv": "시군구별_장애정도별_성별_등록장애인수*.csv",
    "trend_xlsx": "*장애인거주시설*현황*.xlsx",
    "allowance_zip": "장애수당*수급자수*.zip",
    "api_guide_docx": "*OpenAPI*사회복지시설정보*.docx",
}


def find_raw(key: str) -> Path:
    """RAW_DIR에서 원자료 파일을 찾는다. 없으면 무엇을 어디에 두어야 하는지 알려 준다."""
    pattern = RAW_PATTERNS[key]
    hits = sorted(RAW_DIR.glob(pattern))
    if not hits:
        raise FileNotFoundError(
            f"원자료를 찾지 못했습니다: {pattern}\n"
            f"찾은 위치: {RAW_DIR}\n"
            "파일을 이 폴더에 두거나 환경변수 BATON_RAW_DIR로 위치를 지정하세요."
        )
    return hits[-1]


SIDO_FULL = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종",
    "경기도": "경기", "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북", "충청남도": "충남",
    "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남", "경상북도": "경북",
    "경상남도": "경남", "제주특별자치도": "제주",
}
SIDO_ORDER = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기",
              "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
METRO = {"서울", "부산", "대구", "인천", "광주", "대전", "울산"}

# 일람표 거주시설 종류(총괄표 열 순서와 같음)
RES_TYPES = ["지체", "시각", "청각", "지적", "중증", "영유아", "단기", "공동"]
RES_TYPE_NAME = {
    "지체": "지체장애인 거주시설", "시각": "시각장애인 거주시설", "청각": "청각·언어장애인 거주시설",
    "지적": "지적장애인 거주시설", "중증": "중증장애인 거주시설", "영유아": "장애영유아 거주시설",
    "단기": "장애인 단기거주시설", "공동": "장애인 공동생활가정",
}
# 발달장애 성인과 관련된 거주 유형(바톤의 돌봄 경로에서 쓰는 범위)
DEV_TYPES = ["지적", "중증", "단기", "공동"]


def sgg_key(sido: str, sgg: str) -> str:
    """시군구 이름을 지역 결합용 키로 맞춘다.
    - 광역시가 아닌 곳의 '○○시○○구'(예: 수원시장안구)는 '○○시'로 묶는다(일람표는 시 단위).
    - 세종은 '세종시' 하나로 둔다.
    """
    g = re.sub(r"\s+", "", str(sgg))
    if sido == "세종":
        return "세종시"
    m = re.match(r"^(.+?시)(.+구)$", g)
    if m and sido not in METRO:
        return m.group(1)
    return g


def setup_korean_font():
    """matplotlib 한글 글꼴을 운영체제에 맞게 고른다(Windows: 맑은 고딕)."""
    import matplotlib
    from matplotlib import font_manager

    candidates = ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR",
                  "Noto Sans KR", "Noto Sans CJK JP"]
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in installed:
            matplotlib.rcParams["font.family"] = name
            break
    else:
        print("[알림] 한글 글꼴을 찾지 못했습니다. 그래프의 한글이 깨지면 맑은 고딕이나 나눔고딕을 설치하세요.")
    matplotlib.rcParams["axes.unicode_minus"] = False
    return matplotlib.rcParams["font.family"]


def read_csv_any(path, **kw):
    """공공데이터 CSV는 cp949와 utf-8이 섞여 있어 둘 다 시도한다."""
    import pandas as pd
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, encoding=enc, **kw)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("csv", b"", 0, 1, f"인코딩을 알 수 없습니다: {path}")
