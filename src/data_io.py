"""가격 파일 입출력 모듈: 플래츠 엑셀 불러오기, CSV 읽기·쓰기, 수동 가격 입력(upsert)과 검증. 모든 오류는 한글로 안내합니다."""  # 모듈 설명
# 필요 라이브러리 설치: pip install pandas numpy openpyxl
from datetime import date as date_cls, timedelta  # 오늘 날짜 비교용
from pathlib import Path  # 경로 처리용

import pandas as pd  # 표 데이터 처리용

from . import config as cfg  # 설정 상수 불러오기


class DataError(Exception):  # 데이터 관련 오류를 구분하기 위한 예외
    """가격 데이터 읽기·쓰기·검증 단계에서 발생하는 오류(메시지는 한글)."""  # 예외 설명


def all_codes() -> list:  # 전체 품목 코드 목록 함수
    """설정에 정의된 품목 코드를 탭 순서대로 돌려줍니다."""  # 함수 설명
    return [it["code"] for it in cfg.ITEMS]  # 코드만 추출


def _normalize(text: str) -> str:  # 비교용 문자열 정리 함수
    """공백·괄호·대소문자·특수문자를 없애 비교하기 쉬운 문자열로 만듭니다."""  # 함수 설명
    return "".join(ch for ch in str(text).lower() if ch.isalnum())  # 글자와 숫자만 남김


def resolve_item(token: str) -> dict:  # 품목 이름 해석 함수
    """코드(예: AAMFL00), 키(예: SM_FOB_KR), 탭 이름(예: 'SM FOB 한국') 중 무엇으로 써도 품목을 찾아 돌려줍니다.
    정확히 일치하는 것이 없으면 부분 일치가 하나일 때만 인정하고, 여러 개면 후보를 알려주며 오류를 냅니다."""  # 함수 설명
    norm = _normalize(token)  # 비교용 문자열
    if not norm:  # 비어 있으면
        raise DataError("품목 이름이 비어 있습니다. 코드·키·탭 이름 중 하나를 쓰세요. (python -m src.cli list 로 목록 확인)")  # 한글 오류 안내
    for it in cfg.shown_items():  # 정확히 일치하는 품목 찾기(표시 품목만)
        if norm in (_normalize(it["code"]), _normalize(it["key"]), _normalize(it["label"])):  # 코드·키·이름 중 하나가 같으면
            return it  # 품목 반환
    partial = [it for it in cfg.shown_items() if norm in _normalize(it["key"]) or norm in _normalize(it["label"])]  # 부분 일치 후보
    if len(partial) == 1:  # 후보가 하나면
        return partial[0]  # 그 품목 반환
    if len(partial) > 1:  # 후보가 여럿이면
        names = ", ".join(f"{p['key']}({p['label']})" for p in partial[:8])  # 후보 나열
        raise DataError(f"'{token}'에 해당하는 품목이 여러 개입니다: {names}. 키나 코드로 정확히 써 주세요.")  # 한글 오류 안내
    raise DataError(f"'{token}'에 해당하는 품목을 찾을 수 없습니다. (python -m src.cli list 로 코드·키 목록을 확인하세요)")  # 한글 오류 안내


def parse_assignments(tokens: list) -> dict:  # 입력 토큰 해석 함수
    """['SM_FOB_KR=1420', 'AAMFI00=1,369'] 같은 목록을 {코드: 가격} 사전으로 바꿉니다. 같은 품목을 두 번 쓰면 오류입니다."""  # 함수 설명
    values = {}  # 결과 사전
    for tok in tokens:  # 토큰을 하나씩
        if "=" not in tok:  # 등호가 없으면
            raise DataError(f"'{tok}'는 '품목=가격' 형식이 아닙니다. 예: SM_FOB_KR=1420")  # 한글 오류 안내
        name, raw = tok.split("=", 1)  # 이름과 값 분리
        item = resolve_item(name.strip())  # 품목 해석
        text = raw.strip().replace(",", "")  # 천 단위 쉼표 제거
        try:  # 숫자 변환 시도
            price = float(text)  # 가격 변환
        except ValueError:  # 숫자가 아니면
            raise DataError(f"{item['key']}의 가격 '{raw}'를 숫자로 읽을 수 없습니다.") from None  # 한글 오류 안내
        if item["code"] in values:  # 같은 품목을 중복 입력했으면
            raise DataError(f"{item['key']}가 두 번 입력되었습니다. 한 번만 쓰세요.")  # 한글 오류 안내
        values[item["code"]] = price  # 결과에 추가
    return values  # 사전 반환


