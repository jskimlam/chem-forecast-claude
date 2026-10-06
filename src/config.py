"""프로젝트 전역 설정: 품목 메타데이터(전체 27개 보관, 화면에는 SHOW_CODES만 표시), 주기(일간/주간)별 지표 프리셋, 공통 상수."""  # 모듈 설명
# 필요 라이브러리 설치: pip install pandas numpy openpyxl
from pathlib import Path  # 경로를 다루기 위한 표준 모듈

ROOT = Path(__file__).resolve().parent.parent  # 프로젝트 최상위 폴더 경로
DATA_DIR = ROOT / "data"  # 데이터 폴더
SITE_DIR = ROOT / "site"  # 사이트 산출물 폴더
TEMPLATE_PATH = ROOT / "templates" / "index.html"  # 페이지 템플릿 파일 경로
PRICES_CSV = DATA_DIR / "prices.csv"  # 누적 가격 파일(날짜 + 품목 코드별 열, 오름차순)
PLACEHOLDER = "__CHEM_DATA__"  # 템플릿 안에서 데이터가 들어갈 자리 표시

# ── 그룹(탭 상단 줄) ─────────────────────────────────────────────
GROUPS = [  # 화면에 보이는 순서(상류 → 하류)
    {"id": "crude", "label": "Crude · Naphtha"},  # 원유와 납사
    {"id": "olefin", "label": "Olefin · Aromatics"},  # 에틸렌, 벤젠, 톨루엔, 프로필렌
    {"id": "sm", "label": "Styrene"},  # 스티렌모노머
    {"id": "an", "label": "Acrylonitrile"},  # 아크릴로니트릴
    {"id": "bd", "label": "Butadiene"},  # 부타디엔
    {"id": "resin", "label": "Resins"},  # ABS, PS, HIPS, PP
    {"id": "freight", "label": "Freight"},  # 액체화학품 운임
]  # 그룹 목록 끝

