"""지표 상태 요약 모듈: 장기선, RSI, MACD의 현재 상태를 한글 문장으로 정리합니다(해석용, 예측 확률에는 반영하지 않음)."""  # 모듈 설명
# 필요 라이브러리 설치: pip install pandas numpy
import numpy as np  # 수치 계산용
import pandas as pd  # 표 데이터 처리용

from . import config as cfg  # 설정 상수 불러오기
from .indicators import macd, rsi_wilder, sma  # 지표 계산 함수


def compute_series(prices: pd.DataFrame, win: dict) -> pd.DataFrame:  # 지표 시계열 계산 함수
    """종가로 이동평균·RSI·MACD 시계열을 한 번에 계산해 표로 돌려줍니다. ma_mid는 장기선과 교차를 볼 세 번째 이동평균, ma_long은 장기선입니다."""  # 함수 설명
    close = prices["close"].astype(float).reset_index(drop=True)  # 종가 열
    out = pd.DataFrame({"date": pd.to_datetime(prices["date"]).reset_index(drop=True), "close": close})  # 기본 표
    out["ma_mid"] = sma(close, win["ma"][2])  # 세 번째 이동평균(교차 비교 대상)
    out["ma_long"] = sma(close, win["ma"][3])  # 장기선
    out["rsi"] = rsi_wilder(close, win["rsi"])  # RSI
    fast, slow, sig = win["macd"]  # MACD 기간 세 개
    m = macd(close, fast, slow, sig)  # MACD 묶음
    out["macd"] = m["macd"]  # MACD선
    out["signal"] = m["signal"]  # 시그널선
    out["hist"] = m["hist"]  # 히스토그램
    return out  # 표 반환


def last_cross(a: pd.Series, b: pd.Series):  # 마지막 교차 찾기 함수
    """a가 b를 위로 뚫은 가장 최근 시점(골든)이나 아래로 뚫은 시점(데드)을 찾아 (방향, 위치)로 돌려줍니다. 없으면 None입니다."""  # 함수 설명
    diff = (a - b).to_numpy(dtype=float)  # 두 선의 차이
    sign = np.sign(diff)  # 부호(위 +1, 아래 −1)
    for i in range(len(diff) - 1, 0, -1):  # 뒤에서부터 거슬러 올라가며
        if np.isnan(sign[i]) or np.isnan(sign[i - 1]) or sign[i] == 0:  # 값이 없거나 같으면
            continue  # 건너뜀
        j = i - 1  # 직전 봉부터
        while j >= 0 and sign[j] == 0:  # 같은 값이었던 봉은 건너뛰고
            j -= 1  # 더 앞으로
        if j < 0 or np.isnan(sign[j]):  # 비교할 값이 없으면
            return None  # 교차 없음
        if sign[i] != sign[j]:  # 부호가 바뀌었으면
            return ("golden" if sign[i] > 0 else "dead", i)  # 교차 방향과 위치
    return None  # 교차 없음


def swing_points(values: np.ndarray, k: int):  # 스윙 저점·고점 찾기 함수
    """양옆 k봉보다 낮은(높은) 봉을 저점(고점)으로 봅니다. 마지막 k봉은 확정되지 않아 제외합니다. (저점 위치들, 고점 위치들)을 돌려줍니다."""  # 함수 설명
    lows, highs = [], []  # 결과 목록
    for i in range(k, len(values) - k):  # 양옆에 k봉이 있는 구간만
        window = values[i - k : i + k + 1]  # 비교 구간
        if np.isnan(window).any():  # 값이 없으면
            continue  # 건너뜀
        if values[i] == window.min() and (window == values[i]).sum() == 1:  # 유일한 최저
            lows.append(i)  # 저점 추가
        if values[i] == window.max() and (window == values[i]).sum() == 1:  # 유일한 최고
            highs.append(i)  # 고점 추가
    return lows, highs  # 결과 반환