def _clean_frame(df: pd.DataFrame) -> pd.DataFrame:  # 가격 표 정리 함수
    """날짜 인덱스를 오름차순·중복 없이 정리하고, 모든 품목 열이 있도록 맞춥니다."""  # 함수 설명
    df = df.copy()  # 원본 보호
    df.index = pd.to_datetime(df.index).normalize()  # 날짜로 통일(시각 제거)
    df.index.name = "date"  # 인덱스 이름
    df = df[~df.index.duplicated(keep="last")].sort_index()  # 중복 날짜는 마지막 값 사용 후 오름차순 정렬
    for code in all_codes():  # 모든 품목에 대해
        if code not in df.columns:  # 열이 없으면
            df[code] = float("nan")  # 빈 열 추가
        df[code] = pd.to_numeric(df[code], errors="coerce")  # 숫자로 변환(변환 불가는 NaN)
    return df[all_codes()]  # 탭 순서대로 열 정렬


def read_prices(path: Path = None) -> pd.DataFrame:  # CSV 읽기 함수
    """누적 가격 CSV(date + 품목 코드 열)를 읽어 날짜 인덱스 표로 돌려줍니다."""  # 함수 설명
    path = Path(path) if path else cfg.PRICES_CSV  # 경로 결정
    if not path.exists():  # 파일이 없으면
        raise DataError(f"파일을 찾을 수 없습니다: {path} (먼저 python -m src.cli import --xlsx 파일.xlsx 로 만들어 주세요)")  # 한글 오류 안내
    try:  # 읽기 시도
        raw = pd.read_csv(path)  # CSV 읽기
    except Exception as exc:  # 읽기 실패
        raise DataError(f"가격 파일을 읽지 못했습니다({path}): {exc}") from None  # 한글 오류 안내
    if "date" not in raw.columns:  # 날짜 열이 없으면
        raise DataError(f"가격 파일에 'date' 열이 없습니다: {path}")  # 한글 오류 안내
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")  # 날짜 변환
    if raw["date"].isna().any():  # 날짜로 못 읽은 행이 있으면
        raise DataError(f"가격 파일에 날짜를 읽을 수 없는 행이 {int(raw['date'].isna().sum())}개 있습니다: {path}")  # 한글 오류 안내
    return _clean_frame(raw.set_index("date"))  # 정리해서 반환


def write_prices(df: pd.DataFrame, path: Path = None) -> Path:  # CSV 쓰기 함수
    """가격 표를 CSV로 저장합니다(날짜 오름차순, 날짜 형식 YYYY-MM-DD)."""  # 함수 설명
    path = Path(path) if path else cfg.PRICES_CSV  # 경로 결정
    path.parent.mkdir(parents=True, exist_ok=True)  # 폴더 만들기
    out = _clean_frame(df)  # 정리
    out.index = out.index.strftime("%Y-%m-%d")  # 날짜 문자열로 변환
    out.index.name = "date"  # 인덱스 이름
    out.to_csv(path)  # 저장
    return path  # 경로 반환


