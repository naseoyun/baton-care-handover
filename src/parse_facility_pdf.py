"""「2025 장애인복지시설 일람표」(2024.12 기준) PDF 전처리.

산출물(data/processed/):
  - ilam_summary_residential.csv   총괄표(3쪽) 시도 × 거주시설 종류별 시설수·정원·현원
  - ilam_summary_community.csv     총괄표(4쪽) 시도별 지역사회재활시설 시설수(주간이용시설 포함)
  - residential_facilities.csv     거주시설 1,524곳 시설 단위 표(정원·현원·종사자·주소·설치신고일)
  - day_facilities.csv             장애인 주간이용시설 시설 단위 표(정원)
  - ilam_validation.csv            시설 목록 합계와 총괄표의 칸별 대조 결과

방법: PDF 표에는 선이 없고 셀 글자가 여러 줄로 나뉘어 있어서, 글자 좌표로 열 위치를 잡고
일련번호가 있는 줄을 기준으로 위아래 줄 조각을 같은 행으로 합친다.
"""
from __future__ import annotations

import re
import sys

import pandas as pd
import pdfplumber

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import PROCESSED, RES_TYPES, SIDO_FULL, SIDO_ORDER, find_raw  # noqa: E402

NUM = re.compile(r"^\d{1,4}$")
DATE = re.compile(r"\d{4}-\d{1,2}-?\d{0,2}")
SGG_RE = re.compile(r"^[가-힣]{1,6}(시|군|구)$")
PHONE = re.compile(r"\(?0\d{1,4}\)?-?\d{3,4}-\d{4}")


def _rows(words, tol=2.5):
    """같은 높이(top)의 글자를 한 줄로 묶는다."""
    rows = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if rows and abs(rows[-1][0]["top"] - w["top"]) <= tol:
            rows[-1].append(w)
        else:
            rows.append([w])
    return rows


def _words(page):
    return page.extract_words(x_tolerance=1.5, y_tolerance=2)


# ---------------------------------------------------------------- 총괄표
def parse_summaries(path):
    """총괄표는 PDF에서 90도 돌아간 쪽이라 pypdf의 layout 추출로 읽는다."""
    import logging
    import pypdf
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = pypdf.PdfReader(str(path))
    res, com = [], []
    for page in reader.pages[:10]:
        text = page.extract_text(extraction_mode="layout") or ""
        is_res = "거주시설" in text and "총괄표" in text and "지체장애" in text
        is_com = "지역사회재활시설" in text and "총괄표" in text and "복지관" in text
        if not (is_res or is_com):
            continue
        for line in text.split("\n"):
            parts = line.split()
            if not parts or parts[0] not in SIDO_ORDER + ["합계"]:
                continue
            nums = [p.replace(",", "") for p in parts[1:]]
            if not nums or not all(n.isdigit() for n in nums):
                continue
            nums = [int(n) for n in nums]
            if is_res and len(nums) == 27:
                row = {"시도": parts[0], "합계_시설수": nums[0], "합계_정원": nums[1], "합계_현원": nums[2]}
                for i, t in enumerate(RES_TYPES):
                    row[f"{t}_시설수"], row[f"{t}_정원"], row[f"{t}_현원"] = nums[3 + i * 3: 6 + i * 3]
                res.append(row)
            elif is_com and len(nums) >= 10:
                com.append({"시도": parts[0], "지역사회재활_소계": nums[0], "장애인복지관": nums[1],
                            "주간이용시설": nums[2], "장애인체육시설": nums[3], "수어통역센터": nums[4],
                            "시각장애인등생활지원센터": nums[5], "점자도서관": nums[6],
                            "점자도서및녹음서출판시설": nums[7], "장애인재활치료시설": nums[8],
                            "의료재활시설": nums[9]})
    return pd.DataFrame(res).drop_duplicates("시도"), pd.DataFrame(com).drop_duplicates("시도")


