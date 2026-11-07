"""「2025 국민기초생활보장 사업안내」 PDF 전처리.

산출물(data/processed/):
  - nblsa_median_income_2025.csv        2025년 기준 중위소득(1~7인)
  - nblsa_selection_criteria_2025.csv   급여종류별 수급자 선정기준(생계 32%, 의료 40%, 주거 48%, 교육 50%)
  - nblsa_facility_benefit_2025.csv     보장시설 수급자 1인당 월 생계급여 지급기준(수급자 현원 구간별)
  - nblsa_rules.csv / .json             바톤 서비스에 쓰는 규정 문장과 쪽수(원문 발췌)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROCESSED, find_raw  # noqa: E402

MONEY = re.compile(r"\d{1,3}(?:,\d{3})+")

# 바톤에서 근거로 쓰는 규정: (키, 설명, 원문에서 찾을 문구)
RULES = [
    ("guardian", "발달장애인 등 의사무능력자는 후견인 지정을 우선 검토, 공공후견지원사업 이용",
     "필요시 발달장애인, 치매환자, 정신질환자 공공후견지원사업 이용"),
    ("benefit_manager", "후견인 지정이 어렵거나 오래 걸리면 급여관리자를 지정해 급여를 대신 관리",
     "급여관리자를 지정하여 급여를 대신 관리하도록 할 수 있으며"),
    ("ghh_not_protected", "장애인공동생활가정은 사회복지시설이지만 보장시설은 아님",
     "장애인공동생활가정은 「사회복지사업법」상 사회복지시설이나 보장시설은 아님"),
    ("protected_requirement", "보장시설 요건: 정부로부터 운영비와 인건비를 전액 지원받는 생활시설",
     "정부로부터 운영비와"),
    ("protected_scope_disabled", "장애인거주시설은 보장시설(장애인단기거주시설, 장애인공동생활가정 제외)",
     "거주시설, 장애인공동생활"),
    ("no_refusal", "보장시설은 위탁받은 급여를 정당한 사유 없이 거부할 수 없고 위반 시 300만원 이하 벌금 등",
     "정당한 사유 없이 거부할 수 없고"),
    ("separate_household", "보장시설 수급자는 별도 보장가구, 남은 가구원은 부양의무자로 처리",
     "보장시설 수급자는 별도 보장가구로 인정하여"),
    ("resident_registration", "보장시설 입소자는 주민등록을 보장기관으로 변경",
     "보장시설 입소자는 주민등록을 보장기관으로 변경하여야 함"),
    ("leave_refuse_support", "장애인시설 등에서 퇴소해 부양의무자가 부양을 거부·기피하면 지방생활보장위원회로 보장 필요성 검토",
     "장애인시설 등에서 퇴소하여 부양의무자가 부양을 거부하거나 기피하는 경우"),
    ("eligibility_needed", "수급자가 아닌 사람이 보장시설에 입소했다는 이유만으로는 수급자격이 생기지 않음",
     "입소하였다는 이유만으로는 수급자격"),
    ("benefit_target", "보장시설 생계급여 지급대상: 보장시설 수급자 선정기준(기준 중위소득 40% 이하) 절차로 결정된 입소자",
     "보장시설 수급자 선정기준(기준 중위소득 40% 이하)"),
    ("tier_by_recipients", "지급기준 구분은 수급자 현원(총정원·총현원·수급자정원 아님)",
     "지급기준 구분은 수급자 현원임"),
    ("no_payroll_use", "보장시설 생계급여는 종사자 인건비 등 관리운영비로 전용 불가",
     "시설 종사자 인건비"),
]


def printed_page(text: str) -> str:
    """쪽 아래·위에 찍힌 인쇄 쪽수(숫자 또는 로마숫자)를 찾는다."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for l in reversed(lines[-4:]):
        if re.fullmatch(r"\d{1,3}", l) or re.fullmatch(r"[ivxlc]{1,6}", l):
            return l
    for l in lines[:3]:
        m = re.match(r"^(\d{1,3})\s", l)
        if m:
            return m.group(1)
    return ""


