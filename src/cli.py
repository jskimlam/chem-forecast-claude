"""명령행 도구: 엑셀 불러오기(import), 가격 수동 입력(update), 사이트 빌드(build), 데이터 점검(check), 품목 목록(list).

실행 예)
    python -m src.cli import --xlsx 원본.xlsx
    python -m src.cli update --date 2026-10-05 SM_FOB_KR=1420 BZ_FOB_KR=1180 NMCL001=90.5
    python -m src.cli update --file 새가격.csv
    python -m src.cli sync            # 구글시트에서 가격을 받아 prices.csv 갱신 후 빌드
    python -m src.cli build
    python -m src.cli check
    python -m src.cli list
"""  # 모듈 설명
# 필요 라이브러리 설치: pip install pandas numpy openpyxl
import argparse  # 명령행 인자 처리용
import os  # 환경변수 읽기용
import sys  # 종료 코드 반환용
from pathlib import Path  # 경로 처리용

import pandas as pd  # 표 데이터 처리용

from . import config as cfg  # 설정 상수 불러오기
from .build_site import BuildError, render_site  # 사이트 빌드
from .data_io import DataError, data_report, import_xlsx, parse_assignments, read_prices, resolve_item, upsert_row, write_prices  # 데이터 입출력
from .payload import build_all  # 페이지 데이터 생성
from .sheet_sync import sync_prices  # 구글시트 동기화


def parse_args(argv=None):  # 명령행 인자를 해석하는 함수
    """명령행 인자를 읽어 돌려줍니다."""  # 함수 설명
    parser = argparse.ArgumentParser(description="원료 가격 기술적 분석 대시보드 도구")  # 파서 생성
    sub = parser.add_subparsers(dest="cmd", required=True)  # 하위 명령
    p_imp = sub.add_parser("import", help="플래츠 엑셀을 읽어 data/prices.csv 를 만듭니다")  # import 명령
    p_imp.add_argument("--xlsx", required=True, help="플래츠 엑셀 파일 경로")  # 엑셀 경로
    p_imp.add_argument("--no-build", action="store_true", help="사이트를 다시 만들지 않음")  # 빌드 생략
    p_upd = sub.add_parser("update", help="날짜와 가격을 입력해 data/prices.csv 를 갱신합니다")  # update 명령
    p_upd.add_argument("--date", default=None, help="입력할 날짜(YYYY-MM-DD)")  # 날짜
    p_upd.add_argument("--file", default=None, help="여러 날짜를 한 번에 넣는 CSV(첫 열 date, 나머지 열 이름은 품목 코드·키)")  # CSV 입력
    p_upd.add_argument("--allow-nonpositive", action="store_true", help="0 이하 가격(예: WTI 음수)을 허용")  # 음수 허용
    p_upd.add_argument("--no-build", action="store_true", help="사이트를 다시 만들지 않음")  # 빌드 생략
    p_upd.add_argument("prices", nargs="*", help="품목=가격 목록 (예: SM_FOB_KR=1420)")  # 가격 목록
    p_sync = sub.add_parser("sync", help="구글시트(Apps Script 웹앱)에서 가격을 받아 data/prices.csv 를 갱신합니다")  # sync 명령
    p_sync.add_argument("--url", default=None, help="웹앱 주소(기본: 환경변수 CHEM_GAS_URL)")  # 웹앱 주소
    p_sync.add_argument("--token", default=None, help="읽기 토큰(기본: 환경변수 CHEM_GAS_TOKEN)")  # 읽기 토큰
    p_sync.add_argument("--no-build", action="store_true", help="사이트를 다시 만들지 않음")  # 빌드 생략
    sub.add_parser("build", help="data/prices.csv 로 site/index.html 을 만듭니다")  # build 명령
    sub.add_parser("check", help="품목별 데이터 현황을 출력합니다")  # check 명령
    sub.add_parser("list", help="품목 코드·키·이름 목록을 출력합니다")  # list 명령
    return parser.parse_args(argv)  # 해석 결과 반환


