"""확률 예측 모듈(추세 + 볼린저 평균회귀 + 실현 변동성). 페이지의 자바스크립트 계산과 같은 공식입니다."""  # 모듈 설명
# 필요 라이브러리 설치: pip install pandas numpy
import math  # 수학 함수 사용

import pandas as pd  # 날짜 계산용

from . import config as cfg  # 설정 상수 불러오기


def norm_cdf(x: float) -> float:  # 표준정규분포 누적확률 함수
    """표준정규분포의 누적분포함수 Φ(x)를 돌려줍니다."""  # 함수 설명
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))  # 오차함수로 계산


def flat_band(t: int, bars: int, first: float, last: float) -> float:  # 보합 폭 계산 함수
    """t봉 뒤의 보합 폭(기준 종가 대비 비율)을 돌려줍니다. 1봉 뒤는 first, 마지막 봉은 last, 사이는 직선 보간입니다."""  # 함수 설명
    if bars <= 1:  # 한 봉만 예측하면
        return first  # 첫 값 사용
    return first + (last - first) * (t - 1) / (bars - 1)  # 직선 보간


def compute_forecast(closes: list, wt: float, wm: float, bars: int, below: float, above: float, win: dict, sd: float) -> dict:  # 예측 계산 함수
    """종가 목록으로 bars봉 앞까지 봉별 확률과 예측 범위를 계산합니다.

    wt: 추세 반영도(0~1), wm: 볼린저 평균회귀 반영도(0~1),
    below/above: '그 아래/위에서 마감할 확률'을 구할 가격 레벨,
    win: 주기별 프리셋(볼린저·추세 기간, 보합 폭), sd: 봉당 변동성(로그수익률 표준편차).
    """  # 함수 설명
    n = len(closes)  # 종가 개수
    need = max(win["bb"], win["trend"], win["vol"] + 1)  # 필요한 최소 종가 수
    if n < need:  # 부족하면
        raise ValueError(f"예측에 필요한 종가가 부족합니다({n}개). 최소 {need}개가 필요합니다.")  # 한글 오류 안내
    if sd <= 0:  # 변동성이 0 이하이면 확률 계산이 불가능
        raise ValueError("변동성이 0 이하라 확률을 계산할 수 없습니다.")  # 한글 오류 안내
    p0 = float(closes[-1])  # 출발점: 마지막 종가
    nb = win["bb"]  # 볼린저 기간
    window = closes[-nb:]  # 볼린저 계산 구간
    mid = sum(window) / nb  # 볼린저 중심선
    bb_sd = math.sqrt(sum((v - mid) ** 2 for v in window) / nb)  # 모표준편차
    bb_up = mid + cfg.BB_K * bb_sd  # 볼린저 상단
    bb_lo = mid - cfg.BB_K * bb_sd  # 볼린저 하단
    width = bb_up - bb_lo  # 밴드 너비
    pb = (p0 - bb_lo) / width if width > 0 else 0.5  # %b(너비 0이면 0.5)
    bw = width / mid if mid != 0 else 0.0  # 밴드폭
    nt = win["trend"]  # 추세 기간
    tail = closes[-nt:]  # 추세 계산 구간
    y_mean = sum(tail) / nt  # 구간 평균
    x_mean = (nt - 1) / 2.0  # x 평균
    num = sum((j - x_mean) * (tail[j] - y_mean) for j in range(nt))  # 기울기 분자
    den = sum((j - x_mean) ** 2 for j in range(nt))  # 기울기 분모
    slope = num / den  # 회귀 기울기(가격 단위/봉)
    g = slope / p0  # 봉당 변화율로 환산
    kappa = cfg.KAPPA_SCALE * wm  # 평균회귀 속도
    gap = math.log(mid / p0)  # 이동평균(볼린저 중심)과의 로그 간격
    rows = []  # 봉별 결과 목록
    cum_drift = 0.0  # 누적 기대 변화율
    for t in range(1, bars + 1):  # 1봉 뒤부터 bars봉 뒤까지
        m_trend = wt * g * (cfg.TREND_DECAY ** (t - 1))  # 추세 성분(봉마다 감쇠)
        m_revert = gap * (math.exp(-kappa * (t - 1)) - math.exp(-kappa * t))  # 평균회귀 성분
        m = m_trend + m_revert  # 그 봉의 기대 변화율
        cum_drift += m  # 누적에 더함
        sd_t = sd * math.sqrt(t)  # t봉 뒤 폭
        band = flat_band(t, bars, win["flat_first"], win["flat_last"])  # 그 봉의 보합 폭
        p3_up = 1.0 - norm_cdf((math.log(1.0 + band) - cum_drift) / sd_t)  # 기준 종가보다 band 넘게 오를 확률
        p3_dn = norm_cdf((math.log(1.0 - band) - cum_drift) / sd_t)  # 기준 종가보다 band 넘게 내릴 확률
        rows.append(  # 결과 한 줄 추가
            {
                "t": t,  # 몇 봉 뒤인지
                "m": m,  # 그 봉의 기대 변화율
                "p_up": norm_cdf(m / sd),  # 그 봉의 상승 확률
                "cum": norm_cdf(cum_drift / sd_t),  # 기준 종가 대비 누적 상승 확률
                "center": p0 * math.exp(cum_drift),  # 기대 종가
                "lo1": p0 * math.exp(cum_drift - sd_t),  # 1σ 하단
                "hi1": p0 * math.exp(cum_drift + sd_t),  # 1σ 상단
                "lo2": p0 * math.exp(cum_drift - 2 * sd_t),  # 2σ 하단
                "hi2": p0 * math.exp(cum_drift + 2 * sd_t),  # 2σ 상단
                "band": band,  # 보합 폭(기준 종가 대비 비율)
                "p3_up": p3_up,  # 상승 확률(보합 폭 초과)
                "p3_flat": 1.0 - p3_up - p3_dn,  # 보합 확률(±band 이내)
                "p3_dn": p3_dn,  # 하락 확률(보합 폭 초과)
                "p_below": norm_cdf((math.log(below / p0) - cum_drift) / sd_t),  # below 아래에서 마감할 확률
                "p_above": 1.0 - norm_cdf((math.log(above / p0) - cum_drift) / sd_t),  # above 위에서 마감할 확률
            }
        )
    return {  # 전체 결과 묶음
        "p0": p0,  # 출발점
        "bb": {"mid": mid, "up": bb_up, "lo": bb_lo, "sd": bb_sd},  # 볼린저 값
        "pb": pb,  # %b
        "bw": bw,  # 밴드폭
        "sd": sd,  # 봉당 변동성
        "slope": slope,  # 추세 기울기
        "rows": rows,  # 봉별 결과
    }