def import_xlsx(path: Path) -> tuple:  # 엑셀 불러오기 함수
    """플래츠 엑셀(품목 코드 행 + 날짜별 가격)을 읽어 (가격 표, 안내 목록)을 돌려줍니다. 날짜가 내림차순이어도 오름차순으로 바꿉니다."""  # 함수 설명
    path = Path(path)  # 경로 객체로 통일
    if not path.exists():  # 파일이 없으면
        raise DataError(f"파일을 찾을 수 없습니다: {path}")  # 한글 오류 안내
    try:  # 읽기 시도
        raw = pd.read_excel(path, header=None)  # 헤더 없이 전체 읽기
    except Exception as exc:  # 읽기 실패
        raise DataError(f"엑셀 파일을 읽지 못했습니다({path}): {exc}") from None  # 한글 오류 안내
    known = set(all_codes())  # 알려진 코드 집합
    code_row = None  # 코드가 적힌 행 번호
    for i in range(min(15, len(raw))):  # 위쪽 15행 안에서
        cells = {str(v).strip() for v in raw.iloc[i, 1:].tolist() if pd.notna(v)}  # 이 행의 셀 값들
        if len(cells & known) >= max(3, len(known) // 2):  # 알려진 코드가 절반 이상이면
            code_row = i  # 코드 행으로 확정
            break  # 탐색 종료
    if code_row is None:  # 못 찾았으면
        raise DataError("엑셀에서 품목 코드 행(NMCL001, PAAAD00 ...)을 찾지 못했습니다. 양식이 바뀌지 않았는지 확인하세요.")  # 한글 오류 안내
    codes = [str(v).strip() if pd.notna(v) else "" for v in raw.iloc[code_row, 1:].tolist()]  # 열별 코드
    start = None  # 데이터 시작 행
    for i in range(code_row + 1, len(raw)):  # 코드 행 아래에서
        if pd.notna(raw.iloc[i, 0]) and (isinstance(raw.iloc[i, 0], (pd.Timestamp, date_cls)) or hasattr(raw.iloc[i, 0], "year")):  # 첫 열이 날짜이면
            start = i  # 데이터 시작으로 확정
            break  # 탐색 종료
    if start is None:  # 날짜 행이 없으면
        raise DataError("엑셀에서 날짜가 있는 데이터 행을 찾지 못했습니다.")  # 한글 오류 안내
    body = raw.iloc[start:].copy()  # 데이터 부분
    body.columns = ["date"] + codes  # 열 이름 지정
    body["date"] = pd.to_datetime(body["date"], errors="coerce")  # 날짜 변환
    notes = []  # 안내 목록
    bad_dates = int(body["date"].isna().sum())  # 날짜 변환 실패 수
    if bad_dates:  # 있으면
        notes.append(f"날짜를 읽지 못한 행 {bad_dates}개는 제외했습니다.")  # 안내
        body = body.dropna(subset=["date"])  # 해당 행 제외
    unknown = [c for c in codes if c and c not in known]  # 설정에 없는 코드
    if unknown:  # 있으면
        notes.append("설정에 없는 코드는 무시했습니다: " + ", ".join(unknown))  # 안내
    missing = [c for c in all_codes() if c not in codes]  # 엑셀에 없는 코드
    if missing:  # 있으면
        notes.append("엑셀에 없는 품목은 빈 열로 두었습니다: " + ", ".join(missing))  # 안내
    nonnum = 0  # 숫자가 아닌 값 수
    for c in codes:  # 코드 열마다
        if c in known:  # 알려진 코드만
            numeric = pd.to_numeric(body[c], errors="coerce")  # 숫자 변환
            nonnum += int((body[c].notna() & numeric.isna()).sum())  # 변환 실패 수 누적
    if nonnum:  # 있으면
        notes.append(f"숫자가 아닌 값 {nonnum}개는 빈 칸으로 처리했습니다.")  # 안내
    frame = _clean_frame(body.loc[:, ~body.columns.duplicated()].set_index("date"))  # 정리
    return frame, notes  # 표와 안내 반환


def upsert_row(df: pd.DataFrame, when, values: dict, allow_nonpositive: bool = False) -> tuple:  # 수동 가격 입력 함수
    """when 날짜에 values({코드: 가격})를 넣습니다. 이미 있는 날짜면 해당 품목 값만 덮어씁니다.
    (새 표, 보고서)를 돌려주며 보고서에는 추가·수정 내역과 경고가 들어 있습니다. 오류는 DataError입니다."""  # 함수 설명
    try:  # 날짜 해석 시도
        stamp = pd.Timestamp(when).normalize()  # 날짜 변환
    except Exception:  # 변환 실패
        raise DataError(f"날짜 '{when}'를 읽을 수 없습니다. YYYY-MM-DD 형식으로 써 주세요.") from None  # 한글 오류 안내
    if stamp.date() > date_cls.today() + timedelta(days=1):  # 내일보다 먼 미래이면
        raise DataError(f"{stamp:%Y-%m-%d}는 미래 날짜입니다. 날짜를 확인하세요.")  # 한글 오류 안내
    if not values:  # 입력이 없으면
        raise DataError("입력된 가격이 없습니다. 예: --date 2026-10-05 SM_FOB_KR=1420")  # 한글 오류 안내
    report = {"date": stamp.strftime("%Y-%m-%d"), "added": [], "updated": [], "warnings": []}  # 보고서 뼈대
    if stamp.weekday() >= 5:  # 주말이면
        report["warnings"].append(f"{stamp:%Y-%m-%d}는 주말입니다. 날짜가 맞는지 확인하세요.")  # 경고
    out = df.copy()  # 원본 보호
    if stamp not in out.index:  # 새 날짜이면
        out.loc[stamp] = float("nan")  # 빈 행 추가
        out = out.sort_index()  # 날짜순 정렬
    for code, price in values.items():  # 입력값을 하나씩
        item = cfg.item_by_code(code)  # 품목 정보
        if price != price or price in (float("inf"), float("-inf")):  # NaN·무한대이면
            raise DataError(f"{item['key']}의 가격이 올바른 숫자가 아닙니다.")  # 한글 오류 안내
        if price <= 0 and not allow_nonpositive:  # 0 이하이면
            raise DataError(f"{item['key']}의 가격 {price:g}은 0 이하입니다. 입력 실수가 아니라면 --allow-nonpositive 를 붙이세요.")  # 한글 오류 안내
        before = out.loc[:stamp - pd.Timedelta(days=1), code].dropna()  # 입력일 이전의 마지막 유효 가격
        if len(before) and before.iloc[-1] > 0:  # 비교할 값이 있으면
            chg = price / float(before.iloc[-1]) - 1  # 직전 대비 변화율
            if abs(chg) > cfg.BIG_MOVE:  # 급변동이면
                report["warnings"].append(f"{item['key']}: 직전 {float(before.iloc[-1]):g} → {price:g} ({chg * 100:+.1f}%) 급변동입니다. 입력 실수가 아닌지 확인하세요.")  # 경고
        old = out.at[stamp, code]  # 기존 값
        if pd.isna(old):  # 비어 있었으면
            report["added"].append((item["key"], price))  # 추가 내역
        elif old != price:  # 값이 달라지면
            report["updated"].append((item["key"], float(old), price))  # 수정 내역
        out.at[stamp, code] = price  # 값 입력
    return out, report  # 새 표와 보고서 반환


def data_report(df: pd.DataFrame) -> list:  # 데이터 현황 함수
    """품목별 마지막 날짜·유효 개수·기준일 대비 지연 정도를 목록으로 돌려줍니다."""  # 함수 설명
    latest = df.index.max()  # 전체 데이터의 마지막 날짜
    rows = []  # 결과 목록
    for it in cfg.shown_items():  # 표시 품목마다
        s = df[it["code"]].dropna()  # 유효 가격
        last = s.index.max() if len(s) else None  # 마지막 날짜
        behind = None if last is None else int((latest - last).days)  # 달력일 기준 지연
        rows.append({"key": it["key"], "label": it["label"], "freq": it["freq"], "n": int(len(s)), "last": None if last is None else last.strftime("%Y-%m-%d"), "behind_days": behind})  # 한 줄 추가
    return rows  # 목록 반환
