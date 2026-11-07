"""CSV·엑셀·ZIP 원자료 전처리.

산출물(data/processed/):
  - registered_disabled_2025.csv       시군구별 등록장애인(전체·심한·심하지 않은, 성별) + 결합용 시군구 키
  - residential_trend_2020_2025.csv    장애인 거주시설 시설수·입소인원 추이(연도 × 지역 × 시설유형), 긴 형식
  - allowance_basic_long.csv           장애수당(기초생활보장) 수급자 2025.12~2026.9, 월 × 시군구 × 장애정도 × 장애유형
  - allowance_basic_monthly.csv        위 자료의 월 × 장애유형 합계
"""
from __future__ import annotations

import csv
import io
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROCESSED, SIDO_FULL, find_raw, sgg_key  # noqa: E402


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("csv", raw[:10], 0, 1, str(path))


def clean_registered():
    path = find_raw("registered_csv")
    rows = list(csv.reader(io.StringIO(_read_text(path))))
    year = rows[0][2]
    out = []
    for r in rows[3:]:
        if len(r) < 11:
            continue
        sido_full, sgg = r[0].strip(), r[1].strip()
        nums = [int(x) for x in r[2:11]]
        rec = {"기준연도": year, "시도명": sido_full, "시도": SIDO_FULL.get(sido_full, sido_full), "시군구_원자료": sgg,
               "전체": nums[0], "전체_남": nums[1], "전체_여": nums[2],
               "심한장애": nums[3], "심한장애_남": nums[4], "심한장애_여": nums[5],
               "심하지않은장애": nums[6], "심하지않은장애_남": nums[7], "심하지않은장애_여": nums[8]}
        out.append(rec)
    df = pd.DataFrame(out)
    nat = df[df["시도명"] == "전국"]
    sido = df[(df["시군구_원자료"] == "소계") & (df["시도명"] != "전국")]
    sgg = df[df["시군구_원자료"] != "소계"].copy()
    # 세종은 소계 한 줄뿐이라 시군구 행으로도 쓴다
    sej = sido[sido["시도"] == "세종"].copy()
    if len(sej) and not (sgg["시도"] == "세종").any():
        sej["시군구_원자료"] = "세종시"
        sgg = pd.concat([sgg, sej])
    sgg["시군구키"] = [sgg_key(s, g) for s, g in zip(sgg["시도"], sgg["시군구_원자료"])]
    sgg.to_csv(PROCESSED / "registered_disabled_2025.csv", index=False, encoding="utf-8-sig")
    sido.to_csv(PROCESSED / "registered_disabled_2025_sido.csv", index=False, encoding="utf-8-sig")
    check = int(sido["전체"].sum()) == int(nat["전체"].iloc[0])
    print(f"[등록장애인 {year}] 전국 {int(nat['전체'].iloc[0]):,}명, 심한 장애 {int(nat['심한장애'].iloc[0]):,}명, "
          f"시군구 {len(sgg[['시도', '시군구키']].drop_duplicates())}개(결합 키 기준), 시도 소계 합 = 전국: {check}")
    return sgg


def clean_trend():
    path = find_raw("trend_xlsx")
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    out = []
    for ws in wb.worksheets:
        rows = [r for r in ws.iter_rows(values_only=True) if any(v is not None for v in r)]
        hdr = next(r for r in rows if r[0] == "구분")
        regions = [c for c in hdr[2:] if c]
        src = next((str(r[0]).replace("\n", " ") for r in rows if r[0] and str(r[0]).startswith("*")), "")
        label = None
        for r in rows:
            if r[0] in ("시설 수", "입소인원"):
                ftype, metric = "합계", ("시설수" if r[0] == "시설 수" else "입소인원")
            elif r[0] and r[0] != "구분" and not str(r[0]).startswith("*") and r[1]:
                label = str(r[0]).replace("중중", "중증")
                ftype, metric = label, "시설수"
            elif r[0] is None and r[1] == "입소인원" and label:
                ftype, metric = label, "입소인원"
            else:
                continue
            for reg, v in zip(regions, r[2:2 + len(regions)]):
                if v is not None:
                    out.append({"연도": int(ws.title), "지역": reg, "시설유형": ftype, "항목": metric, "값": int(v),
                                "출처표기": src})
    df = pd.DataFrame(out)
    df.to_csv(PROCESSED / "residential_trend_2020_2025.csv", index=False, encoding="utf-8-sig")
    nat = df[(df["지역"] == "전국") & (df["시설유형"] == "합계") & (df["항목"] == "입소인원")].set_index("연도")["값"]
    print("[거주시설 추이] 전국 입소인원 " + ", ".join(f"{y} {v:,}" for y, v in nat.items()))
    return df


def clean_allowance():
    path = find_raw("allowance_zip")
    frames = []
    with zipfile.ZipFile(path) as z:
        for name in sorted(z.namelist()):
            if not name.lower().endswith(".csv"):
                continue
            raw = z.read(name)
            text = None
            for enc in ("cp949", "utf-8-sig"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            frames.append(pd.read_csv(io.StringIO(text)))
    df = pd.concat(frames, ignore_index=True)
    df.columns = ["통계연월", "시도명", "시군구명", "장애정도", "장애유형", "수급자수"]
    df.to_csv(PROCESSED / "allowance_basic_long.csv", index=False, encoding="utf-8-sig")
    monthly = df.pivot_table(index="통계연월", columns="장애유형", values="수급자수", aggfunc="sum").fillna(0).astype(int)
    monthly["합계"] = monthly.sum(axis=1)
    monthly.to_csv(PROCESSED / "allowance_basic_monthly.csv", encoding="utf-8-sig")
    last = monthly.index.max()
    print(f"[장애수당(기초)] {len(frames)}개월 {len(df):,}행, {last} 합계 {monthly.loc[last, '합계']:,}명 "
          f"(지적 {monthly.loc[last].get('지적', 0):,}, 자폐성 {monthly.loc[last].get('자폐성', 0):,})")
    return df


def main():
    clean_registered()
    clean_trend()
    try:
        clean_allowance()
    except FileNotFoundError as e:
        print(f"[건너뜀] {e}")


if __name__ == "__main__":
    main()