# ── 품목 27개 ────────────────────────────────────────────────────
# code: 플래츠 심볼(엑셀 헤더와 동일), key: 명령행에서 쓰는 짧은 영문 이름, label: 탭에 보이는 이름,
# group: 소속 그룹, unit: 가격 단위, ccy: 통화, freq: D(일간) 또는 W(주간, 가격이 주 1회만 나오는 품목)
ITEMS = [  # 품목 목록(탭 순서)
    {"code": "NMCL001", "key": "WTI_NYMEX", "label": "WTI NYMEX", "group": "crude", "unit": "BBL", "ccy": "USD", "freq": "D", "name": "NYMEX Light Sweet Crude Settlement Mo01"},
    {"code": "PCACG00", "key": "WTI_CUSHING", "label": "WTI Cushing", "group": "crude", "unit": "BBL", "ccy": "USD", "freq": "D", "name": "WTI Cushing Mo01"},
    {"code": "PAAAD00", "key": "NAPHTHA", "label": "Naphtha CFR Japan", "group": "crude", "unit": "MT", "ccy": "USD", "freq": "D", "name": "Naphtha C+F Japan Cargo $/mt (NextGen MOC)"},
    {"code": "AAOTM00", "key": "ETHYLENE", "label": "Ethylene CFR NE Asia", "group": "olefin", "unit": "MT", "ccy": "USD", "freq": "D", "name": "Ethylene CFR NE Asia"},
    {"code": "AAWWK00", "key": "PROPYLENE", "label": "Propylene CFR China", "group": "olefin", "unit": "MT", "ccy": "USD", "freq": "D", "name": "Propylene Poly Grade CFR China"},
    {"code": "PHASM05", "key": "BZ_FOB_KR", "label": "Benzene FOB Korea", "group": "olefin", "unit": "MT", "ccy": "USD", "freq": "D", "name": "Benzene FOB Korea Marker"},
    {"code": "AAOAX00", "key": "BZ_CIF_ARA", "label": "Benzene CIF ARA", "group": "olefin", "unit": "MT", "ccy": "USD", "freq": "D", "name": "Benzene CIF ARA"},
    {"code": "AAKYD00", "key": "BZ_FOB_USG", "label": "Benzene FOB USG", "group": "olefin", "unit": "GAL", "ccy": "USC", "freq": "D", "name": "Benzene FOB USG Mo02 cts/gal"},
    {"code": "PHASO05", "key": "TOLUENE", "label": "Toluene FOB Korea", "group": "olefin", "unit": "MT", "ccy": "USD", "freq": "D", "name": "Toluene FOB Korea Marker"},
    {"code": "AAMFL00", "key": "SM_FOB_KR", "label": "Styrene FOB Korea", "group": "sm", "unit": "MT", "ccy": "USD", "freq": "D", "name": "Styrene FOB Korea Marker LC 90 days"},
    {"code": "PHACB00", "key": "SM_CFR_TW", "label": "Styrene CFR Taiwan", "group": "sm", "unit": "MT", "ccy": "USD", "freq": "D", "name": "Styrene CFR Taiwan"},
    {"code": "AAMFI00", "key": "SM_CFR_CN", "label": "Styrene CFR China", "group": "sm", "unit": "MT", "ccy": "USD", "freq": "D", "name": "Styrene CFR China Marker LC 90 days"},
    {"code": "STYFC00", "key": "SM_FOB_CN", "label": "Styrene FOB China", "group": "sm", "unit": "MT", "ccy": "USD", "freq": "D", "name": "Styrene Monomer FOB China Marker"},
    {"code": "AAOTU00", "key": "SM_EAST_CN", "label": "Styrene East China (CNY)", "group": "sm", "unit": "MT", "ccy": "CNY", "freq": "D", "name": "Styrene East China Prompt Marker Yuan/mt"},
    {"code": "AAOQP00", "key": "SM_FOB_ARA", "label": "Styrene FOB ARA", "group": "sm", "unit": "MT", "ccy": "USD", "freq": "D", "name": "Styrene FOB ARA"},
    {"code": "AAIKW00", "key": "SM_FOB_USG", "label": "Styrene FOB USG", "group": "sm", "unit": "LB", "ccy": "USC", "freq": "D", "name": "Styrene FOB USG cts/lb"},
    {"code": "PHAOO00", "key": "AN_CFR_FE", "label": "Acrylonitrile CFR FE Asia", "group": "an", "unit": "MT", "ccy": "USD", "freq": "W", "name": "ACN CFR FE Asia Weekly"},
    {"code": "AAWWM00", "key": "BD_FOB_KR", "label": "Butadiene FOB Korea", "group": "bd", "unit": "MT", "ccy": "USD", "freq": "D", "name": "Butadiene FOB Korea"},
    {"code": "AAWWL00", "key": "BD_CFR_CN", "label": "Butadiene CFR China", "group": "bd", "unit": "MT", "ccy": "USD", "freq": "D", "name": "Butadiene CFR China"},
    {"code": "BTNEA00", "key": "BD_CFR_NEA", "label": "Butadiene CFR NE Asia", "group": "bd", "unit": "MT", "ccy": "USD", "freq": "D", "name": "Butadiene CFR North East Asia"},
    {"code": "AAWWU00", "key": "BD_CN_DOM", "label": "Butadiene China Domestic (CNY)", "group": "bd", "unit": "MT", "ccy": "CNY", "freq": "D", "name": "Butadiene China Domestic (Ex-Tank) Yuan/mt"},
    {"code": "PHAHF00", "key": "ABS", "label": "ABS Inj CFR China", "group": "resin", "unit": "MT", "ccy": "USD", "freq": "W", "name": "ABS Inj CFR China Weekly"},
    {"code": "PHAIL00", "key": "PS", "label": "PS GP CFR China", "group": "resin", "unit": "MT", "ccy": "USD", "freq": "W", "name": "PS G-P CFR China Weekly"},
    {"code": "PHAIR00", "key": "HIPS", "label": "HIPS CFR China", "group": "resin", "unit": "MT", "ccy": "USD", "freq": "W", "name": "HIPS CFR China Weekly"},
    {"code": "PHBIF00", "key": "PP", "label": "PP Inj CFR Far East", "group": "resin", "unit": "MT", "ccy": "USD", "freq": "D", "name": "PP Inj CFR FE Asia"},
    {"code": "AAVCC00", "key": "FRT_USG_KR", "label": "Freight USG to Korea", "group": "freight", "unit": "MT", "ccy": "USD", "freq": "D", "name": "Liquid Chemicals Freight USG-Korea 10-12 kt (daily)"},
    {"code": "AAVCA00", "key": "FRT_KR_CN", "label": "Freight Korea to East China", "group": "freight", "unit": "MT", "ccy": "USD", "freq": "D", "name": "Liquid Chemicals Freight Korea-East China 5 kt (daily)"},
]  # 품목 목록 끝

# 화면(탭)에 보일 품목 코드. 목록에 없는 품목은 가격 파일에는 남아 있지만 대시보드·입력 대상에서는 빠집니다.
# 다시 보이게 하려면 코드를 이 목록에 추가하고 `python -m src.cli build` 만 실행하면 됩니다.
SHOW_CODES = [  # 사용자가 지정한 대표 지표 12개
    "NMCL001",  # WTI (NYMEX)
    "PAAAD00",  # 납사 CFR 일본
    "AAMFI00",  # SM CFR 중국
    "AAOTU00",  # SM 동중국(위안)
    "AAOTM00",  # 에틸렌 CFR NE아시아
    "PHASM05",  # 벤젠 FOB 한국
    "AAWWK00",  # 프로필렌 CFR 중국
    "PHAOO00",  # AN CFR 극동(주간)
    "AAWWL00",  # BD CFR 중국
    "PHAIL00",  # PS GP CFR 중국(주간)
    "PHAIR00",  # HIPS CFR 중국(주간)
    "PHAHF00",  # ABS Inj CFR 중국(주간)
]  # 표시 품목 끝

