"""기술 지표 계산 모듈(이동평균, 볼린저밴드, RSI, MACD, 변동성, 추세 기울기). 종가만 사용합니다."""  # 모듈 설명
# 필요 라이브러리 설치: pip install pandas numpy
import numpy as np  # 수치 계산용
import pandas as pd  # 표 데이터 처리용

from . import config as cfg  # 설정 상수 불러오기


def sma(close: pd.Series, n: int) -> pd.Series:  # 단순이동평균 함수
    """종가의 n봉 단순이동평균을 돌려줍니다."""  # 함수 설명
    return close.rolling(n).mean()  # n봉 평균 계산


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:  # 볼린저밴드 함수
    """볼린저밴드를 계산합니다. 표준편차는 관례대로 모표준편차(ddof=0)를 씁니다.
    밴드 폭이 0(n봉 내내 같은 가격)이면 %b는 0.5, 밴드폭은 0으로 둡니다."""  # 함수 설명
    mid = close.rolling(n).mean()  # 중심선(n봉 이동평균)
    sd = close.rolling(n).std(ddof=0)  # n봉 모표준편차
    up = mid + k * sd  # 상단 밴드
    lo = mid - k * sd  # 하단 밴드
    width = up - lo  # 밴드 너비
    pb = ((close - lo) / width).where(width > 0, 0.5)  # %b: 밴드 안의 위치(너비 0이면 0.5)
    pb = pb.where(mid.notna())  # 중심선이 없는 앞쪽 구간은 비움
    bw = (width / mid).where(mid != 0, 0.0)  # 밴드폭: 너비를 중심선으로 나눈 비율
    return pd.DataFrame({"mid": mid, "up": up, "lo": lo, "pb": pb, "bw": bw})  # 표로 묶어 반환


def log_returns(close: pd.Series) -> pd.Series:  # 로그수익률 함수
    """양수 가격끼리의 로그수익률만 돌려줍니다. 0 이하 가격(예: 2020-04 WTI 음수 가격)이 낀 구간은 제외합니다."""  # 함수 설명
    prev = close.shift()  # 직전 봉 가격
    ok = (close > 0) & (prev > 0)  # 두 가격이 모두 양수인 봉만
    rets = np.log((close / prev).where(ok))  # 조건을 만족하는 봉만 계산(나머지는 결측으로 두어 로그 경고를 막음)
    return rets.dropna()  # 결측 제거


def realized_vol(close: pd.Series, n: int = 20) -> float:  # 실현 변동성 함수
    """최근 n개 로그수익률의 표본표준편차(봉당 변동성)를 돌려줍니다."""  # 함수 설명
    rets = log_returns(close).tail(n)  # 최근 n개 로그수익률
    if len(rets) < n:  # 수익률이 부족하면
        raise ValueError(f"변동성 계산에 필요한 수익률이 부족합니다({len(rets)}/{n}).")  # 한글 오류 안내
    return float(rets.std(ddof=1))  # 표본표준편차 반환


def robust_vol(close: pd.Series, n: int = 20) -> tuple:  # 방어적 변동성 함수
    """최근 n봉 변동성을 돌려주되, 거의 0이면(가격이 계속 그대로) 3배 구간 → 전체 구간 순으로 넓혀 다시 계산합니다.
    그래도 0이면 하한(SD_FLOOR)을 씁니다. (변동성, 안내 문구 또는 None)을 돌려줍니다."""  # 함수 설명
    sd = realized_vol(close, n)  # 기본 변동성
    if sd >= cfg.SD_MIN:  # 충분히 크면
        return sd, None  # 그대로 사용
    rets_all = log_returns(close)  # 전체 로그수익률
    for span in (n * 3, len(rets_all)):  # 구간을 넓혀가며
        if span <= n or len(rets_all) < span:  # 쓸 수 없는 구간이면
            continue  # 건너뜀
        wide = float(rets_all.tail(span).std(ddof=1))  # 넓힌 구간 변동성
        if wide >= cfg.SD_MIN:  # 값이 잡히면
            return wide, f"최근 {n}봉 가격이 거의 변하지 않아 변동성을 최근 {span}봉 기준으로 대체했습니다."  # 대체 사용
    return cfg.SD_FLOOR, f"변동성이 잡히지 않아 하한 {cfg.SD_FLOOR * 100:.1f}%를 적용했습니다."  # 하한 적용


