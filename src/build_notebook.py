"""notebooks/baton_데이터_탐색.ipynb 를 만들고, 각 셀을 실행한 결과(표·그래프)를 함께 저장한다.
VS Code에서 노트북을 열면 실행하지 않아도 결과가 보이고, Jupyter 확장으로 다시 실행할 수 있다.
"""
from __future__ import annotations

import ast
import base64
import contextlib
import io
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT  # noqa: E402

NB = ROOT / "notebooks" / "baton_데이터_탐색.ipynb"

CELLS = [
    ("md", """# 바톤 — 공공데이터 전처리·탐색 노트북

발달장애인 **돌봄 인계 플랫폼 ‘바톤’**에 들어가는 데이터를 원자료에서 어떻게 만들었는지 보여 주는 노트북입니다.

| 원자료 | 전처리 결과 |
|---|---|
| 2025 장애인복지시설 일람표(PDF, 2024.12 기준) | 거주시설 1,524곳·주간이용시설 855곳 시설 단위 표, 총괄표 대조 |
| 2025 국민기초생활보장 사업안내(PDF) | 기준 중위소득, 급여 선정기준, 보장시설 생계급여 기준, 규정 발췌(쪽수) |
| 시군구별 등록장애인수(CSV, 2025) | 시군구 결합 키를 붙인 수요 표 |
| 특광역시 장애인거주시설 현황(xlsx, 2020~2025) | 연도 × 지역 × 시설유형 긴 형식 |
| 장애수당(기초생활보장) 수급자(ZIP, 2025.12~2026.9) | 월별 통합 표 — 검토 후 서비스 지표에서는 제외 |
| 사회복지시설정보 OpenAPI | `src/fetch_facility_api.py` 실행 후 채워짐 |

> 다시 실행하려면 위쪽의 **Run All**을 누르세요. 먼저 `python src/run_all.py` 로 전처리 결과를 만들어 두어야 합니다."""),
    ("code", """import sys, pandas as pd, matplotlib.pyplot as plt
from pathlib import Path
ROOT = Path.cwd() if (Path.cwd() / 'src').exists() else Path.cwd().parent
sys.path.insert(0, str(ROOT / 'src'))
from common import PROCESSED, API_DIR, setup_korean_font, RES_TYPE_NAME, SIDO_ORDER
setup_korean_font()
pd.set_option('display.max_columns', 30); pd.set_option('display.width', 200)
print('전처리 폴더:', PROCESSED)"""),
    ("md", "## 1. 일람표 PDF → 시설 단위 표\n시설 목록에서 뽑은 값을 같은 문서 3쪽 총괄표(시도 17 × 종류 8 × 시설수·정원·현원 = 408칸)와 맞춰 봅니다."),
    ("code", """res = pd.read_csv(PROCESSED / 'residential_facilities.csv')
val = pd.read_csv(PROCESSED / 'ilam_validation.csv')
print(f"거주시설 {len(res):,}곳 | 정원 {res['입소정원'].sum():,} | 현원 {res['입소현원'].sum():,} | 빈자리 {res['빈자리'].sum():,}")
print(f"총괄표 대조: {val['일치'].sum()} / {len(val)} 칸 일치")
res.head(8)"""),
    ("code", """g = res.groupby('시설종류').agg(시설수=('시설명','size'), 정원=('입소정원','sum'), 현원=('입소현원','sum'),
                             종사자정원=('종사자정원','sum'), 종사자현원=('종사자현원','sum'))
g['빈자리'] = g['정원'] - g['현원']; g['빈자리율(%)'] = (g['빈자리']/g['정원']*100).round(1)
g['종사자충원율(%)'] = (g['종사자현원']/g['종사자정원']*100).round(1)
g.index = [RES_TYPE_NAME[t] for t in g.index]
g.sort_values('정원', ascending=False)"""),
    ("code", """from IPython.display import Image, display
display(Image(filename=str(ROOT/'outputs/figures/fig02_vacancy_by_type.png')))"""),
    ("md", "## 2. 주간이용시설(낮 돌봄)\n일람표 3장 지역사회재활시설 중 ‘장애인 주간이용시설’ 표를 뽑아 4쪽 총괄표의 시도별 개수와 맞춥니다."),
    ("code", """day = pd.read_csv(PROCESSED / 'day_facilities.csv')
com = pd.read_csv(PROCESSED / 'ilam_summary_community.csv').set_index('시도')
chk = day.groupby('소관시도').size().rename('목록').to_frame().join(com['주간이용시설'].rename('총괄표'))
chk['일치'] = chk['목록'] == chk['총괄표']
print(f"주간이용시설 {len(day)}곳, 시도별 일치 {chk['일치'].sum()}/{len(chk)}")
chk.T"""),
    ("md", "## 3. 거주시설 추이(xlsx)"),
    ("code", """t = pd.read_csv(PROCESSED / 'residential_trend_2020_2025.csv')
t[(t['지역']=='전국')].pivot_table(index='시설유형', columns='연도', values='값', aggfunc='sum').loc[:, :]"""),
    ("code", """display(Image(filename=str(ROOT/'outputs/figures/fig01_residential_trend.png')))"""),
    ("md", "## 4. 지역별 돌봄 공백 (일람표 + 등록장애인 결합)\n시설의 시군구는 **소관** 기준이고, 수요 지표(심한 장애 등록장애인)는 모든 장애유형을 포함합니다."),
    ("code", """sido = pd.read_csv(PROCESSED / 'region_sido_panel.csv')
sido[['시도','시설수','정원','현원','빈자리율(%)','종사자충원율(%)','심한장애','발달관련_정원','심한장애_1천명당_발달관련정원','단기거주없는_시군구','시군구수']]"""),
    ("code", """display(Image(filename=str(ROOT/'outputs/figures/fig03_supply_per_1000_severe.png')))
display(Image(filename=str(ROOT/'outputs/figures/fig04_staff_fill_rate.png')))"""),
    ("code", """p = pd.read_csv(PROCESSED / 'region_sgg_panel.csv')
print(f"단기거주시설 없는 시군구: {p['단기거주_없음'].sum()} / {len(p)}  (심한 장애 {p.loc[p['단기거주_없음'],'심한장애'].sum():,}명)")
print(f"단기거주·주간이용 둘 다 없는 시군구: {(p['단기거주_없음'] & p['주간이용_없음']).sum()}")
p[p['단기거주_없음']].sort_values('심한장애', ascending=False)[['시도','시군구키','심한장애','주간이용시설_수','장기거주(지적·중증)_시설수','공동_시설수']].head(15)"""),
    ("code", """display(Image(filename=str(ROOT/'outputs/figures/fig05_no_short_stay_sgg.png')))"""),
    ("md", "## 5. 국민기초생활보장 사업안내 PDF → 기준값·규정\n규정 문장은 원문에서 찾아 **인쇄 쪽수**와 함께 저장합니다(서비스 화면의 근거 표기에 사용)."),
    ("code", """pd.read_csv(PROCESSED / 'nblsa_selection_criteria_2025.csv').pivot(index='급여', columns='가구원수', values='선정기준_원')"""),
    ("code", """pd.read_csv(PROCESSED / 'nblsa_facility_benefit_2025.csv')"""),
    ("code", """pd.set_option('display.max_colwidth', 120)
pd.read_csv(PROCESSED / 'nblsa_rules.csv')[['설명','인쇄쪽','원문발췌']]"""),
    ("code", """display(Image(filename=str(ROOT/'outputs/figures/fig06_facility_benefit_tiers.png')))"""),
    ("md", "## 6. 장애수당(기초생활보장) 수급자 — 검토 후 제외한 이유"),
    ("code", """m_path = PROCESSED / 'allowance_basic_monthly.csv'
if m_path.exists():
    m = pd.read_csv(m_path, index_col=0)
    print('자폐성 장애인은 대부분 장애인연금 대상이라 이 자료에 거의 잡히지 않아, 발달장애 수요 지표로 쓰지 않았습니다.')
    display(m[['합계','지적','자폐성']])
    display(Image(filename=str(ROOT/'outputs/figures/fig08_allowance_review.png')))
else:
    print('장애수당 ZIP 파일이 원자료 폴더에 없어 건너뜁니다.')"""),
    ("md", "## 7. 사회복지시설정보 OpenAPI: 2026 현행화와 채용 신호\n`python src/fetch_facility_api.py` 로 수집하고 `python src/match_api_to_ilam.py` 로 일람표(2024.12)와 연결합니다. 연결은 같은 시도·같은 돌봄 단계 안에서 시설명이 같거나 한쪽이 다른 쪽을 포함할 때만 1:1로 합니다. 이름으로 연결되지 않은 시설은 신설·폐지 후보일 뿐 확정이 아닙니다."),
    ("code", """f = API_DIR / 'api_facilities.csv'
rp = PROCESSED / 'facility_api_match_report.csv'
if f.exists() and rp.exists():
    api = pd.read_csv(f, dtype=str)
    print(f"API 장애인 관련 시설 {api['srvInstId'].nunique():,}곳 (서비스기관ID 기준)")
    display(pd.read_csv(rp, index_col=0))
    display(Image(filename=str(ROOT/'outputs/figures/fig10_api_currency.png')))
else:
    mock = API_DIR / 'mock' / 'api_facilities.csv'
    print('아직 실제 API 수집 전입니다.' + (' 모의 실행 결과:' if mock.exists() else ''))
    if mock.exists(): display(pd.read_csv(mock, dtype=str))"""),
    ("code", """hp = PROCESSED / 'api_hiring_by_stage.csv'
if hp.exists():
    display(pd.read_csv(hp, index_col=0))
    display(Image(filename=str(ROOT/'outputs/figures/fig09_api_hiring_by_stage.png')))
else:
    print('구인정보 수집 전입니다.')"""),
]