def find_divergence(series: pd.DataFrame, win: dict):  # 다이버전스 탐지 함수
    """최근 div_window봉에서 마지막 두 스윙 저점·고점의 가격과 RSI를 비교합니다.
    가격 저점은 낮아졌는데 RSI 저점은 높아졌으면 강세, 가격 고점은 높아졌는데 RSI 고점은 낮아졌으면 약세 다이버전스로 봅니다.
    규칙으로 찾은 단순 해석이며 신호의 신뢰도는 검증되지 않았습니다. 없으면 None입니다."""  # 함수 설명
    tail = series.tail(win["div_window"]).reset_index(drop=True)  # 최근 구간
    close = tail["close"].to_numpy(dtype=float)  # 종가
    rsi = tail["rsi"].to_numpy(dtype=float)  # RSI
    lows, highs = swing_points(close, win["swing_k"])  # 스윙 점
    found = []  # 찾은 결과
    if len(lows) >= 2:  # 저점이 둘 이상이면
        a, b = lows[-2], lows[-1]  # 마지막 두 저점
        if not (np.isnan(rsi[a]) or np.isnan(rsi[b])) and close[b] < close[a] * 0.998 and rsi[b] > rsi[a] + 2.0:  # 가격은 낮아지고 RSI는 높아짐
            found.append(("bull", tail["date"].iloc[a], tail["date"].iloc[b], b))  # 강세 다이버전스
    if len(highs) >= 2:  # 고점이 둘 이상이면
        a, b = highs[-2], highs[-1]  # 마지막 두 고점
        if not (np.isnan(rsi[a]) or np.isnan(rsi[b])) and close[b] > close[a] * 1.002 and rsi[b] < rsi[a] - 2.0:  # 가격은 높아지고 RSI는 낮아짐
            found.append(("bear", tail["date"].iloc[a], tail["date"].iloc[b], b))  # 약세 다이버전스
    if not found:  # 없으면
        return None  # 없음
    found.sort(key=lambda x: x[3])  # 더 최근 것을 뒤로
    kind, d1, d2, _ = found[-1]  # 가장 최근 것
    return {"kind": kind, "date1": pd.Timestamp(d1).strftime("%m/%d"), "date2": pd.Timestamp(d2).strftime("%m/%d")}  # 결과 반환


def fmt_cross(cross, dates: pd.Series, n_bars: int, up_word: str, down_word: str, unit: str) -> str:  # 교차 문장 함수
    """교차 정보를 'N봉 전 (월/일) 골든' 형태의 문장으로 만듭니다."""  # 함수 설명
    if cross is None:  # 교차가 없으면
        return "최근 구간에 교차가 없습니다"  # 안내
    kind, pos = cross  # 방향과 위치
    ago = n_bars - 1 - pos  # 몇 봉 전인지
    day = pd.Timestamp(dates.iloc[pos]).strftime("%m/%d")  # 교차한 날짜
    word = up_word if kind == "golden" else down_word  # 방향 단어
    return f"{ago}{unit} 전({day}) {word}"  # 문장 반환(봉 단위는 일 또는 주)


