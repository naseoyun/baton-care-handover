"""웹 데모(공무원 업무 화면)에 넣을 2026 API 현행 데이터 → web_demo/data_api.js

입력: data/api/api_facilities.csv, data/processed/facility_api_matched.csv, facility_api_match_report.csv,
      api_hiring_by_stage.csv  (python src/match_api_to_ilam.py 를 먼저 실행)
산출: window.BATON_API = {asof, api:[...], ilamOnly:[...], stage:{...}, report:{...}}
  api 행: [시도, 시군구, 시설명, 단계번호, 일람표거주시설번호(없으면 -1), 일람표연결(0/1), 채용중공고수, 전체공고수]
  단계번호: 0 장기거주, 1 단기거주, 2 공동생활가정, 3 주간이용
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import API_DIR, PROCESSED, ROOT  # noqa: E402
from match_api_to_ilam import api_sido  # noqa: E402

STAGES = ["장기거주", "단기거주", "공동생활가정", "주간이용"]


def main():
    need = [API_DIR / "api_facilities.csv", PROCESSED / "facility_api_matched.csv",
            PROCESSED / "facility_api_match_report.csv", PROCESSED / "api_hiring_by_stage.csv"]
    if not all(p.exists() for p in need):
        print("[건너뜀] API 결과가 없습니다. fetch_facility_api.py → match_api_to_ilam.py 순서로 먼저 실행하세요.")
        return
    api = pd.read_csv(need[0], dtype=str).drop_duplicates("srvInstId")
    m = pd.read_csv(need[1], dtype={"srvInstId": str})
    rep = pd.read_csv(need[2], index_col=0)
    st = pd.read_csv(need[3], index_col=0)
    asof = str(int(st["기준일"].iloc[0]))

    n_res = len(pd.read_csv(PROCESSED / "residential_facilities.csv"))
    m["행"] = range(len(m))  # 앞 n_res 행 = residential_facilities.csv 순서(웹 데모 FAC 번호와 같음)
    link = m.dropna(subset=["srvInstId"]).set_index("srvInstId")["행"]

    hire = {}
    jp = API_DIR / "api_jobs.csv"
    if jp.exists():
        j = pd.read_csv(jp, dtype=str)
        j["채용중"] = j["accpClseDe"].fillna("") >= asof
        hire = j.groupby("srvInstId").agg(a=("채용중", "sum"), t=("title", "size")).to_dict("index")

    rows = []
    for _, r in api.iterrows():
        parts = str(r["jrsdSggNm"]).split()
        sido = api_sido(r["jrsdSggNm"]) or (parts[0] if parts else "")
        sgg = parts[1] if len(parts) > 1 else "(도 소관)"
        if sido == "세종":
            sgg = "세종시"  # 일람표·등록장애인 통계 표기
        idx = link.get(r["srvInstId"])
        h = hire.get(r["srvInstId"], {"a": 0, "t": 0})
        rows.append([sido, sgg, r["fcltNm"], STAGES.index(r["바톤단계"]),
                     int(idx) if idx is not None and idx < n_res else -1, int(idx is not None), int(h["a"]), int(h["t"])])

    only = m[m["srvInstId"].isna()]
    ilam_only = [[r["소관시도"], r["소관시군구"], r["시설명"], STAGES.index(r["돌봄단계"])] for _, r in only.iterrows()]

    out = {
        "asof": asof,
        "api": rows,
        "ilamOnly": ilam_only,
        "stage": {k: {c: (None if pd.isna(v) else float(v)) for c, v in st.loc[k].items()} for k in st.index},
        "report": {k: {c: float(v) for c, v in rep.loc[k].items()} for k in rep.index},
    }
    dst = ROOT / "web_demo" / "data_api.js"
    dst.write_text("window.BATON_API=" + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"[웹 데이터] {dst.name}: API 시설 {len(rows):,}곳, 일람표에만 있는 시설 {len(ilam_only)}곳, 기준일 {asof}")


if __name__ == "__main__":
    main()
