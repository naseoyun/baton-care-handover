"""전처리 결과 시각화 → outputs/figures/*.png

fig01  거주시설 입소인원·시설 수 추이(2020~2025)
fig02  시설 종류별 현원과 빈자리
fig03  시도별 심한 장애 1천 명당 발달 관련 거주 정원
fig04  시도별 거주시설 종사자 충원율
fig05  단기거주시설이 없는 시군구(심한 장애 인구 상위 15)
fig06  보장시설 수급자 1인당 월 생계급여 지급기준(2025)
fig07  시설 종류별 현원 규모 분포
fig08  장애수당(기초생활보장) 수급자 월별 추이 — 자료 검토용
fig09  돌봄 단계별 채용 중 시설 비율(API)
fig10  2024 일람표 vs 2026 API 현행화 비교
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import API_DIR, FIG_DIR, PROCESSED, RES_TYPE_NAME, SIDO_ORDER, setup_korean_font  # noqa: E402

INK, MUTED, GRID = "#16202d", "#596476", "#dbe0e7"
ACC, RELAY, OK = "#1d4ed0", "#d9560f", "#17845a"


def style(ax, title, sub=None):
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", color=INK, pad=22 if sub else 10)
    if sub:
        ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=9, color=MUTED, va="bottom")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)


def save(fig, name, source):
    fig.text(0.01, 0.005, "출처: " + source, fontsize=7.5, color=MUTED, ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(FIG_DIR / name, dpi=160)
    plt.close(fig)
    print(f"  {name}")


def fig01():
    t = pd.read_csv(PROCESSED / "residential_trend_2020_2025.csv")
    t = t[(t["지역"] == "전국") & (t["시설유형"] == "합계")].pivot(index="연도", columns="항목", values="값")
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.fill_between(t.index, t["입소인원"], 26000, color=ACC, alpha=.08)
    ax.plot(t.index, t["입소인원"], color=ACC, lw=2.5, marker="o")
    ax.scatter([t.index[-1]], [t["입소인원"].iloc[-1]], color=RELAY, s=70, zorder=5)
    for y, v in t["입소인원"].items():
        ax.annotate(f"{v:,}", (y, v), textcoords="offset points", xytext=(0, 9), ha="center", fontsize=9, color=INK)
    ax.set_ylim(26000, 29600)
    ax.set_xticks(t.index, [f"{y}\n{int(n):,}곳" for y, n in t["시설수"].items()])
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.grid(axis="y", color=GRID, lw=.8)
    d = (t["입소인원"].iloc[-1] - t["입소인원"].iloc[0]) / t["입소인원"].iloc[0] * 100
    style(ax, f"장애인 거주시설 입소인원 5년째 감소 ({d:.1f}%)", "전국 입소인원(명), 아래는 시설 수")
    save(fig, "fig01_residential_trend.png", "보건복지통계연보(2020~2023), 장애인복지시설 일람표 총괄표(2024·2025) — 제공 xlsx")


def fig02():
    r = pd.read_csv(PROCESSED / "residential_facilities.csv")
    g = r.groupby("시설종류")[["입소정원", "입소현원"]].sum()
    g["빈자리"] = g["입소정원"] - g["입소현원"]
    g = g.sort_values("입소정원")
    fig, ax = plt.subplots(figsize=(8, 4.4))
    labels = [RES_TYPE_NAME[t].replace(" 거주시설", "") for t in g.index]
    ax.barh(labels, g["입소현원"], color=ACC, alpha=.35, label="현원")
    ax.barh(labels, g["빈자리"], left=g["입소현원"], color=RELAY, label="빈자리(정원−현원)")
    for i, (t, row) in enumerate(g.iterrows()):
        ax.text(row["입소정원"] + 150, i, f"{row['빈자리']:,}석 ({row['빈자리'] / row['입소정원'] * 100:.1f}%)",
                va="center", fontsize=9, color=INK)
    ax.set_xlim(0, g["입소정원"].max() * 1.28)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    tot = g.sum()
    style(ax, f"빈자리 {int(tot['빈자리']):,}석 — 정원 {int(tot['입소정원']):,} 중 {tot['빈자리'] / tot['입소정원'] * 100:.1f}%",
          "시설 종류별 입소 현원과 빈자리, 2024.12")
    save(fig, "fig02_vacancy_by_type.png", "2025 장애인복지시설 일람표(시설 1,524곳 추출, 총괄표와 대조 일치)")


def fig03():
    s = pd.read_csv(PROCESSED / "region_sido_panel.csv").set_index("시도").reindex(SIDO_ORDER)
    v = s["심한장애_1천명당_발달관련정원"]
    fig, ax = plt.subplots(figsize=(9, 4.2))
    colors = [RELAY if x == v.min() else ACC for x in v]
    ax.bar(v.index, v.values, color=colors, alpha=.9)
    for i, x in enumerate(v.values):
        ax.text(i, x + .6, f"{x:.1f}", ha="center", fontsize=8.5, color=INK)
    ax.axhline(s["발달관련_정원"].sum() / s["심한장애"].sum() * 1000, color=MUTED, ls="--", lw=1)
    nat = s["발달관련_정원"].sum() / s["심한장애"].sum() * 1000
    ax.text(-0.45, nat + .8, f"전국 {nat:.1f}", fontsize=8.5, color=MUTED, ha="left")
    ax.grid(axis="y", color=GRID, lw=.8)
    style(ax, f"지역마다 {v.max() / v.min():.1f}배 차이 나는 발달 관련 거주 정원",
          "심한 장애 등록장애인 1천 명당 정원(지적·중증·단기·공동생활가정). 수요 지표는 모든 장애유형 포함")
    save(fig, "fig03_supply_per_1000_severe.png", "2025 장애인복지시설 일람표(2024.12), 시군구별 등록장애인수(2025)")


def fig04():
    s = pd.read_csv(PROCESSED / "region_sido_panel.csv").set_index("시도").reindex(SIDO_ORDER)
    v = s["종사자충원율(%)"]
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(v.index, v.values, color=[RELAY if x < 90 else ACC for x in v], alpha=.9)
    ax.axhline(100, color=OK, lw=1.2)
    for i, x in enumerate(v.values):
        ax.text(i, x + .4, f"{x:.1f}", ha="center", fontsize=8.5, color=INK)
    ax.set_ylim(75, 104)
    ax.grid(axis="y", color=GRID, lw=.8)
    r = pd.read_csv(PROCESSED / "residential_facilities.csv")
    short = (r["종사자현원"] < r["종사자정원"]).sum()
    style(ax, f"거주시설 종사자 {int((r['종사자정원'] - r['종사자현원']).sum()):,}명 결원, {short}곳이 정원 미달",
          "시도별 종사자 현원 ÷ 정원(%), 주황은 90% 미만")
    save(fig, "fig04_staff_fill_rate.png", "2025 장애인복지시설 일람표(2024.12)")


def fig05():
    p = pd.read_csv(PROCESSED / "region_sgg_panel.csv")
    g = p[p["단기거주_없음"]].sort_values("심한장애", ascending=False).head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 5.2))
    lab = g["시도"] + " " + g["시군구키"]
    ax.barh(lab, g["심한장애"], color=[RELAY if d == 0 else ACC for d in g["주간이용시설_수"]], alpha=.9)
    for i, (_, r) in enumerate(g.iterrows()):
        ax.text(r["심한장애"] + 150, i, f"{r['심한장애']:,}명 · 주간이용 {r['주간이용시설_수']}곳", va="center", fontsize=8.5)
    ax.set_xlim(0, g["심한장애"].max() * 1.45)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    n = int(p["단기거주_없음"].sum())
    style(ax, f"단기거주시설이 없는 시군구 {n}곳 (전체 {len(p)}곳)",
          "심한 장애 등록장애인이 많은 순 상위 15곳, 주황은 주간이용시설도 없는 곳 (소관 시군구 기준)")
    save(fig, "fig05_no_short_stay_sgg.png", "2025 장애인복지시설 일람표(2024.12), 시군구별 등록장애인수(2025)")


def fig06():
    b = pd.read_csv(PROCESSED / "nblsa_facility_benefit_2025.csv")
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    ax.bar(b["수급자현원_구간"], b["월급여액_원"], color=ACC, alpha=.9, width=.55)
    for i, v in enumerate(b["월급여액_원"]):
        ax.text(i, v + 600, f"{v:,}원", ha="center", fontsize=9, color=INK)
    ax.set_ylim(300000, 362000)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v / 10000:.0f}만"))
    ax.grid(axis="y", color=GRID, lw=.8)
    style(ax, "보장시설 수급자 1인당 월 생계급여: 규모 구간만 있다",
          "구간 기준은 수급자 현원, 돌봄 난이도 기준 없음, 인건비 전용 불가 (세로축 30만 원부터)")
    save(fig, "fig06_facility_benefit_tiers.png", b["출처"].iloc[0])


def fig07():
    r = pd.read_csv(PROCESSED / "residential_facilities.csv")
    order = ["공동", "단기", "지적", "중증"]
    data = [r.loc[r["시설종류"] == t, "입소현원"] for t in order]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    bp = ax.boxplot(data, orientation="horizontal", patch_artist=True, widths=.5,
                    medianprops=dict(color=RELAY, lw=2), flierprops=dict(markersize=3, markeredgecolor=MUTED))
    for b in bp["boxes"]:
        b.set(facecolor=ACC, alpha=.25, edgecolor=ACC)
    ax.set_yticks(range(1, len(order) + 1), [f"{RES_TYPE_NAME[t].replace(' 거주시설', '')} ({len(d)}곳)" for t, d in zip(order, data)])
    for i, d in enumerate(data, 1):
        ax.text(d.max() + 3, i, f"중앙값 {int(d.median())}명", va="center", fontsize=8.5, color=INK)
    ax.axvline(30, color=MUTED, ls=":", lw=1)
    ax.text(31, 0.62, "현원 30인(생계급여 구간 경계)", fontsize=8, color=MUTED)
    ax.grid(axis="x", color=GRID, lw=.8)
    style(ax, "시설 종류별 현원 규모", "발달 관련 4개 유형의 시설당 입소 현원 분포")
    save(fig, "fig07_facility_size.png", "2025 장애인복지시설 일람표(2024.12)")


def fig08():
    p = PROCESSED / "allowance_basic_monthly.csv"
    if not p.exists():
        print("  fig08 건너뜀(장애수당 자료 없음)")
        return
    m = pd.read_csv(p, index_col=0)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    x = [f"{str(i)[:4]}.{str(i)[4:]}" for i in m.index]
    ax.plot(x, m["합계"], color=ACC, lw=2, marker="o")
    ax2 = ax.twinx()
    ax2.bar(x, m.get("자폐성", 0), color=RELAY, alpha=.5, width=.4)
    ax2.set_ylim(0, max(1, m.get("자폐성", pd.Series([0])).max()) * 6)
    ax2.set_ylabel("자폐성(막대)", color=RELAY, fontsize=8.5)
    ax.set_zorder(ax2.get_zorder() + 1)  # 선이 막대 위에 보이게
    ax.patch.set_visible(False)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.grid(axis="y", color=GRID, lw=.8)
    last = m.iloc[-1]
    style(ax, f"장애수당(기초) 수급자 {int(last['합계']):,}명 중 자폐성 {int(last.get('자폐성', 0))}명",
          "발달장애 수요 지표로 쓰기 어려운 이유: 자폐성 장애인은 대부분 장애인연금 대상")
    for s in ("top",):
        ax2.spines[s].set_visible(False)
    save(fig, "fig08_allowance_review.png", "장애수당 장애정도별 장애유형별 수급자수(기초생활보장), 2025.12~2026.9")


STAGE_ORDER = ["장기거주", "단기거주", "공동생활가정", "주간이용"]


def fig09():
    p = PROCESSED / "api_hiring_by_stage.csv"
    if not p.exists():
        print("  fig09 건너뜀(python src/match_api_to_ilam.py 실행 전)")
        return
    d = pd.read_csv(p, index_col=0)
    asof = str(int(d["기준일"].iloc[0]))
    d = d.loc[STAGE_ORDER]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    bars = ax.barh(d.index[::-1], d["채용중비율(%)"][::-1], color=[ACC if i else RELAY for i in (1, 1, 1, 0)])
    for b, (_, r) in zip(bars, d[::-1].iterrows()):
        ax.text(b.get_width() + 0.3, b.get_y() + b.get_height() / 2,
                f"{r['채용중비율(%)']:.1f}%  ({int(r['채용중시설'])}/{int(r['시설수'])}곳, 공고 {int(r['공고수'])}건)",
                va="center", fontsize=9, color=INK)
    ax.set_xlim(0, d["채용중비율(%)"].max() * 1.9)
    ax.set_xlabel("마감 전 구인 공고가 있는 시설 비율(%)", fontsize=9, color=MUTED)
    style(ax, "장기거주시설 6곳 중 1곳은 지금 사람을 구하는 중",
          f"돌봄 단계별 채용 중 시설 비율, 기준일 {asof[:4]}.{asof[4:6]}.{asof[6:]} (API 2,384곳 전수 조회)")
    save(fig, "fig09_api_hiring_by_stage.png", "한국사회보장정보원 사회복지시설정보 OpenAPI(시설별 구인정보)")


def fig10():
    p = PROCESSED / "facility_api_match_report.csv"
    if not p.exists():
        print("  fig10 건너뜀(python src/match_api_to_ilam.py 실행 전)")
        return
    d = pd.read_csv(p, index_col=0).loc[STAGE_ORDER]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    y = range(len(d))[::-1]
    ax.barh(list(y), d["연결"], color=OK, label="2024 일람표와 2026 API 모두 확인")
    ax.barh(list(y), d["일람표만"], left=d["연결"], color=MUTED, label="2024 일람표에만 있음")
    ax.barh(list(y), d["API만"], left=d["연결"] + d["일람표만"], color=RELAY, label="2026 API에만 있음")
    ax.set_yticks(list(y), d.index)
    for yy, (_, r) in zip(y, d.iterrows()):
        ax.text(r["연결"] + r["일람표만"] + r["API만"] + 8, yy, f"이름 연결 {r['연결률_일람표기준(%)']:.1f}%",
                va="center", fontsize=9, color=INK)
    ax.set_xlim(0, (d["연결"] + d["일람표만"] + d["API만"]).max() * 1.22)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3, fontsize=8.5, frameon=False)
    style(ax, "2년 사이 시설 목록이 바뀌었다: PDF 대신 API로 현행화",
          "돌봄 단계별 시설 수: 2024.12 일람표(PDF) vs 2026.11 API, 같은 시도·단계 안 시설명으로 연결")
    save(fig, "fig10_api_currency.png", "보건복지부 2025 장애인복지시설 일람표, 한국사회보장정보원 사회복지시설정보 OpenAPI")


def main():
    font = setup_korean_font()
    print(f"[시각화] 글꼴: {font}")
    for f in (fig01, fig02, fig03, fig04, fig05, fig06, fig07, fig08, fig09, fig10):
        f()


if __name__ == "__main__":
    main()