UNIT_TEXT = {"BBL": "bbl", "MT": "MT", "LB": "lb", "GAL": "gal"}  # 화면에 보이는 수량 단위 표기
CCY_TEXT = {"USD": "USD", "CNY": "CNY", "USC": "USc"}  # 화면에 보이는 통화 표기(USC는 미국 센트)

# ── 주기별 지표 프리셋 ───────────────────────────────────────────
# 일간: WTI 앱과 같은 값(20일 볼린저, 5·10·20·60일선, RSI 14, MACD 12·26·9).
# 주간: 같은 기간을 주 단위로 환산(13주 ≈ 1분기, 26주 ≈ 반년)한 값. 모두 제가 정한 가정이며 검증하지 않았습니다.
WINDOWS = {  # 주기별 프리셋 묶음
    "D": {  # 일간
        "unit": "일",  # 봉 한 개의 단위 표기
        "bb": 20,  # 볼린저밴드 기간
        "vol": 20,  # 변동성(로그수익률 표준편차) 계산에 쓰는 수익률 개수
        "trend": 10,  # 추세(회귀 기울기) 계산 기간
        "ma": (5, 10, 20, 60),  # 이동평균 4개(마지막이 장기선)
        "longs": (50, 100, 200),  # 해설에서 위치를 알려주는 장기 이동평균 기간
        "rsi": 14,  # RSI 기간(와일더)
        "macd": (12, 26, 9),  # MACD 단기·장기·시그널 기간
        "ma_slope_bars": 5,  # 장기선 기울기를 볼 때 비교하는 봉 간격
        "ma_slope_flat": 0.001,  # 장기선 기울기가 이 비율 이내면 횡보로 봄
        "high_fall": -0.002,  # 고점이 한 봉에 이 비율 이하로 내려가면 '하락'으로 봄
        "swing_k": 3,  # 다이버전스용 스윙 판정에서 양옆으로 비교하는 봉 수
        "div_window": 40,  # 다이버전스를 찾는 최근 봉 수
        "forecast_bars": 5,  # 예측할 봉 수
        "flat_first": 0.005,  # 보합 폭: 다음 봉 기준 종가 대비 ±0.5%
        "flat_last": 0.010,  # 보합 폭: 마지막 예측 봉 기준 종가 대비 ±1.0%
        "year_bars": 250,  # 약 1년에 해당하는 봉 수(가격 위치 계산용)
        "stale_warn": 0.40,  # 최근 60봉 중 전봉과 같은 가격 비율이 이 값 이상이면 경고
    },  # 일간 끝
    "W": {  # 주간
        "unit": "주",  # 봉 한 개의 단위 표기
        "bb": 13,  # 볼린저밴드 기간(13주)
        "vol": 13,  # 변동성 계산에 쓰는 수익률 개수
        "trend": 6,  # 추세 계산 기간
        "ma": (4, 8, 13, 26),  # 이동평균 4개(마지막이 장기선)
        "longs": (26, 52, 104),  # 해설에서 위치를 알려주는 장기 이동평균 기간
        "rsi": 9,  # RSI 기간
        "macd": (6, 13, 5),  # MACD 기간(일간 12·26·9를 절반으로 환산)
        "ma_slope_bars": 4,  # 장기선 기울기 비교 봉 간격
        "ma_slope_flat": 0.0025,  # 장기선 기울기 횡보 기준
        "high_fall": -0.005,  # 고점 하락 판정 기준
        "swing_k": 2,  # 스윙 판정 봉 수
        "div_window": 26,  # 다이버전스를 찾는 최근 봉 수
        "forecast_bars": 4,  # 예측할 봉 수(4주)
        "flat_first": 0.010,  # 보합 폭: 다음 주 기준 종가 대비 ±1.0%
        "flat_last": 0.020,  # 보합 폭: 4주 뒤 기준 종가 대비 ±2.0%
        "year_bars": 52,  # 약 1년에 해당하는 봉 수
        "stale_warn": 0.60,  # 전봉과 같은 가격 비율 경고 기준(주간은 원래 같은 값이 잦아 높게 둠)
    },  # 주간 끝
}  # 프리셋 끝