def _section_range(pdf, start_kw, end_kw, start_from=8):
    start = end = None
    for i in range(start_from, len(pdf.pages)):
        t = pdf.pages[i].extract_text() or ""
        if start is None and start_kw in t and "시도별" in t:
            start = i
        elif start is not None and end_kw in t and "시도별" in t:
            end = i
            break
    return start, end


# ---------------------------------------------------------------- 거주시설
def parse_residential(pdf):
    start, end = _section_range(pdf, "장애인 거주시설", "장애인 지역사회")
    items = []
    for pi in range(start, end):
        page = pdf.pages[pi]
        words = _words(page)
        rows = _rows(words)
        headers = []
        for r0 in rows:
            r = [w for w in r0 if w["x0"] < 400] or r0
            s = "".join(w["text"] for w in r)
            x0 = min(w["x0"] for w in r)
            t = min(w["top"] for w in r)
            if x0 < 200 and s in SIDO_FULL:
                items.append((pi, t - 0.01, "sido", SIDO_FULL[s]))
            elif x0 < 200 and len(r) <= 4:
                if s.startswith("장애유형별거주시설"):
                    items.append((pi, t - 0.01, "kind", "유형별"))
                elif s.startswith("중증장애인거주시설"):
                    items.append((pi, t - 0.01, "kind", "중증"))
                elif s.startswith("장애영유아거주시설"):
                    items.append((pi, t - 0.01, "kind", "영유아"))
                elif s.startswith("장애인단기거주시설") or s == "단기거주시설":
                    items.append((pi, t - 0.01, "kind", "단기"))
                elif s.startswith("장애인공동생활가정"):
                    items.append((pi, t - 0.01, "kind", "공동"))
                elif s.startswith("∙"):
                    sub = s[1:]
                    if "중증" in sub:
                        items.append((pi, t - 0.01, "kind", "중증"))
                    else:
                        items.append((pi, t - 0.01, "sub", sub))
            texts = [w["text"] for w in r0]
            if texts.count("정원") == 2 and texts.count("현원") == 2:
                headers.append(r0)

        def colx(name, near):
            c = [w for w in words if w["text"] == name and abs(w["top"] - near) < 20]
            return c[0]["x0"] if c else None

        tables = []
        for h in headers:
            nums = sorted([w for w in h if w["text"] in ("정원", "현원")], key=lambda w: w["x0"])
            top = h[0]["top"]
            tables.append(dict(top=top, c=[(w["x0"] + w["x1"]) / 2 for w in nums],
                               sgg=colx("시군구", top), date=colx("설치신고일", top), corp=colx("법인명", top)))
        for k, tb in enumerate(tables):
            tb["bottom"] = tables[k + 1]["top"] - 30 if k + 1 < len(tables) else page.height
            c = tb["c"]
            region = [w for w in words if tb["top"] + 4 < w["top"] < tb["bottom"]]
            anchors = []
            for r in _rows(region):
                ser = [w for w in r if w["x0"] < tb["sgg"] - 2 and NUM.match(w["text"])]
                nums = [w for w in r if any(abs((w["x0"] + w["x1"]) / 2 - cc) < 12 for cc in c)
                        and NUM.match(w["text"])]
                if ser and len(nums) == 4:
                    anchors.append((r[0]["top"], int(ser[0]["text"]), sorted(nums, key=lambda w: w["x0"])))
            for j, (t, ser, nums) in enumerate(anchors):
                lo = (anchors[j - 1][0] + t) / 2 if j > 0 else t - 12
                hi = (anchors[j + 1][0] + t) / 2 if j + 1 < len(anchors) else t + 12
                band = sorted([w for w in region if lo <= w["top"] < hi], key=lambda w: (round(w["top"]), w["x0"]))
                left = [w for w in band if tb["sgg"] - 4 <= w["x0"] < c[0] - 14]
                anc = [w for w in left if abs(w["top"] - t) < 2.5]
                sggw = anc[0] if anc else None
                name = "".join(w["text"] for w in left if w is not sggw)

                def col(a, b):
                    return " ".join(w["text"] for w in band if (a is None or w["x0"] >= a) and (b is None or w["x0"] < b))
                addr = col(c[3] + 12, tb["date"] - 10 if tb["date"] else None)
                addr = re.sub(r"\s+", " ", PHONE.sub(" ", addr)).strip()
                dm = DATE.search(col(tb["date"] - 10, tb["corp"] - 15 if tb["corp"] else None) if tb["date"] else "")
                items.append((pi, t, "row", dict(
                    pdf_page=pi + 1, 일련번호=ser, 소관시군구=sggw["text"] if sggw else "", 시설명=name,
                    입소정원=int(nums[0]["text"]), 입소현원=int(nums[1]["text"]),
                    종사자정원=int(nums[2]["text"]), 종사자현원=int(nums[3]["text"]),
                    소재지주소=addr, 설치신고일=dm.group(0) if dm else "",
                    법인명=col(tb["corp"] - 15, None).strip() if tb["corp"] else "")))
    items.sort(key=lambda x: (x[0], x[1]))
    sido = kind = sub = None
    out = []
    for _, _, typ, val in items:
        if typ == "sido":
            sido, kind, sub = val, None, None
        elif typ == "kind":
            kind, sub = val, None
        elif typ == "sub":
            sub = val
        else:
            t = kind
            if kind == "유형별":
                t = next((k for k in ("지체", "시각", "청각", "지적") if k in (sub or "")), None)
            out.append({"소관시도": sido, "시설종류": t, **val})
    df = pd.DataFrame(out)
    df["빈자리"] = df["입소정원"] - df["입소현원"]
    loc = df["소재지주소"].str.split().str[0].map(SIDO_FULL)
    df["소재지시도"] = loc
    if (df["소관시도"] == "세종").any():
        df.loc[df["소관시도"] == "세종", "소관시군구"] = "세종시"
    return df


