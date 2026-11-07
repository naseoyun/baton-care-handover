"""시설(일람표) + 등록장애인(csv)을 시군구·시도 단위로 결합해 돌봄 공백 지표를 만든다.

산출물(data/processed/):
  - region_sgg_panel.csv   시군구별 수요(심한 장애 등록장애인)와 공급(유형별 거주시설·주간이용시설), 공백 표시
  - region_sido_panel.csv  시도별 정원·현원·빈자리·종사자 충원율·심한 장애 1천 명당 발달 관련 거주 정원
주의: 시설의 시군구는 '소관' 시군구이며 실제 소재지와 다를 수 있다. 수요 지표는 모든 장애유형의 심한 장애 인구다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DEV_TYPES, PROCESSED, RES_TYPES, SIDO_ORDER  # noqa: E402


def main():
    res = pd.read_csv(PROCESSED / "residential_facilities.csv")
    day = pd.read_csv(PROCESSED / "day_facilities.csv")
    reg = pd.read_csv(PROCESSED / "registered_disabled_2025.csv")

    reg_g = reg.groupby(["시도", "시군구키"], as_index=False)[["전체", "심한장애", "심하지않은장애"]].sum()
    res = res.rename(columns={"소관시도": "시도", "소관시군구": "시군구키"})
    day = day.rename(columns={"소관시도": "시도", "소관시군구": "시군구키"})

    cnt = res.pivot_table(index=["시도", "시군구키"], columns="시설종류", values="시설명", aggfunc="size", fill_value=0)
    cnt = cnt.reindex(columns=RES_TYPES, fill_value=0).add_suffix("_시설수")
    dev = res[res["시설종류"].isin(DEV_TYPES)].groupby(["시도", "시군구키"]).agg(
        발달관련_정원=("입소정원", "sum"), 발달관련_현원=("입소현원", "sum"))
    dayg = day.groupby(["시도", "시군구키"]).agg(주간이용시설_수=("시설명", "size"), 주간이용시설_정원=("정원", "sum"))

    panel = reg_g.set_index(["시도", "시군구키"]).join([cnt, dev, dayg]).fillna(0).reset_index()
    for c in panel.columns[2:]:
        panel[c] = panel[c].astype(int)
    panel["장기거주(지적·중증)_시설수"] = panel["지적_시설수"] + panel["중증_시설수"]
    panel["단기거주_없음"] = panel["단기_시설수"] == 0
    panel["주간이용_없음"] = panel["주간이용시설_수"] == 0
    panel["장기거주_없음"] = panel["장기거주(지적·중증)_시설수"] == 0
    panel["심한장애_1천명당_발달관련정원"] = (panel["발달관련_정원"] / panel["심한장애"] * 1000).round(1)
    unmatched = set(map(tuple, res[["시도", "시군구키"]].drop_duplicates().values)) - set(map(tuple, reg_g[["시도", "시군구키"]].values))
    panel.to_csv(PROCESSED / "region_sgg_panel.csv", index=False, encoding="utf-8-sig")

    g = res.groupby("시도").agg(시설수=("시설명", "size"), 정원=("입소정원", "sum"), 현원=("입소현원", "sum"),
                              종사자정원=("종사자정원", "sum"), 종사자현원=("종사자현원", "sum"))
    g["빈자리"] = g["정원"] - g["현원"]
    g["빈자리율(%)"] = (g["빈자리"] / g["정원"] * 100).round(1)
    g["종사자충원율(%)"] = (g["종사자현원"] / g["종사자정원"] * 100).round(1)
    sido = g.join(panel.groupby("시도").agg(심한장애=("심한장애", "sum"), 발달관련_정원=("발달관련_정원", "sum"),
                                         시군구수=("시군구키", "size"), 단기거주없는_시군구=("단기거주_없음", "sum")))
    sido["심한장애_1천명당_발달관련정원"] = (sido["발달관련_정원"] / sido["심한장애"] * 1000).round(1)
    sido = sido.reindex(SIDO_ORDER).reset_index()
    sido.to_csv(PROCESSED / "region_sido_panel.csv", index=False, encoding="utf-8-sig")

    n = len(panel)
    ns = int(panel["단기거주_없음"].sum())
    print(f"[지역 패널] 시군구 {n}개, 결합 안 된 시설 시군구 {len(unmatched)}개")
    print(f"  단기거주시설 없는 시군구 {ns}곳(심한 장애 {panel.loc[panel['단기거주_없음'], '심한장애'].sum():,}명), "
          f"그중 주간이용시설도 없는 곳 {int((panel['단기거주_없음'] & panel['주간이용_없음']).sum())}곳, "
          f"지적·중증 거주시설 없는 곳 {int(panel['장기거주_없음'].sum())}곳")
    lo, hi = sido.loc[sido["심한장애_1천명당_발달관련정원"].idxmin()], sido.loc[sido["심한장애_1천명당_발달관련정원"].idxmax()]
    print(f"  심한 장애 1천 명당 발달 관련 거주 정원: 최저 {lo['시도']} {lo['심한장애_1천명당_발달관련정원']}, "
          f"최고 {hi['시도']} {hi['심한장애_1천명당_발달관련정원']}")


if __name__ == "__main__":
    main()
