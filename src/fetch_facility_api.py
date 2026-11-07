"""한국사회보장정보원 「사회복지시설정보」 OpenAPI 수집기.

서비스: https://apis.data.go.kr/B554287/sclWlfrFcltInfoInqirService2 (활용신청 End Point), Service1(활용가이드 v2.5)도 예비로 시도
쓰는 오퍼레이션
  - getFcltKindCodeInfoInqire2  시설종류코드 조회      → 장애인 관련 시설종류코드 찾기
  - getFcltListInfoInqire2      시설 목록정보 조회      → 종류코드별 시설 목록(시설코드·소관 시군구)
  - getFcltByJoInfo2            시설별 구인정보         → 시설의 채용 공고(종사자 부족 신호)
  - getFcltByBassInfoInqire2    시설별 기본정보 조회    → 주소·전화·설립일(선택)

실행 예
  python src/fetch_facility_api.py                 # 종류코드 → 장애인 시설 목록 → 구인정보
  python src/fetch_facility_api.py --limit 50      # 구인정보는 앞 50곳만(시험용)
  python src/fetch_facility_api.py --basic         # 기본정보까지 수집
  python src/fetch_facility_api.py --mock          # 인터넷 없이 가이드 예시 형식으로 동작 확인

결과: data/api/ (모의 실행은 data/api/mock/)
  api_kind_codes.csv, api_facilities.csv, api_jobs.csv, api_basic.csv, api_log.csv
응답 원문(XML)은 data/api/raw/ 에 캐시되어, 다시 실행하면 받은 것은 건너뛴다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import API_DIR, ROOT  # noqa: E402

# 활용신청 화면의 End Point. 미리보기로 시설종류코드 조회가 되는 것을 확인함(2026-11-06)
BASES = ["https://apis.data.go.kr/B554287/sclWlfrFcltInfoInqirService2"]
FIXTURES = ROOT / "tests" / "fixtures"
# Service2의 오퍼레이션 이름(포털 상세기능에서 확인: 가이드 v2.5의 이름 뒤에 2가 붙음)
OP_KIND = "getFcltKindCodeInfoInqire2"
OP_LIST = "getFcltListInfoInqire2"
OP_JOB = "getFcltByJoInfo2"
OP_BASIC = "getFcltByBassInfoInqire2"

# 시설종류 상세명으로 바톤의 돌봄 단계 분류
STAGE_RULES = [
    ("단기거주", ["단기"]),
    ("공동생활가정", ["공동생활"]),
    ("주간이용", ["주간"]),
    ("장기거주", ["거주", "요양", "생활시설"]),
]


class ApiError(RuntimeError):
    pass


def _items(root):
    return [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]


def parse_response(xml_text: str):
    """data.go.kr XML 응답을 (items, totalCount)로 바꾼다. 오류 응답이면 ApiError."""
    try:
        root = ET.fromstring(xml_text.strip().encode("utf-8"))
    except ET.ParseError as e:
        raise ApiError(f"XML이 아닌 응답입니다: {xml_text[:200]!r}") from e
    if root.tag == "OpenAPI_ServiceResponse":
        auth = (root.findtext(".//returnAuthMsg") or "") + " " + (root.findtext(".//errMsg") or "")
        code = root.findtext(".//returnReasonCode") or ""
        hint = {
            "SERVICE_KEY_IS_NOT_REGISTERED_ERROR": "키가 아직 등록되지 않았습니다. 활용신청 승인 후 1~2시간 뒤 다시 해 보세요.",
            "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR": "하루 호출 한도를 넘었습니다. 내일 이어서 실행하면 캐시된 부분은 건너뜁니다.",
            "SERVICE_ACCESS_DENIED_ERROR": "이 API에 대한 활용신청이 필요합니다.",
        }
        hint = next((v for k, v in hint.items() if k in auth), "")
        if not hint and "등록되지 않은" in auth:
            hint = hint or "키가 아직 등록되지 않았습니다. 활용신청 승인 후 1~2시간 뒤 다시 해 보세요."
        raise ApiError(f"API 오류 {code} {auth} {hint}".strip())
    code = root.findtext(".//resultCode")
    if code not in (None, "00", "0", "000"):
        raise ApiError(f"API 결과코드 {code}: {root.findtext('.//resultMsg')}")
    total = root.findtext(".//totalCount")
    return _items(root), int(total) if total and total.isdigit() else None


class Client:
    def __init__(self, key: str | None, mock: bool = False, sleep: float = 0.05):
        self.key, self.mock, self.sleep = key, mock, sleep
        self.raw = (API_DIR / ("mock" if mock else "") / "raw")
        self.raw.mkdir(parents=True, exist_ok=True)
        self.log = []
        self.base = BASES[0]

    def call(self, op: str, **params):
        params = {k: v for k, v in params.items() if v not in (None, "")}
        tag = hashlib.md5(json.dumps([op, params], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
        cache = self.raw / op / f"{tag}.xml"
        if cache.exists():
            text = cache.read_text(encoding="utf-8")
        elif self.mock:
            text = (FIXTURES / f"{op.rstrip('2')}.xml").read_text(encoding="utf-8")
        else:
            text = self._get(op, params)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(text, encoding="utf-8")
            time.sleep(self.sleep)
        items, total = parse_response(text)
        self.log.append({"op": op, "params": json.dumps(params, ensure_ascii=False), "items": len(items), "total": total})
        return items, total

    def _get(self, op, params):
        import requests
        last = None
        errors = []
        for attempt in range(2):
            for base in ([self.base] + [b for b in BASES if b != self.base]):
                try:
                    r = requests.get(f"{base}/{op}", params={"serviceKey": self.key, **params}, timeout=20)
                    if r.status_code == 200 and "<" in r.text[:50]:
                        self.base = base
                        r.encoding = "utf-8"
                        return r.text
                    if "OpenAPI_ServiceResponse" in r.text:
                        # 포털 오류(키 미등록, 서비스 없음 등)는 원인 문구를 풀어서 보여 준다
                        try:
                            parse_response(r.text)
                        except ApiError as e:
                            last = f"HTTP {r.status_code} {e} (주소: {base})"
                    else:
                        last = f"HTTP {r.status_code}: {r.text[:200]} (주소: {base})"
                except requests.RequestException as e:
                    last = repr(e)
                errors.append(last)
            time.sleep(1.5 * (attempt + 1))
        raise ApiError(f"{op} 호출 실패:\n  " + "\n  ".join(dict.fromkeys(e for e in errors if e)))

    def paged(self, op, rows=100, max_pages=500, **params):
        out, page = [], 1
        while page <= max_pages:
            items, total = self.call(op, pageNo=page, numOfRows=rows, **params)
            out.extend(items)
            if not items or total is None or len(out) >= total or self.mock:
                break
            page += 1
        return out


def stage_of(detail_name: str) -> str:
    for stage, kws in STAGE_RULES:
        if any(k in detail_name for k in kws):
            return stage
    return "기타"


def main():
    ap = argparse.ArgumentParser(description="사회복지시설정보 OpenAPI 수집")
    ap.add_argument("--mock", action="store_true", help="tests/fixtures의 예시 응답으로 실행(인터넷 불필요)")
    ap.add_argument("--limit", type=int, default=None, help="구인·기본정보를 받을 시설 수 상한")
    ap.add_argument("--rows", type=int, default=100, help="한 페이지 결과 수")
    ap.add_argument("--no-jobs", action="store_true", help="구인정보 수집 생략")
    ap.add_argument("--basic", action="store_true", help="시설별 기본정보도 수집")
    ap.add_argument("--all-disabled", action="store_true",
                    help="장애인 관련 시설종류 전부(복지관·직업재활 등 포함). 기본은 바톤 돌봄 경로(거주·단기·공동생활·주간이용)만")
    args = ap.parse_args()

    out_dir = API_DIR / "mock" if args.mock else API_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    key = None
    if not args.mock:
        from api_key import load_service_key
        key = load_service_key()
    cl = Client(key, mock=args.mock)

    # 1) 시설종류코드
    kinds = pd.DataFrame(cl.paged(OP_KIND, rows=args.rows))
    if kinds.empty:
        raise ApiError("시설종류코드가 비어 있습니다.")
    for c in ("fcltKindNm", "fcltDtlKindNm", "fcltUseRcpnNm"):
        if c not in kinds:
            kinds[c] = ""
    kinds["장애인관련"] = kinds[["fcltKindNm", "fcltDtlKindNm", "fcltUseRcpnNm"]].astype(str).agg(" ".join, axis=1).str.contains("장애")
    kinds["바톤단계"] = kinds["fcltDtlKindNm"].astype(str).map(stage_of)
    kinds.to_csv(out_dir / "api_kind_codes.csv", index=False, encoding="utf-8-sig")
    dis = kinds[kinds["장애인관련"]]
    if not args.all_disabled:
        dis = dis[dis["바톤단계"] != "기타"]
    print(f"[1] 시설종류코드 {len(kinds)}개 중 수집 대상 {len(dis)}개")

    # 2) 장애인 관련 종류코드별 시설 목록
    facs = []
    for _, k in dis.iterrows():
        items = cl.paged(OP_LIST, rows=args.rows, fcltKindCd=k["fcltKindCd"])
        for it in items:
            it.update({"요청_종류코드": k["fcltKindCd"], "종류상세명": k.get("fcltDtlKindNm", ""), "바톤단계": k["바톤단계"]})
        facs.extend(items)
        print(f"    {k['fcltKindCd']} {k.get('fcltDtlKindNm', '')}: {len(items)}곳")
    fac = pd.DataFrame(facs).drop_duplicates(subset=[c for c in ("fcltCd", "srvInstId") if facs and c in facs[0]] or None)
    fac.to_csv(out_dir / "api_facilities.csv", index=False, encoding="utf-8-sig")
    print(f"[2] 장애인 관련 시설 {len(fac):,}곳")

    targets = fac.head(args.limit) if args.limit else fac

    # 3) 구인정보
    if not args.no_jobs and len(targets):
        jobs = []
        for n, (_, f) in enumerate(targets.iterrows(), 1):
            try:
                items, _ = cl.call(OP_JOB, pageNo=1, numOfRows=args.rows,
                                   fcltCd=f.get("fcltCd"), srvInstId=f.get("srvInstId"))
            except ApiError as e:
                print(f"    [건너뜀] {f.get('fcltNm')}: {e}")
                if "한도" in str(e):
                    break
                continue
            for it in items:
                it.update({"요청_시설코드": f.get("fcltCd"), "요청_시설명": f.get("fcltNm"), "바톤단계": f.get("바톤단계")})
            jobs.extend(items)
            if n % 100 == 0:
                print(f"    구인정보 {n}/{len(targets)}곳 확인")
        pd.DataFrame(jobs).to_csv(out_dir / "api_jobs.csv", index=False, encoding="utf-8-sig")
        print(f"[3] 구인 공고 {len(jobs):,}건 (시설 {len(targets):,}곳 조회)")

    # 4) 기본정보(선택)
    if args.basic and len(targets):
        basics = []
        for _, f in targets.iterrows():
            try:
                items, _ = cl.call(OP_BASIC, pageNo=1, numOfRows=10, fcltCd=f.get("fcltCd"),
                                   srvInstId=f.get("srvInstId"))
                basics.extend(items)
            except ApiError as e:
                print(f"    [건너뜀] {f.get('fcltNm')}: {e}")
        pd.DataFrame(basics).to_csv(out_dir / "api_basic.csv", index=False, encoding="utf-8-sig")
        print(f"[4] 기본정보 {len(basics):,}건")

    pd.DataFrame(cl.log).to_csv(out_dir / "api_log.csv", index=False, encoding="utf-8-sig")
    print(f"완료: {out_dir}")


if __name__ == "__main__":
    try:
        main()
    except ApiError as e:
        print(f"\n[중단] {e}")
        sys.exit(1)