def do_build() -> int:  # 사이트 빌드 실행 함수
    """prices.csv를 읽어 모든 품목을 계산하고 site/index.html을 만듭니다."""  # 함수 설명
    frame = read_prices()  # 가격 읽기
    payload, errors = build_all(frame)  # 데이터 생성
    for e in errors:  # 품목별 문제 출력
        print(f"[주의] {e}")  # 주의 출력
    for code, it in payload["items"].items():  # 품목마다 품질 경고 확인
        for w in (it.get("meta") or {}).get("warnings", []):  # 경고 문구마다
            print(f"[품질] {it['meta'].get('key', code)}: {w}")  # 실행 화면에서 볼 수 있게 출력
    out = render_site(payload)  # 사이트 생성
    meta = payload["meta"]  # 전체 메타
    print(f"[완료] 기준 최신일 {meta['latest_date']}, 품목 {meta['n_items']}개, 생성 {meta['generated_at']}")  # 완료 안내
    print(f"[완료] 사이트: {out}")  # 산출물 위치 안내
    return 0  # 성공 코드


def do_sync(args) -> int:  # 시트 동기화 실행 함수
    """구글시트에서 가격을 받아 prices.csv 를 갱신하고 사이트를 다시 만듭니다."""  # 함수 설명
    url = args.url or os.environ.get("CHEM_GAS_URL", "")  # 웹앱 주소
    token = args.token or os.environ.get("CHEM_GAS_TOKEN", "")  # 읽기 토큰
    frame, notes = sync_prices(url, token)  # 시트에서 받아 저장
    for n in notes:  # 안내 출력
        print(f"[안내] {n}")  # 안내 출력
    print(f"[완료] 시트에서 {len(frame)}행을 받아 {cfg.PRICES_CSV} 에 저장했습니다. ({frame.index.min():%Y-%m-%d} ~ {frame.index.max():%Y-%m-%d})")  # 완료 안내
    return 0 if args.no_build else do_build()  # 이어서 빌드


def do_import(args) -> int:  # 엑셀 불러오기 실행 함수
    """엑셀을 읽어 prices.csv로 저장합니다. 기존 파일이 있으면 .bak 으로 백업합니다."""  # 함수 설명
    frame, notes = import_xlsx(Path(args.xlsx))  # 엑셀 읽기
    for n in notes:  # 안내 출력
        print(f"[안내] {n}")  # 안내 출력
    if cfg.PRICES_CSV.exists():  # 기존 파일이 있으면
        backup = cfg.PRICES_CSV.with_suffix(".csv.bak")  # 백업 경로
        backup.write_bytes(cfg.PRICES_CSV.read_bytes())  # 백업 저장
        print(f"[안내] 기존 파일을 {backup} 로 백업했습니다.")  # 백업 안내
    path = write_prices(frame)  # CSV 저장
    print(f"[완료] {path} 저장: {len(frame)}행, {frame.index.min():%Y-%m-%d} ~ {frame.index.max():%Y-%m-%d}")  # 저장 안내
    return 0 if args.no_build else do_build()  # 이어서 빌드


def rows_from_csv(path: Path) -> list:  # 입력 CSV 해석 함수
    """여러 날짜를 담은 CSV를 [(날짜, {코드: 가격})] 목록으로 바꿉니다. 빈 칸은 건너뜁니다."""  # 함수 설명
    if not path.exists():  # 파일이 없으면
        raise DataError(f"파일을 찾을 수 없습니다: {path}")  # 한글 오류 안내
    raw = pd.read_csv(path)  # CSV 읽기
    if "date" not in raw.columns:  # 날짜 열이 없으면
        raise DataError("입력 CSV에 'date' 열이 없습니다.")  # 한글 오류 안내
    rows = []  # 결과 목록
    for _, r in raw.iterrows():  # 행마다
        values = {}  # 그날의 값
        for col in raw.columns:  # 열마다
            if col == "date" or pd.isna(r[col]):  # 날짜 열이거나 빈 칸이면
                continue  # 건너뜀
            item = resolve_item(str(col))  # 열 이름으로 품목 해석
            try:  # 숫자 변환 시도
                values[item["code"]] = float(str(r[col]).replace(",", ""))  # 가격 변환
            except ValueError:  # 숫자가 아니면
                raise DataError(f"{r['date']}의 {col} 값 '{r[col]}'을 숫자로 읽을 수 없습니다.") from None  # 한글 오류 안내
        rows.append((r["date"], values))  # 행 추가
    return rows  # 목록 반환


