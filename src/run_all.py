"""전체 파이프라인 실행: 원자료 → 전처리 → 지역 결합 → (API 매칭) → 시각화 → 노트북.

  python src/run_all.py              # 전부
  python src/run_all.py --skip-pdf   # PDF 전처리 결과가 이미 있으면 건너뛰기(빠름)
  python src/run_all.py --api        # 마지막에 OpenAPI 수집·매칭까지
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))
from common import PROCESSED, RAW_DIR  # noqa: E402


def step(title, script, *args):
    t = time.time()
    print(f"\n=== {title} ===")
    r = subprocess.run([sys.executable, str(SRC / script), *args], cwd=SRC.parent)
    if r.returncode != 0:
        print(f"[실패] {script} (종료코드 {r.returncode})")
        sys.exit(r.returncode)
    print(f"--- {time.time() - t:.0f}초")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-pdf", action="store_true")
    ap.add_argument("--api", action="store_true", help="OpenAPI 수집과 일람표 매칭까지 실행")
    a = ap.parse_args()
    print(f"원자료 폴더: {RAW_DIR}")
    if not (a.skip_pdf and (PROCESSED / "residential_facilities.csv").exists()):
        step("1. 일람표 PDF 전처리(수 분 걸림)", "parse_facility_pdf.py")
        step("2. 기초생활보장 사업안내 PDF 전처리", "parse_nblsa_pdf.py")
    step("3. CSV·엑셀·ZIP 전처리", "clean_tabular.py")
    step("4. 지역 패널 결합", "build_region_panel.py")
    if a.api:
        step("5. 사회복지시설정보 OpenAPI 수집", "fetch_facility_api.py")
    # 이미 받아 둔 API 결과(data/api/)가 있으면 매칭·웹 데이터는 항상 다시 만든다(없으면 각 스크립트가 건너뜀)
    step("6. API ↔ 일람표 연결, 현행화·채용 신호", "match_api_to_ilam.py")
    step("6-1. 웹 데모용 API 데이터", "build_web_api_data.py")
    step("7. 시각화", "visualize.py")
    step("8. 노트북 결과 갱신", "build_notebook.py")
    print("\n완료. data/processed, outputs/figures, notebooks 폴더를 확인하세요.")


if __name__ == "__main__":
    main()