def main():
    path = find_raw("nblsa_pdf")
    print(f"[사업안내] {path.name}")
    pdf = pdfplumber.open(path)
    texts = [(p.extract_text() or "") for p in pdf.pages]
    flat = [re.sub(r"\s+", "", t) for t in texts]

    # 1) 기준 중위소득, 급여종류별 선정기준
    for i, t in enumerate(texts[:60]):
        if "2025년도 기준 중위소득" in t and "급여종류별" in t:
            lines = t.split("\n")
            med = next(l for l in lines if l.startswith("기준 중위소득"))
            vals = [int(v.replace(",", "")) for v in MONEY.findall(med)]
            pd.DataFrame({"가구원수": range(1, 8), "기준중위소득_원": vals}).assign(
                출처=f"2025 국민기초생활보장 사업안내 {printed_page(t)}쪽(PDF {i + 1}쪽)").to_csv(
                PROCESSED / "nblsa_median_income_2025.csv", index=False, encoding="utf-8-sig")
            rows = []
            for name, pct in (("생계급여", 32), ("의료급여", 40), ("주거급여", 48), ("교육급여", 50)):
                k = next(j for j, l in enumerate(lines) if l.startswith(name + "수급자"))
                vals = [int(v.replace(",", "")) for v in MONEY.findall(lines[k + 1])]
                for n, v in enumerate(vals, 1):
                    rows.append({"급여": name, "기준중위소득_비율": pct, "가구원수": n, "선정기준_원": v})
            pd.DataFrame(rows).to_csv(PROCESSED / "nblsa_selection_criteria_2025.csv", index=False, encoding="utf-8-sig")
            print(f"  기준 중위소득·선정기준: PDF {i + 1}쪽")
            break

    # 2) 보장시설 수급자 1인당 월급여 지급기준
    for i, t in enumerate(texts):
        if i < 300 or "보장시설 수급자 1인당 월급여 지급기준" not in t:
            continue
        rows = []
        for label, pat in (("30인 미만", r"30인\s*미만\s*시설\s+([\d,]+)원"),
                           ("30인 이상~100인 미만", r"30인\s*이상\s*~\s*100인\s*미만\s*시설\s+([\d,]+)원"),
                           ("100인 이상~300인 미만", r"100인\s*이상\s*~\s*300인\s*미만\s*시설\s+([\d,]+)원"),
                           ("300인 이상", r"300인\s*이상\s*시설\s+([\d,]+)원")):
            m = re.search(pat, t)
            rows.append({"수급자현원_구간": label, "월급여액_원": int(m.group(1).replace(",", "")) if m else None})
        df = pd.DataFrame(rows).assign(출처=f"2025 국민기초생활보장 사업안내 {printed_page(t)}쪽(PDF {i + 1}쪽)")
        df.to_csv(PROCESSED / "nblsa_facility_benefit_2025.csv", index=False, encoding="utf-8-sig")
        print("  보장시설 생계급여 지급기준:\n" + df.to_string(index=False))
        break

    # 3) 규정 발췌와 쪽수
    out = []
    for key, desc, phrase in RULES:
        target = re.sub(r"\s+", "", phrase)
        hit = None
        for i, f in enumerate(flat):
            if target in f:
                hit = i
                if i > 250:  # 본문(제5·6편)을 우선
                    break
        if hit is None:
            out.append({"key": key, "설명": desc, "pdf쪽": None, "인쇄쪽": None, "원문발췌": "찾지 못함"})
            continue
        t = texts[hit]
        # 발췌: 띄어쓰기·줄바꿈이 섞여 있어도 찾도록 글자 사이에 공백을 허용해 원문 위치를 잡는다
        pat = r"\s*".join(re.escape(ch) for ch in target)
        m = re.search(pat, t)
        a, b = (m.start(), m.end()) if m else (0, 0)
        excerpt = re.sub(r"\s+", " ", t[max(0, a - 60): b + 80]).strip()
        out.append({"key": key, "설명": desc, "pdf쪽": hit + 1, "인쇄쪽": printed_page(t), "원문발췌": excerpt})
    pd.DataFrame(out).to_csv(PROCESSED / "nblsa_rules.csv", index=False, encoding="utf-8-sig")
    json.dump(out, open(PROCESSED / "nblsa_rules.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    found = sum(1 for o in out if o["pdf쪽"])
    print(f"  규정 발췌 {found}/{len(out)}건 쪽수 확인")


if __name__ == "__main__":
    main()