def do_update(args) -> int:  # 가격 입력 실행 함수
    """가격을 입력해 prices.csv를 갱신하고 사이트를 다시 만듭니다. 검증을 통과하지 못하면 파일을 바꾸지 않습니다."""  # 함수 설명
    frame = read_prices()  # 기존 가격
    if args.file:  # CSV로 여러 날짜 입력
        batches = rows_from_csv(Path(args.file))  # 입력 해석
    else:  # 명령행으로 한 날짜 입력
        if not args.date:  # 날짜가 없으면
            raise DataError("--date YYYY-MM-DD 를 써 주세요. (또는 --file 로 CSV 입력)")  # 한글 오류 안내
        batches = [(args.date, parse_assignments(args.prices))]  # 한 날짜 묶음
    reports = []  # 보고서 모음
    for when, values in batches:  # 날짜별로
        frame, rep = upsert_row(frame, when, values, allow_nonpositive=args.allow_nonpositive)  # 입력 반영
        reports.append(rep)  # 보고서 저장
    path = write_prices(frame)  # 검증을 통과한 뒤에만 저장
    for rep in reports:  # 보고서 출력
        print(f"[입력] {rep['date']}: 추가 {len(rep['added'])}건, 수정 {len(rep['updated'])}건")  # 요약
        for key, price in rep["added"]:  # 추가 내역
            print(f"   + {key} = {price:g}")  # 출력
        for key, old, new in rep["updated"]:  # 수정 내역
            print(f"   ~ {key}: {old:g} → {new:g}")  # 출력
        for w in rep["warnings"]:  # 경고
            print(f"[경고] {w}")  # 출력
    print(f"[완료] {path} 저장")  # 저장 안내
    return 0 if args.no_build else do_build()  # 이어서 빌드


def do_check() -> int:  # 데이터 점검 실행 함수
    """품목별 마지막 날짜·유효 개수·지연을 표로 출력합니다."""  # 함수 설명
    frame = read_prices()  # 가격 읽기
    rows = data_report(frame)  # 현황
    print(f"전체 {len(frame)}행, {frame.index.min():%Y-%m-%d} ~ {frame.index.max():%Y-%m-%d}")  # 전체 요약
    print(f"{'키':14s} {'주기':4s} {'개수':>5s} {'마지막 날짜':12s} {'지연(일)':>8s}  이름")  # 표 머리
    for r in rows:  # 품목마다
        behind = "-" if r["behind_days"] is None else str(r["behind_days"])  # 지연 표기
        print(f"{r['key']:14s} {r['freq']:4s} {r['n']:5d} {str(r['last']):12s} {behind:>8s}  {r['label']}")  # 한 줄 출력
    return 0  # 성공 코드


def do_list() -> int:  # 품목 목록 실행 함수
    """코드·키·탭 이름·그룹을 출력합니다."""  # 함수 설명
    gname = {g["id"]: g["label"] for g in cfg.GROUPS}  # 그룹 이름 사전
    print(f"{'코드':9s} {'키':14s} {'주기':4s} {'단위':10s} {'그룹':12s} 탭 이름")  # 표 머리
    for it in cfg.shown_items():  # 표시 품목마다
        print(f"{it['code']:9s} {it['key']:14s} {it['freq']:4s} {cfg.unit_label(it):10s} {gname[it['group']]:12s} {it['label']}")  # 한 줄 출력
    return 0  # 성공 코드


def run(argv=None) -> int:  # 전체 실행 함수
    """명령을 실행하고 종료 코드(0 성공, 1 실패)를 돌려줍니다."""  # 함수 설명
    args = parse_args(argv)  # 인자 해석
    try:  # 오류를 한글로 안내하기 위한 묶음
        if args.cmd == "import":  # 엑셀 불러오기
            return do_import(args)  # 실행
        if args.cmd == "update":  # 가격 입력
            return do_update(args)  # 실행
        if args.cmd == "sync":  # 시트 동기화
            return do_sync(args)  # 실행
        if args.cmd == "build":  # 빌드
            return do_build()  # 실행
        if args.cmd == "check":  # 점검
            return do_check()  # 실행
        return do_list()  # 목록
    except (DataError, BuildError, ValueError) as exc:  # 예상 가능한 오류
        print(f"[오류] {exc}")  # 한글 오류 출력
        return 1  # 실패 코드
    except Exception as exc:  # 예상하지 못한 오류
        print(f"[오류] 예상하지 못한 문제가 생겼습니다: {exc}")  # 한글 오류 출력
        return 1  # 실패 코드


if __name__ == "__main__":  # 직접 실행될 때만
    sys.exit(run())  # 종료 코드로 끝냄