def linear_fit(values: np.ndarray):  # 단순 회귀직선 함수
    """0,1,2... 을 x로 한 최소제곱 직선의 기울기와 절편을 돌려줍니다."""  # 함수 설명
    x = np.arange(len(values), dtype=float)  # x축: 봉 순번
    x_mean = x.mean()  # x 평균
    y_mean = float(np.mean(values))  # y 평균
    slope = float(((x - x_mean) * (values - y_mean)).sum() / ((x - x_mean) ** 2).sum())  # 기울기
    intercept = y_mean - slope * x_mean  # 절편
    return slope, intercept  # 기울기와 절편 반환


def trend_slope(close: pd.Series, n: int = 10) -> float:  # 추세 기울기 함수
    """최근 n봉 종가의 회귀 기울기(가격 단위/봉)를 돌려줍니다."""  # 함수 설명
    if len(close) < n:  # 봉이 부족하면
        raise ValueError(f"추세 계산에 필요한 봉이 부족합니다({len(close)}/{n}).")  # 한글 오류 안내
    values = close.tail(n).to_numpy(dtype=float)  # 최근 n봉 종가 배열
    slope, _ = linear_fit(values)  # 회귀 기울기 계산
    return slope  # 기울기 반환


def ema(close: pd.Series, n: int) -> pd.Series:  # 지수이동평균 함수
    """종가의 n봉 지수이동평균(span=n, 첫 값에서 시작)을 돌려줍니다. 초반 봉은 증권사마다 조금 다를 수 있고 수십 봉이 지나면 차이가 사라집니다."""  # 함수 설명
    return close.ewm(span=n, adjust=False).mean()  # 지수이동평균 계산


def rsi_wilder(close: pd.Series, n: int = 14) -> pd.Series:  # RSI 함수
    """Wilder 방식 RSI를 계산합니다. 첫 평균은 처음 n개 변화량의 단순평균, 이후는 (이전 평균×(n-1)+이번 값)/n 으로 이어갑니다. 앞쪽 n개 봉은 NaN입니다."""  # 함수 설명
    values = close.to_numpy(dtype=float)  # 종가 배열
    out = np.full(len(values), np.nan)  # 결과 배열(처음엔 NaN)
    if len(values) <= n:  # 봉이 부족하면
        return pd.Series(out, index=close.index)  # 전부 NaN으로 반환
    delta = np.diff(values)  # 전봉 대비 변화량
    gain = np.where(delta > 0, delta, 0.0)  # 상승분
    loss = np.where(delta < 0, -delta, 0.0)  # 하락분(양수로)
    avg_gain = gain[:n].mean()  # 첫 평균 상승폭
    avg_loss = loss[:n].mean()  # 첫 평균 하락폭
    for i in range(n, len(values)):  # n번째 봉부터 값이 나옴
        if i > n:  # 첫 값 이후에는 Wilder 평활
            avg_gain = (avg_gain * (n - 1) + gain[i - 1]) / n  # 평균 상승폭 갱신
            avg_loss = (avg_loss * (n - 1) + loss[i - 1]) / n  # 평균 하락폭 갱신
        if avg_loss == 0:  # 하락이 전혀 없으면
            out[i] = 50.0 if avg_gain == 0 else 100.0  # 변화 없음은 50, 상승만 있으면 100
        else:  # 일반적인 경우
            out[i] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)  # RSI 공식
    return pd.Series(out, index=close.index)  # 시리즈로 반환


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:  # MACD 함수
    """MACD선(단기EMA−장기EMA), 시그널선(MACD의 EMA), 히스토그램(MACD−시그널)을 계산합니다. MACD는 slow봉, 시그널은 그로부터 signal봉이 지난 뒤부터 값이 있습니다."""  # 함수 설명
    line = ema(close, fast) - ema(close, slow)  # MACD선
    line.iloc[: slow - 1] = np.nan  # 장기 EMA가 자리 잡기 전 구간은 비움
    valid = line.dropna()  # 유효 구간
    sig = pd.Series(np.nan, index=close.index)  # 시그널선(처음엔 NaN)
    if len(valid) >= signal:  # 유효 구간이 충분하면
        sig.loc[valid.index] = valid.ewm(span=signal, adjust=False).mean()  # 유효 구간에서 시그널 계산
        sig.iloc[: slow - 1 + signal - 1] = np.nan  # 시그널이 자리 잡기 전 구간은 비움
    hist = line - sig  # 히스토그램
    return pd.DataFrame({"macd": line, "signal": sig, "hist": hist})  # 표로 묶어 반환