def build_signals(prices: pd.DataFrame, win: dict, digits: int) -> list:  # 지표 상태 요약 함수
    """장기선·RSI·MACD의 현재 상태를 [{key, name, value, reading, tone}] 목록으로 돌려줍니다. tone은 up(강세 쪽)/dn(약세 쪽)/neutral 입니다."""  # 함수 설명
    s = compute_series(prices, win)  # 지표 시계열
    n = len(s)  # 봉 개수
    last = s.iloc[-1]  # 마지막 봉
    close = float(last["close"])  # 마지막 종가
    unit = win["unit"]  # 봉 단위(일/주)
    p_mid, p_long = win["ma"][2], win["ma"][3]  # 교차를 보는 두 이동평균 기간
    md = max(1, digits)  # MACD 값 표시 자릿수
    rows = []  # 결과 목록

    # 장기선
    long_name = f"{p_long}{unit}선"  # 장기선 이름
    if pd.isna(last["ma_long"]):  # 봉이 부족하면
        rows.append({"key": "ma_long", "name": long_name, "value": "계산 불가", "reading": f"봉이 {p_long}개 필요합니다(현재 {n}개).", "tone": "neutral"})  # 안내
    else:  # 계산 가능하면
        ma_l = float(last["ma_long"])  # 장기선 값
        gap = (close / ma_l - 1) * 100  # 종가와 장기선의 간격(%)
        nb = win["ma_slope_bars"]  # 기울기 비교 간격
        prev = s["ma_long"].iloc[-1 - nb] if n > nb else np.nan  # 몇 봉 전 장기선
        slope = (ma_l / prev - 1) if not pd.isna(prev) and prev > 0 else None  # 간격 동안의 변화율
        if slope is None:  # 비교 불가
            slope_text, slope_tone = "기울기 계산 불가", 0  # 기울기 없음
        elif slope > win["ma_slope_flat"]:  # 상승
            slope_text, slope_tone = f"{long_name}은 상승 중({slope * 100:+.2f}%/{nb}{unit})", 1  # 상승 문장
        elif slope < -win["ma_slope_flat"]:  # 하락
            slope_text, slope_tone = f"{long_name}은 하락 중({slope * 100:+.2f}%/{nb}{unit})", -1  # 하락 문장
        else:  # 횡보
            slope_text, slope_tone = f"{long_name}은 횡보({slope * 100:+.2f}%/{nb}{unit})", 0  # 횡보 문장
        side = 1 if close > ma_l else -1  # 종가가 선 위(+1)인지 아래(−1)인지
        cross = last_cross(s["ma_mid"], s["ma_long"])  # 중기선과 장기선의 교차
        cross_text = f"{p_mid}{unit}선–{p_long}{unit}선: " + fmt_cross(cross, s["date"], n, "골든크로스", "데드크로스", unit)  # 교차 문장
        pos_text = f"종가는 {long_name} " + ("위" if side > 0 else "아래")  # 위치 문장
        score = side + slope_tone  # 위치와 기울기를 합친 방향성
        tone = "up" if score >= 1 else "dn" if score <= -1 else "neutral"  # 톤 결정
        rows.append({"key": "ma_long", "name": long_name, "value": f"{ma_l:,.{digits}f} (종가 대비 {gap:+.1f}%)", "reading": f"{pos_text}, {slope_text}. {cross_text}.", "tone": tone})  # 행 추가

    # RSI
    rn = win["rsi"]  # RSI 기간
    if pd.isna(last["rsi"]):  # 봉이 부족하면
        rows.append({"key": "rsi", "name": f"RSI({rn})", "value": "계산 불가", "reading": f"봉이 {rn + 1}개 필요합니다.", "tone": "neutral"})  # 안내
    else:  # 계산 가능하면
        r = float(last["rsi"])  # RSI 값
        if r >= cfg.RSI_HIGH:  # 과매수
            zone, tone = f"{cfg.RSI_HIGH:.0f} 이상 과매수권(되돌림 주의)", "neutral"  # 과매수 문장
        elif r <= cfg.RSI_LOW:  # 과매도
            zone, tone = f"{cfg.RSI_LOW:.0f} 이하 과매도권(반등 가능성 구간)", "neutral"  # 과매도 문장
        elif r > 50:  # 50 위
            zone, tone = "중립권, 50 위(상승 쪽 힘이 조금 우세)", "up"  # 50 위 문장
        else:  # 50 아래
            zone, tone = "중립권, 50 아래(하락 쪽 힘이 조금 우세)", "dn"  # 50 아래 문장
        div = find_divergence(s, win)  # 다이버전스
        div_text = ""  # 다이버전스 문장
        if div:  # 있으면
            div_text = (" 강세 다이버전스 가능성: 가격 저점은 낮아졌는데 RSI 저점은 높아졌습니다(" if div["kind"] == "bull" else " 약세 다이버전스 가능성: 가격 고점은 높아졌는데 RSI 고점은 낮아졌습니다(") + f"{div['date1']}→{div['date2']})."  # 문장 구성
        rows.append({"key": "rsi", "name": f"RSI({rn})", "value": f"{r:.1f}", "reading": zone + "." + div_text, "tone": tone})  # 행 추가

    # MACD
    fast, slow, sg = win["macd"]  # MACD 기간
    mname = f"MACD({fast},{slow},{sg})"  # MACD 이름
    if pd.isna(last["signal"]):  # 봉이 부족하면
        need = slow + sg - 1  # 필요한 봉 수
        rows.append({"key": "macd", "name": mname, "value": "계산 불가", "reading": f"봉이 {need}개 필요합니다(현재 {n}개).", "tone": "neutral"})  # 안내
    else:  # 계산 가능하면
        mv, sv, hv = float(last["macd"]), float(last["signal"]), float(last["hist"])  # 값들
        prev_h = s["hist"].iloc[-2] if n >= 2 else np.nan  # 직전 히스토그램
        if pd.isna(prev_h):  # 비교 불가
            trend = ""  # 문장 없음
        elif abs(hv) > abs(prev_h):  # 절대값이 커짐
            trend = "히스토그램 확대(힘이 붙는 중)"  # 확대 문장
        else:  # 줄어듦
            trend = "히스토그램 축소(힘이 약해지는 중)"  # 축소 문장
        cross = last_cross(s["macd"], s["signal"])  # MACD선과 시그널선의 교차
        cross_text = "MACD–시그널: " + fmt_cross(cross, s["date"], n, "상향 교차", "하향 교차", unit)  # 교차 문장
        zero = "0선 위" if mv > 0 else "0선 아래"  # 0선 위치
        rel = "시그널선 위" if mv > sv else "시그널선 아래"  # 시그널 대비 위치
        tone = "up" if mv > sv else "dn"  # 톤 결정
        rows.append({"key": "macd", "name": mname, "value": f"{mv:+,.{md}f} / 시그널 {sv:+,.{md}f} / 히스토그램 {hv:+,.{md}f}", "reading": f"MACD선은 {rel}, {zero}. " + (trend + ". " if trend else "") + cross_text + ".", "tone": tone})  # 행 추가
    return rows  # 목록 반환
