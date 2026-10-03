"""구글시트 동기화 모듈: Apps Script 웹앱에서 가격 데이터를 내려받아 data/prices.csv 로 저장합니다. 모든 오류는 한글로 안내합니다."""  # 모듈 설명
# 필요 라이브러리 설치: pip install pandas numpy openpyxl
import json  # JSON 해석용
import urllib.error  # 통신 오류 구분용
import urllib.parse  # 주소 만들기용
import urllib.request  # 웹 요청용
from pathlib import Path  # 경로 처리용

import pandas as pd  # 표 데이터 처리용

from . import config as cfg  # 설정 상수 불러오기
from .data_io import DataError, _clean_frame, read_prices, write_prices  # 가격 표 정리·입출력


def build_url(base_url: str, token: str) -> str:  # 요청 주소 만들기 함수
    """웹앱 주소에 action=data 와 토큰을 붙여 돌려줍니다."""  # 함수 설명
    if not base_url or not base_url.strip():  # 주소가 비어 있으면
        raise DataError("웹앱 주소가 없습니다. --url 또는 환경변수 CHEM_GAS_URL 을 설정하세요.")  # 한글 오류 안내
    if not token or not token.strip():  # 토큰이 비어 있으면
        raise DataError("읽기 토큰이 없습니다. --token 또는 환경변수 CHEM_GAS_TOKEN 을 설정하세요.")  # 한글 오류 안내
    sep = "&" if "?" in base_url else "?"  # 주소에 이미 인자가 있는지에 따라 연결 문자 선택
    return base_url.strip() + sep + urllib.parse.urlencode({"action": "data", "token": token.strip()})  # 인자 붙이기


def fetch_payload(base_url: str, token: str, timeout: int = 90) -> dict:  # 웹앱 호출 함수
    """웹앱에서 가격 데이터(JSON)를 받아 사전으로 돌려줍니다. 토큰이 틀리거나 형식이 다르면 한글 오류를 냅니다."""  # 함수 설명
    url = build_url(base_url, token)  # 요청 주소
    try:  # 요청 시도
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # 웹 요청(리다이렉트는 자동으로 따라감)
            text = resp.read().decode("utf-8")  # 응답 본문
    except urllib.error.HTTPError as exc:  # HTTP 오류 응답
        raise DataError(f"웹앱이 오류를 돌려줬습니다(HTTP {exc.code}). 배포 주소와 액세스 권한('모든 사용자')을 확인하세요.") from None  # 한글 오류 안내
    except Exception as exc:  # 통신 실패
        raise DataError(f"웹앱에 연결하지 못했습니다: {exc}") from None  # 한글 오류 안내
    try:  # JSON 해석 시도
        payload = json.loads(text)  # 해석
    except json.JSONDecodeError:  # JSON이 아니면
        raise DataError("웹앱 응답을 읽지 못했습니다. 배포 주소가 맞는지, 로그인 화면이 대신 열리지 않는지 확인하세요.") from None  # 한글 오류 안내
    if not isinstance(payload, dict) or not payload.get("ok"):  # 실패 응답이면
        message = payload.get("error") if isinstance(payload, dict) else None  # 서버가 준 사유
        raise DataError(f"시트에서 데이터를 받지 못했습니다: {message or '알 수 없는 오류'}")  # 한글 오류 안내
    return payload  # 성공 응답 반환