# ---------------------------------------------------------------- 주간이용시설
KINDS = ["장애인복지관", "장애인주간이용시설", "장애인체육시설", "수어통역센터", "시각장애인등생활지원센터",
         "점자도서관", "점자도서및녹음서출판시설", "장애인재활치료시설"]


def parse_day(pdf):
    start, end = _section_range(pdf, "장애인 지역사회", "장애인 직업재활시설", start_from=100)
    items = []
    for pi in range(start, end):
        page = pdf.pages[pi]
        words = _words(page)
        for r0 in _rows(words):
            r = [w for w in r0 if w["x0"] < 400]
            if not r:
                continue
            s = "".join(w["text"] for w in r)
            x0 = min(w["x0"] for w in r)
            t = min(w["top"] for w in r)
            if x0 < 200 and s in SIDO_FULL:
                items.append((pi, t - 0.01, "sido", SIDO_FULL[s]))
            elif x0 < 200 and len(r) <= 4 and s.replace("∙", "") in KINDS:
                items.append((pi, t - 0.01, "kind", s.replace("∙", "")))
        hdr = [w for w in words if w["text"] == "설치신고일"]
        if not hdr:
            continue
        ht = hdr[0]["top"]

        def hx(name):
            c = [w for w in words if w["text"] == name and abs(w["top"] - ht) < 12]
            return c[0] if c else None
        hs, hn, ha, hj = hx("시군구"), hx("시설명"), hx("시설"), hx("정원")
        rows = []
        for r in _rows([w for w in words if w["top"] > ht + 4]):
            ser = [w for w in r if w["x0"] < 90 and NUM.match(w["text"])]
            dt = [w for w in r if DATE.search(w["text"]) and w["x0"] > hdr[0]["x0"] - 15]
            if ser and dt:
                rows.append(r[0]["top"])
        for j, t in enumerate(rows):
            lo = (rows[j - 1] + t) / 2 if j > 0 else t - 12
            hi = (rows[j + 1] + t) / 2 if j + 1 < len(rows) else t + 12
            band = sorted([w for w in words if lo <= w["top"] < hi], key=lambda w: (round(w["top"]), w["x0"]))
            anc = [w for w in band if abs(w["top"] - t) < 2.5]
            sgg = next((w["text"] for w in anc if hs and hs["x0"] - 6 <= w["x0"] < hs["x0"] + 25), "")
            name_lo = hn["x0"] - 36 if hn else 177
            name_hi = ha["x0"] - 35 if ha else 265
            name = "".join(w["text"] for w in band if name_lo <= w["x0"] < name_hi and w["text"] != "시설명")
            cap = next((int(w["text"]) for w in anc if hj and abs((w["x0"] + w["x1"]) / 2 - (hj["x0"] + hj["x1"]) / 2) < 14
                        and NUM.match(w["text"])), None)
            items.append((pi, t, "row", dict(pdf_page=pi + 1, 소관시군구=sgg, 시설명=name, 정원=cap)))
    items.sort(key=lambda x: (x[0], x[1]))
    sido = kind = None
    out = []
    for _, _, typ, val in items:
        if typ == "sido":
            sido, kind = val, None
        elif typ == "kind":
            kind = val
        elif kind == "장애인주간이용시설":
            out.append({"소관시도": sido, **val})
    df = pd.DataFrame(out)
    df.loc[df["소관시도"] == "세종", "소관시군구"] = "세종시"
    return df


