"""API(2026 현행) 시설과 일람표(2024.12) 시설을 연결하고, 현행화·채용 신호를 정리한다.

입력: data/api/api_facilities.csv, api_jobs.csv(있으면), data/processed/residential_facilities.csv, day_facilities.csv
산출(data/processed/):
  - facility_api_matched.csv        일람표 시설 1행 = 1곳, 연결된 API 시설(서비스기관ID)·채용 공고 수
  - facility_api_only.csv           API에는 있으나 일람표와 이름으로 연결되지 않은 시설(신규·명칭 변경 후보)
  - facility_api_match_report.csv   돌봄 단계별 연결 현황
  - api_hiring_by_stage.csv         돌봄 단계별 채용 중 시설 비율·공고 수·공고 월급 하한 중앙값
  - api_hiring_by_sido.csv          시도별 채용 중 시설 비율
연결 규칙: 같은 시도 + 같은 돌봄 단계 안에서 ① 정규화한 시설명이 같으면 연결 ② 없으면 한쪽 이름이 다른 쪽을
포함(3글자 이상)할 때 연결. 한 시설은 한 번만 연결한다(1:1).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import API_DIR, PROCESSED, SIDO_FULL  # noqa: E402

STAGE_OF_ILAM = {"지체": "장기거주", "시각": "장기거주", "청각": "장기거주", "지적": "장기거주", "중증": "장기거주",
                 "영유아": "장기거주", "단기": "단기거주", "공동": "공동생활가정", "주간이용": "주간이용"}
GWANGJU_GU = {"동구", "서구", "남구", "북구", "광산구"}
DROP = ["시설명", "주간보호", "주간이용", "단기보호", "사회복지법인", "재단법인", "사단법인", "장애인", "공동생활가정", "단기거주시설", "단기보호센터", "단기보호시설",
        "주간보호센터", "주간보호시설", "주간이용시설", "거주시설", "그룹홈", "시설", "센터", "의집", "집"]
CARE_JOBS = ["생활재활교사", "생활지도원", "사회재활교사", "재활교사", "보육", "요양보호사", "활동지원"]


def norm(name: str) -> str:
    s = str(name).translate(str.maketrans({"Ⅰ": "1", "Ⅱ": "2", "Ⅲ": "3", "Ⅳ": "4", "Ⅴ": "5"}))
    s = re.sub(r"\((\d)\)", r"\1", s)  # (2) → 2
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s)
    s = re.sub(r"[^가-힣A-Za-z0-9]", "", s)
    for w in DROP:
        s = s.replace(w, "")
    return s


def contains(a: str, b: str) -> bool:
    """짧은 이름이 긴 이름에 포함되고, 짧은 쪽이 4글자 이상이거나 길이 비율이 0.75 이상일 때만 같은 곳으로 본다."""
    if not a or not b:
        return False
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 3 and short in long_ and (len(short) >= 4 or len(short) / len(long_) >= 0.75)


def api_sido(sgg_full: str) -> str | None:
    parts = str(sgg_full).split()
    if not parts:
        return None
    if parts[0] == "전남광주통합특별시":  # 2026 통합 이후 표기 → 일람표(2024) 기준으로 나눔
        return "광주" if len(parts) > 1 and parts[1] in GWANGJU_GU else "전남"
    return SIDO_FULL.get(parts[0])


def wage_floor(text: str):
    m = re.search(r"([\d,]{7,})\s*~", str(text))
    v = int(m.group(1).replace(",", "")) if m else 0
    return v if v >= 1_000_000 else None  # 0원·시급 표기는 제외


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--asof", default=None, help="채용 중 판단 기준일 YYYYMMDD(기본: 공고 파일 수정일)")
    args = ap.parse_args()
    src = API_DIR / "mock" if args.mock else API_DIR
    fpath = src / "api_facilities.csv"
    if not fpath.exists():
        print(f"[건너뜀] {fpath} 가 없습니다. 먼저 python src/fetch_facility_api.py 를 실행하세요.")
        return
    sfx = "_mock" if args.mock else ""

    api = pd.read_csv(fpath, dtype=str)
    api["시도"] = api["jrsdSggNm"].map(api_sido)
    api["키"] = api["fcltNm"].map(norm)
    api = api.drop_duplicates("srvInstId")

    res = pd.read_csv(PROCESSED / "residential_facilities.csv")
    day = pd.read_csv(PROCESSED / "day_facilities.csv").rename(columns={"정원": "입소정원"}).assign(시설종류="주간이용")
    il = pd.concat([res, day], ignore_index=True)
    il["돌봄단계"] = il["시설종류"].map(STAGE_OF_ILAM)
    il["키"] = il["시설명"].map(norm)
    il["srvInstId"] = None
    il["연결방법"] = None

    used = set()
    for method in ("이름 일치", "이름 포함"):
        for (sd, st), g in il[il["srvInstId"].isna()].groupby(["소관시도", "돌봄단계"]):
            cand = api[(api["시도"] == sd) & (api["바톤단계"] == st) & ~api["srvInstId"].isin(used)]
            if cand.empty:
                continue
            for i, r in g.iterrows():
                k = r["키"]
                if not k:
                    continue
                if method == "이름 일치":
                    hit = cand[cand["키"] == k]
                else:
                    hit = cand.loc[cand["키"].map(lambda x: contains(x, k)).astype(bool)]
                hit = hit[~hit["srvInstId"].isin(used)]
                if len(hit):
                    sid = hit.iloc[0]["srvInstId"]
                    il.at[i, "srvInstId"], il.at[i, "연결방법"] = sid, method
                    used.add(sid)

    # 채용 공고
    jobs_path = src / "api_jobs.csv"
    hire = pd.DataFrame(columns=["srvInstId", "공고수", "채용중공고수", "월급하한_중앙값"])
    if jobs_path.exists() and jobs_path.stat().st_size > 5:
        jobs = pd.read_csv(jobs_path, dtype=str)
        asof = args.asof or pd.Timestamp.fromtimestamp(jobs_path.stat().st_mtime).strftime("%Y%m%d")
        # 공고에는 요청한 시설의 서비스기관ID(srvInstId)와 바톤단계가 함께 들어 있다
        if "srvInstId" not in jobs or jobs["srvInstId"].isna().all():
            jobs = jobs.merge(api[["fcltCd", "srvInstId"]].dropna().drop_duplicates("fcltCd"),
                              left_on="요청_시설코드", right_on="fcltCd", how="left", suffixes=("_x", ""))
        sid_col = "srvInstId"
        jobs["채용중"] = jobs["accpClseDe"].fillna("") >= asof
        jobs["돌봄직종"] = jobs["relateJssfc"].fillna("").str.contains("|".join(CARE_JOBS)) | \
            jobs["title"].fillna("").str.contains("|".join(CARE_JOBS))
        jobs["월급하한"] = jobs["wageCond"].map(wage_floor)
        hire = jobs.groupby(sid_col).agg(공고수=("title", "size"), 채용중공고수=("채용중", "sum"),
                                       돌봄직종공고수=("돌봄직종", "sum"),
                                       월급하한_중앙값=("월급하한", "median")).reset_index().rename(columns={sid_col: "srvInstId"})
        api = api.merge(hire, on="srvInstId", how="left")
        for c in ("공고수", "채용중공고수", "돌봄직종공고수"):
            api[c] = api[c].fillna(0).astype(int)
        api["채용중"] = api["채용중공고수"] > 0

        st = api.groupby("바톤단계").agg(시설수=("srvInstId", "size"), 채용중시설=("채용중", "sum"),
                                     공고수=("공고수", "sum"), 돌봄직종공고=("돌봄직종공고수", "sum"))
        st["채용중비율(%)"] = (st["채용중시설"] / st["시설수"] * 100).round(1)
        cw = jobs[jobs["돌봄직종"] & jobs["월급하한"].notna()]
        st = st.join(cw.groupby("바톤단계")["월급하한"].agg(["median", "size"])
                     .rename(columns={"median": "돌봄직종_월급하한_중앙값", "size": "월급표기_공고수"}))
        st.loc["전체"] = [st["시설수"].sum(), st["채용중시설"].sum(), st["공고수"].sum(), st["돌봄직종공고"].sum(),
                        round(st["채용중시설"].sum() / st["시설수"].sum() * 100, 1),
                        cw["월급하한"].median(), len(cw)]
        st.assign(기준일=asof).to_csv(PROCESSED / f"api_hiring_by_stage{sfx}.csv", encoding="utf-8-sig")
        sd = api.groupby("시도").agg(시설수=("srvInstId", "size"), 채용중시설=("채용중", "sum"))
        sd["채용중비율(%)"] = (sd["채용중시설"] / sd["시설수"] * 100).round(1)
        sd.assign(기준일=asof).to_csv(PROCESSED / f"api_hiring_by_sido{sfx}.csv", encoding="utf-8-sig")
        print(f"[채용 신호 {asof}] 시설 {len(api):,}곳 중 채용 중 {int(api['채용중'].sum())}곳 "
              f"({api['채용중'].mean() * 100:.1f}%), 공고 {len(jobs)}건, 돌봄직종 월급 하한 중앙값 "
              f"{cw['월급하한'].median():,.0f}원({len(cw)}건)")

    keep = ["srvInstId", "fcltNm", "fcltCd", "종류상세명", "jrsdSggNm"] + [c for c in ("공고수", "채용중공고수", "채용중") if c in api]
    m = il.merge(api[keep], on="srvInstId", how="left")
    m.drop(columns=["키"]).to_csv(PROCESSED / f"facility_api_matched{sfx}.csv", index=False, encoding="utf-8-sig")
    api_only = api[~api["srvInstId"].isin(used)]
    api_only.drop(columns=["키"]).to_csv(PROCESSED / f"facility_api_only{sfx}.csv", index=False, encoding="utf-8-sig")

    rep = pd.DataFrame({
        "일람표_2024": il.groupby("돌봄단계").size(),
        "API_2026": api.groupby("바톤단계").size(),
        "연결": il[il["srvInstId"].notna()].groupby("돌봄단계").size(),
    }).fillna(0).astype(int)
    rep["일람표만"] = rep["일람표_2024"] - rep["연결"]
    rep["API만"] = rep["API_2026"] - rep["연결"]
    rep["연결률_일람표기준(%)"] = (rep["연결"] / rep["일람표_2024"] * 100).round(1)
    rep.loc["합계"] = rep.sum(numeric_only=True)
    rep.loc["합계", "연결률_일람표기준(%)"] = round(rep.loc["합계", "연결"] / rep.loc["합계", "일람표_2024"] * 100, 1)
    rep.to_csv(PROCESSED / f"facility_api_match_report{sfx}.csv", encoding="utf-8-sig")
    print(rep.to_string())


if __name__ == "__main__":
    main()