def payload_to_frame(payload: dict) -> tuple:  # 응답을 가격 표로 바꾸는 함수
    """{codes, rows:[[날짜, 값...]]} 응답을 (가격 표, 안내 목록)으로 바꿉니다. 모르는 코드는 무시하고 안내합니다."""  # 함수 설명
    codes = payload.get("codes")  # 시트의 코드 목록
    rows = payload.get("rows")  # 날짜별 값
    if not isinstance(codes, list) or not isinstance(rows, list):  # 형식이 다르면
        raise DataError("시트 데이터 형식이 올바르지 않습니다(codes/rows 없음).")  # 한글 오류 안내
    if not rows:  # 데이터가 없으면
        raise DataError("시트에 가격 데이터 행이 없습니다. 헤더 아래에 날짜별 가격을 넣어 주세요.")  # 한글 오류 안내
    known = {it["code"] for it in cfg.ITEMS}  # 알려진 코드
    notes = []  # 안내 목록
    unknown = [c for c in codes if c not in known]  # 설정에 없는 코드
    if unknown:  # 있으면
        notes.append("설정에 없는 코드는 무시했습니다: " + ", ".join(unknown))  # 안내
    missing = [c for c in cfg.SHOW_CODES if c not in codes]  # 시트에 없는 표시 품목
    if missing:  # 있으면
        notes.append("시트에 없는 표시 품목: " + ", ".join(missing) + " (해당 탭은 데이터 부족으로 표시됩니다)")  # 안내
    width = len(codes) + 1  # 한 행의 기대 길이
    clean_rows = []  # 정리된 행
    for r in rows:  # 행마다
        if not isinstance(r, list) or len(r) != width:  # 길이가 다르면
            raise DataError(f"시트 데이터 행 길이가 헤더와 다릅니다: {r!r:.80}")  # 한글 오류 안내
        clean_rows.append(r)  # 통과한 행 저장
    frame = pd.DataFrame(clean_rows, columns=["date"] + list(codes))  # 표 만들기
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")  # 날짜 변환
    bad = int(frame["date"].isna().sum())  # 날짜를 읽지 못한 행 수
    if bad:  # 있으면
        notes.append(f"날짜를 읽지 못한 행 {bad}개는 제외했습니다.")  # 안내
        frame = frame.dropna(subset=["date"])  # 해당 행 제외
    frame = frame.loc[:, ~frame.columns.duplicated()].set_index("date")  # 중복 열 제거 후 날짜 인덱스
    return _clean_frame(frame), notes  # 정리해서 반환


def count_values(frame: pd.DataFrame) -> int:  # 표시 품목의 유효 값 개수 함수
    """표시 품목 열의 비어 있지 않은 값 개수를 돌려줍니다(기존 파일과 규모를 비교할 때 사용)."""  # 함수 설명
    cols = [c for c in cfg.SHOW_CODES if c in frame.columns]  # 표시 품목 열
    return int(frame[cols].notna().sum().sum()) if cols else 0  # 값 개수 합


def sync_prices(base_url: str, token: str, path: Path = None, fetcher=fetch_payload) -> tuple:  # 동기화 함수
    """시트 데이터를 내려받아 prices.csv 로 저장하고 (가격 표, 안내 목록)을 돌려줍니다.
    기존 파일이 있고 새 데이터가 절반 미만이면(시트가 비었거나 일부만 올라온 경우) 덮어쓰지 않고 오류를 냅니다."""  # 함수 설명
    path = Path(path) if path else cfg.PRICES_CSV  # 저장 경로
    payload = fetcher(base_url, token)  # 시트 데이터 받기
    frame, notes = payload_to_frame(payload)  # 표로 변환
    if path.exists():  # 기존 파일이 있으면
        old = read_prices(path)  # 기존 데이터
        old_n, new_n = count_values(old), count_values(frame)  # 규모 비교
        if old_n and new_n < old_n * 0.5:  # 크게 줄었으면
            raise DataError(f"시트 데이터({new_n}개 값)가 기존 파일({old_n}개 값)의 절반 미만이라 덮어쓰지 않았습니다. 시트 내용을 확인하세요.")  # 한글 오류 안내
        backup = path.with_suffix(".csv.bak")  # 백업 경로
        backup.write_bytes(path.read_bytes())  # 기존 파일 백업
        notes.append(f"기존 파일을 {backup.name} 로 백업했습니다.")  # 안내
    write_prices(frame, path)  # 저장
    return frame, notes  # 결과 반환