# ---------------------------------------------------------------- 검증
def validate(res, summ):
    rows = []
    agg = res.groupby(["소관시도", "시설종류"]).agg(시설수=("시설명", "size"), 정원=("입소정원", "sum"),
                                                현원=("입소현원", "sum")).reset_index()
    for _, s in summ[summ["시도"] != "합계"].iterrows():
        for t in RES_TYPES:
            m = agg[(agg["소관시도"] == s["시도"]) & (agg["시설종류"] == t)]
            for metric in ("시설수", "정원", "현원"):
                got = int(m[metric].iloc[0]) if len(m) else 0
                exp = int(s[f"{t}_{metric}"])
                rows.append({"시도": s["시도"], "시설종류": t, "항목": metric, "총괄표": exp, "시설목록합계": got,
                             "일치": exp == got})
    return pd.DataFrame(rows)


def main():
    path = find_raw("ilam_pdf")
    print(f"[일람표] {path.name}")
    pdf = pdfplumber.open(path)
    summ_res, summ_com = parse_summaries(path)
    summ_res.to_csv(PROCESSED / "ilam_summary_residential.csv", index=False, encoding="utf-8-sig")
    summ_com.to_csv(PROCESSED / "ilam_summary_community.csv", index=False, encoding="utf-8-sig")
    print(f"  총괄표: 거주 {len(summ_res)}행, 지역사회재활 {len(summ_com)}행")

    res = parse_residential(pdf)
    res.to_csv(PROCESSED / "residential_facilities.csv", index=False, encoding="utf-8-sig")
    print(f"  거주시설 {len(res):,}곳, 정원 {res['입소정원'].sum():,}, 현원 {res['입소현원'].sum():,}")

    val = validate(res, summ_res)
    val.to_csv(PROCESSED / "ilam_validation.csv", index=False, encoding="utf-8-sig")
    print(f"  총괄표 대조: {val['일치'].sum()}/{len(val)}칸 일치")

    day = parse_day(pdf)
    day.to_csv(PROCESSED / "day_facilities.csv", index=False, encoding="utf-8-sig")
    cmp = day.groupby("소관시도").size().rename("목록").to_frame().join(
        summ_com.set_index("시도")["주간이용시설"].rename("총괄표"))
    print(f"  주간이용시설 목록 {len(day)}곳 (총괄표 {int(summ_com[summ_com['시도'] != '합계']['주간이용시설'].sum())}곳)")
    diff = cmp[cmp["목록"] != cmp["총괄표"]]
    if len(diff):
        print("  목록과 총괄표가 다른 시도:\n" + diff.to_string())


if __name__ == "__main__":
    main()