# ── 모델 상수(WTI 앱과 동일) ─────────────────────────────────────
BB_K = 2.0  # 볼린저밴드 표준편차 배수
TREND_DECAY = 0.8  # 추세가 한 봉마다 남는 비율(20%씩 감쇠)
KAPPA_SCALE = 0.10  # 평균회귀 속도 배율(반영도 1일 때 한 봉에 약 10%)
DEFAULT_WT = 0.5  # 추세 반영도 기본값
DEFAULT_WM = 0.5  # 평균회귀 반영도 기본값
EDGE_MIN_GAP = 0.10  # 상승·하락 확률 차이가 이 값보다 작으면 '우위 없음'
RSI_HIGH = 70.0  # RSI 과매수권 기준
RSI_LOW = 30.0  # RSI 과매도권 기준

SD_MIN = 1e-4  # 변동성이 이 값(0.01%)보다 작으면 '거의 0'으로 보고 더 긴 구간으로 다시 계산
SD_FLOOR = 1e-3  # 어떤 구간으로도 변동성이 안 잡히면 쓰는 하한(0.1%)

# ── 지지·저항·패턴 탐지 상수 ─────────────────────────────────────
LEVEL_LOOKBACK = 60  # 지지·저항 탐지에 쓰는 최근 봉 개수
LEVEL_CLUSTER_TOL = 0.006  # 스윙 고저점을 한 레벨로 묶는 허용 비율
LEVEL_MERGE_TOL = 0.0035  # 서로 가까운 레벨을 하나로 합치는 허용 비율
LEVELS_PER_SIDE = 5  # 현재가 위·아래로 각각 표시할 레벨 수
FIB_WINDOW = 40  # 피보나치 계산에 쓰는 최근 봉 개수
FLOOR_WINDOW = 30  # 바닥 밴드 탐지에 쓰는 최근 봉 개수
FLOOR_TOL = 0.005  # 바닥 밴드 두께 비율
FLOOR_MIN_TOUCHES = 3  # 바닥 밴드로 인정할 최소 터치 횟수(연속 구간은 1번으로 셈)
HIGH_TREND_WINDOW = 10  # 고점 추세선 계산 기간
PSY_STEP_PCT = 0.05  # 심리선(라운드 넘버) 간격을 현재가의 약 5%로 잡고 1·2·5 계열로 맞춤

# ── 화면·검증 상수 ───────────────────────────────────────────────
VIEW_BARS = 60  # 차트에 보여줄 봉 개수
JSON_BARS = 130  # 페이지 데이터에 담을 봉 개수(가장 긴 이동평균 계산 여유 포함)
BIG_MOVE = 0.25  # 한 봉 변동이 이 비율을 넘으면 급변동으로 표시
STALE_LOOKBACK = 60  # 정체 가격 비율을 보는 최근 봉 수
STALE_DAYS_DAILY = 1  # 일간 품목이 기준일보다 이 영업일 이상 늦으면 '미갱신'
STALE_DAYS_WEEKLY = 10  # 주간 품목이 기준일보다 이 달력일 이상 늦으면 '미갱신'
KST_NAME = "KST"  # 생성 시각 표기에 쓰는 시간대 이름


def shown_items() -> list:  # 화면에 보일 품목 목록 함수
    """SHOW_CODES에 든 품목만 ITEMS의 탭 순서대로 돌려줍니다."""  # 함수 설명
    return [it for it in ITEMS if it["code"] in SHOW_CODES]  # 표시 대상만 추려 반환


def shown_groups() -> list:  # 화면에 보일 그룹 목록 함수
    """표시 품목이 하나라도 있는 그룹만 돌려줍니다."""  # 함수 설명
    used = {it["group"] for it in shown_items()}  # 표시 품목이 속한 그룹
    return [g for g in GROUPS if g["id"] in used]  # 비어 있지 않은 그룹만


def item_by_code(code: str) -> dict:  # 코드로 품목 찾기 함수
    """플래츠 코드로 품목 정보를 돌려줍니다. 없으면 ValueError(한글 안내)입니다."""  # 함수 설명
    for it in ITEMS:  # 품목을 하나씩 확인
        if it["code"] == code:  # 코드가 같으면
            return it  # 해당 품목 반환
    raise ValueError(f"알 수 없는 품목 코드입니다: {code}")  # 한글 오류 안내


def unit_label(item: dict) -> str:  # 단위 표기 함수
    """'USD/MT', 'USc/lb' 같은 단위 문자열을 만듭니다."""  # 함수 설명
    return f"{CCY_TEXT[item['ccy']]}/{UNIT_TEXT[item['unit']]}"  # 통화/수량 단위 조합


def digits_for(price: float) -> int:  # 표시 소수 자릿수 결정 함수
    """가격 크기에 맞는 소수 자릿수를 돌려줍니다(1000 이상 0자리, 100 이상 1자리, 그 밖은 2자리)."""  # 함수 설명
    if price >= 1000:  # 천 단위 이상이면
        return 0  # 정수로 표시
    if price >= 100:  # 백 단위이면
        return 1  # 소수 한 자리
    return 2  # 그 밖은 소수 두 자리