def run_cells():
    import matplotlib.pyplot as plt
    ns = {"__name__": "__main__"}
    out_cells = []
    count = 0
    # 노트북은 notebooks/ 폴더에서 실행되는 것과 같게
    import os
    cwd = os.getcwd()
    os.chdir(ROOT / "notebooks")
    shown = []

    def fake_display(obj):
        shown.append(obj)

    class _Image:
        def __init__(self, filename):
            self.filename = filename

    for kind, src in CELLS:
        if kind == "md":
            out_cells.append({"cell_type": "markdown", "metadata": {}, "source": src.splitlines(True)})
            continue
        count += 1
        outputs = []
        shown.clear()
        # 저장되는 셀은 IPython 코드 그대로, 여기서 실행할 때만 표시 함수를 바꿔 결과를 모은다
        code = src.replace("from IPython.display import Image, display", "pass")
        ns["display"], ns["Image"] = fake_display, _Image
        buf = io.StringIO()
        tree = ast.parse(code)
        last = None
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last = ast.Expression(tree.body.pop().value)
        with contextlib.redirect_stdout(buf):
            exec(compile(tree, f"<cell{count}>", "exec"), ns)
            value = eval(compile(last, f"<cell{count}>", "eval"), ns) if last else None
        text = buf.getvalue()
        if text:
            outputs.append({"output_type": "stream", "name": "stdout", "text": text.splitlines(True)})
        for obj in list(shown) + ([value] if value is not None else []):
            fn = getattr(obj, "filename", None)
            if fn:
                data = base64.b64encode(Path(fn).read_bytes()).decode()
                outputs.append({"output_type": "display_data", "metadata": {}, "data": {"image/png": data, "text/plain": ["<Image>"]}})
            elif hasattr(obj, "to_html"):
                outputs.append({"output_type": "execute_result" if obj is value else "display_data", "metadata": {},
                                **({"execution_count": count} if obj is value else {}),
                                "data": {"text/html": obj.to_html(max_rows=30).splitlines(True),
                                         "text/plain": obj.to_string(max_rows=30).splitlines(True)}})
            else:
                outputs.append({"output_type": "execute_result", "execution_count": count, "metadata": {},
                                "data": {"text/plain": [repr(obj)]}})
        plt.close("all")
        out_cells.append({"cell_type": "code", "execution_count": count, "metadata": {}, "outputs": outputs,
                          "source": src.splitlines(True)})
    os.chdir(cwd)
    return out_cells


def main():
    cells = run_cells()
    for i, c in enumerate(cells):
        c["id"] = f"baton-{i:02d}"
    nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                       "language_info": {"name": "python"}},
          "nbformat": 4, "nbformat_minor": 5}
    NB.parent.mkdir(exist_ok=True)
    NB.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[노트북] {NB.relative_to(ROOT)} ({sum(1 for c in cells if c['cell_type'] == 'code')}개 코드 셀 실행 결과 포함)")


if __name__ == "__main__":
    main()