def level_probability(p0: float, sd: float, cum_drift: float, t: int, level: float) -> dict:  # 가격대별 확률 함수
    """t봉 뒤 종가가 level을 넘어(위) 마감할 확률과, 기준 종가에서 가까운 쪽으로 넘어 마감할 확률·장중 터치 근사를 돌려줍니다.

    p_above: t봉 뒤 종가가 level 위일 확률(누적 기대 변화율 cum_drift, 봉당 변동성 sd, 폭 sd·√t의 정규분포).
    beyond: level이 기준 종가 이상이면 p_above(넘어 마감), 아래이면 1−p_above(깨고 마감).
    touch: 기간 중 한 번이라도 닿을 확률의 근사 = min(1, 2×beyond). 반사 원리에서 온 이론 근사이며 검증하지 않았습니다.
    """  # 함수 설명
    sd_t = sd * math.sqrt(t)  # t봉 뒤 폭
    p_above = 1.0 - norm_cdf((math.log(level / p0) - cum_drift) / sd_t)  # 종가가 level 위일 확률
    up = level >= p0  # 기준 종가보다 위 레벨인지
    beyond = p_above if up else 1.0 - p_above  # 넘어(깨고) 마감할 확률
    return {"up": up, "p_above": p_above, "beyond": beyond, "touch": min(1.0, 2.0 * beyond)}  # 결과 묶음


def next_dates(last_date, n: int, freq: str, holidays=None) -> list:  # 예측 날짜 목록 함수
    """마지막 봉 다음의 예측 날짜(YYYY-MM-DD) n개를 돌려줍니다. 일간(D)은 평일, 주간(W)은 7일 간격입니다."""  # 함수 설명
    holidays = holidays if holidays is not None else set()  # 휴장일 목록 결정
    current = pd.Timestamp(last_date).normalize()  # 시작 날짜
    result = []  # 결과 목록
    if freq == "W":  # 주간이면
        for k in range(1, n + 1):  # 1주 뒤부터
            result.append((current + pd.Timedelta(days=7 * k)).strftime("%Y-%m-%d"))  # 7일 간격으로 추가
        return result  # 날짜 목록 반환
    while len(result) < n:  # 일간이면 n개를 채울 때까지
        current = current + pd.Timedelta(days=1)  # 하루 뒤로
        key = current.strftime("%Y-%m-%d")  # 날짜 문자열
        if current.weekday() < 5 and key not in holidays:  # 평일이고 휴장일이 아니면
            result.append(key)  # 목록에 추가
    return result  # 날짜 목록 반환
