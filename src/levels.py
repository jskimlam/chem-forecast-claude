"""지지·저항 레벨과 패턴 자동 탐지 모듈(종가 전용: 스윙 고저점, 피보나치, 볼린저, 심리선, 바닥 밴드, 고점 추세, 삼각형)."""  # 모듈 설명
# 필요 라이브러리 설치: pip install pandas numpy
import math  # 로그·올림 계산용

import numpy as np  # 수치 계산용
import pandas as pd  # 표 데이터 처리용

from . import config as cfg  # 설정 상수 불러오기
from .indicators import linear_fit  # 회귀직선 계산 함수


def count_runs(mask: np.ndarray) -> int:  # 연속 구간 개수 세기 함수
    """True가 이어진 구간을 1번으로 세어 개수를 돌려줍니다. 가격이 며칠씩 그대로인 평가가격이 '여러 번 터치'로 부풀려지는 것을 막습니다."""  # 함수 설명
    runs = 0  # 연속 구간 수
    prev = False  # 직전 봉의 상태
    for flag in mask:  # 봉을 하나씩
        if flag and not prev:  # 새로 True가 시작되면
            runs += 1  # 구간 수 증가
        prev = bool(flag)  # 상태 갱신
    return runs  # 구간 수 반환


def swing_indices(values: np.ndarray, k: int = 2, mode: str = "high") -> list:  # 스윙 고저점 위치 찾기 함수
    """앞뒤 k봉보다 확실히 높은(mode=high) 또는 낮은(mode=low) 봉의 위치 목록을 돌려줍니다."""  # 함수 설명
    result = []  # 결과 목록
    for i in range(k, len(values) - k):  # 앞뒤 k봉이 모두 있는 위치만 검사
        window = values[i - k : i + k + 1]  # 앞뒤 k봉을 포함한 구간
        target = window.max() if mode == "high" else window.min()  # 구간의 최고 또는 최저값
        if values[i] == target and int((window == target).sum()) == 1:  # 자신이 유일한 극값이면
            result.append(i)  # 스윙 위치로 기록
    return result  # 위치 목록 반환


def cluster_values(values: list, tol: float) -> list:  # 가까운 가격을 묶는 함수
    """오름차순 가격들을 시작값 대비 tol 비율 안에서 묶어 (평균, 개수) 목록으로 돌려줍니다."""  # 함수 설명
    if not values:  # 값이 없으면
        return []  # 빈 목록 반환
    ordered = sorted(values)  # 오름차순 정렬
    groups = [[ordered[0]]]  # 첫 묶음 시작
    for v in ordered[1:]:  # 나머지 값을 하나씩
        if v <= groups[-1][0] * (1 + tol):  # 현재 묶음의 시작값 가까이면
            groups[-1].append(v)  # 같은 묶음에 추가
        else:  # 멀면
            groups.append([v])  # 새 묶음 시작
    return [(float(np.mean(g)), len(g)) for g in groups]  # 평균과 개수로 변환


def nice_step(raw: float) -> float:  # 1·2·5 계열 간격 고르기 함수
    """raw에 가장 가까운 1·2·5×10^k 값을 돌려줍니다(로그 거리 기준)."""  # 함수 설명
    power = 10 ** math.floor(math.log10(raw))  # 10의 거듭제곱
    best = min((1, 2, 5, 10), key=lambda f: abs(math.log(raw / (f * power))))  # 로그 거리가 가장 가까운 계수
    return float(best * power)  # 간격 반환


def fmt_price(value: float, digits: int) -> str:  # 가격 문자열 함수
    """소수 자릿수에 맞춰 가격을 문자열로 만듭니다."""  # 함수 설명
    return f"{value:,.{digits}f}"  # 고정 소수점 표기


def level_digits(price: float) -> int:  # 레벨 표시 자릿수 함수
    """레벨 가격 표시용 자릿수(기본 자릿수보다 한 자리 적게, 최소 0)를 돌려줍니다."""  # 함수 설명
    return max(0, cfg.digits_for(price) - 1)  # 한 자리 줄임


def floor_band(df: pd.DataFrame) -> dict:  # 바닥 밴드 탐지 함수
    """최근 구간에서 종가가 가장 촘촘히 반복해서 내려앉은 자리를 바닥 밴드로 돌려줍니다. 터치가 부족하면 None입니다.

    '밴드 두께(FLOOR_TOL) 안에 종가가 가장 많은 구간(연속은 1번)으로 들어가는 자리'를 찾고, 동률이면 더 낮은 자리를 고릅니다.
    현재 종가 이상인 군집은 바닥으로 보지 않습니다. 종가만 있으므로 장중 저점이 아니라 종가 기준 바닥입니다.
    """  # 함수 설명
    window = df.tail(cfg.FLOOR_WINDOW).reset_index(drop=True)  # 최근 구간
    closes = window["close"].astype(float).to_numpy()  # 종가 배열
    last_close = float(closes[-1])  # 마지막 종가
    best_lo = None  # 가장 좋은 밴드의 하단
    best_count = 0  # 그 밴드에 들어간 터치(연속 구간) 수
    for candidate in sorted(set(closes.tolist())):  # 낮은 값부터 밴드 하단 후보로 시험
        if candidate >= last_close or candidate <= 0:  # 종가 이상이거나 0 이하이면 바닥이 아님
            continue  # 건너뜀
        mask = (closes >= candidate) & (closes <= candidate * (1 + cfg.FLOOR_TOL))  # 밴드 안 봉
        count = count_runs(mask)  # 연속 구간 수
        if count > best_count:  # 더 많이 모인 자리면(동률이면 먼저 나온 낮은 자리 유지)
            best_lo, best_count = candidate, count  # 갱신
    if best_lo is None or best_count < cfg.FLOOR_MIN_TOUCHES:  # 터치 횟수가 부족하면
        return None  # 바닥 밴드 없음
    band_hi = best_lo * (1 + cfg.FLOOR_TOL)  # 밴드 상단
    mask = (closes >= best_lo) & (closes <= band_hi)  # 밴드 안 봉
    dates = []  # 터치한 날짜(각 구간의 첫 봉)
    prev = False  # 직전 봉 상태
    for i, flag in enumerate(mask):  # 봉을 하나씩
        if flag and not prev:  # 새 구간이 시작되면
            dates.append(pd.Timestamp(window["date"].iloc[i]).strftime("%m/%d").lstrip("0").replace("/0", "/"))  # M/D 형식 날짜 추가
        prev = bool(flag)  # 상태 갱신
    return {"lo": best_lo, "hi": band_hi, "touches": int(best_count), "dates": dates, "window": int(len(window))}  # 결과 반환


def high_trend(df: pd.DataFrame, win: dict) -> dict:  # 고점 추세 탐지 함수
    """최근 종가들의 회귀직선으로 고점이 내려오는지·올라가는지 판단합니다(종가만 있어 종가를 고점 대용으로 씀)."""  # 함수 설명
    window = df.tail(cfg.HIGH_TREND_WINDOW)  # 최근 구간
    highs = window["close"].to_numpy(dtype=float)  # 종가 배열
    slope, intercept = linear_fit(highs)  # 회귀 기울기와 절편
    slope_pct = slope / float(highs[-1]) if highs[-1] != 0 else 0.0  # 한 봉 기울기를 비율로 환산
    if slope_pct <= win["high_fall"]:  # 기준 이하로 내려가면
        direction = "falling"  # 고점 하락
    elif slope_pct >= -win["high_fall"]:  # 기준 이상으로 올라가면
        direction = "rising"  # 고점 상승
    else:  # 그 사이면
        direction = "flat"  # 뚜렷하지 않음
    return {  # 결과 반환
        "direction": direction,  # 방향
        "slope": slope,  # 한 봉 기울기(가격 단위)
        "slope_pct": slope_pct,  # 한 봉 기울기(비율)
        "v0": intercept,  # 구간 시작 지점의 회귀값
        "v1": intercept + slope * (len(highs) - 1),  # 구간 끝 지점의 회귀값
        "start_date": pd.Timestamp(window["date"].iloc[0]).strftime("%Y-%m-%d"),  # 구간 시작 날짜
        "end_date": pd.Timestamp(window["date"].iloc[-1]).strftime("%Y-%m-%d"),  # 구간 끝 날짜
        "window": int(len(window)),  # 구간 길이
        "max_high": float(highs.max()),  # 구간 최고 종가
    }


def triangle(df: pd.DataFrame, band: dict, trend: dict) -> dict:  # 하락 삼각형 판단 함수
    """고점은 내려오고 바닥은 반복해서 지지받으면 하락 삼각형으로 보고 교과서적 목표가를 계산합니다."""  # 함수 설명
    if band is None or trend["direction"] != "falling":  # 바닥 밴드가 없거나 고점이 안 내려오면
        return None  # 삼각형 아님
    recent = df.tail(cfg.HIGH_TREND_WINDOW)["close"].to_numpy(dtype=float)  # 고점 추세 구간 종가
    touches = count_runs(recent <= band["hi"])  # 이 구간에서 바닥을 건드린 횟수(연속은 1번)
    if touches < 2:  # 구간 안에서 두 번 미만이면
        return None  # 삼각형 아님
    height = trend["max_high"] - band["lo"]  # 삼각형 높이
    return {"height": height, "target": band["lo"] - height, "touches_in_window": int(touches)}  # 목표가 = 바닥 - 높이


def ma_alignment(df: pd.DataFrame, periods: tuple) -> dict:  # 이동평균 배열 판단 함수
    """단기·중기·장기(앞의 세 이동평균)의 배열(정배열/역배열/혼조)을 판단합니다."""  # 함수 설명
    close = df["close"]  # 종가
    p1, p2, p3 = periods[0], periods[1], periods[2]  # 세 기간
    s1 = float(close.tail(p1).mean())  # 단기선
    s2 = float(close.tail(p2).mean())  # 중기선
    s3 = float(close.tail(p3).mean())  # 장기선
    if s1 > s2 > s3:  # 짧은 선이 위에 있으면
        state = "bull"  # 정배열
    elif s1 < s2 < s3:  # 짧은 선이 아래에 있으면
        state = "bear"  # 역배열
    else:  # 섞여 있으면
        state = "mixed"  # 혼조
    return {"state": state, "periods": [p1, p2, p3], "sma1": s1, "sma2": s2, "sma3": s3, "close": float(close.iloc[-1])}  # 결과 반환


def detect_patterns(df: pd.DataFrame, win: dict) -> dict:  # 패턴 전체 탐지 함수
    """바닥 밴드, 고점 추세, 삼각형, 이동평균 배열을 한 번에 계산합니다."""  # 함수 설명
    band = floor_band(df)  # 바닥 밴드
    trend = high_trend(df, win)  # 고점 추세
    return {  # 결과 묶음
        "floor_band": band,  # 바닥 밴드(없으면 None)
        "high_trend": trend,  # 고점 추세
        "triangle": triangle(df, band, trend),  # 하락 삼각형(없으면 None)
        "ma_alignment": ma_alignment(df, win["ma"]),  # 이동평균 배열
    }


def find_levels(df: pd.DataFrame, bb_last: dict) -> list:  # 지지·저항 레벨 탐지 함수
    """스윙 군집, 피보나치, 볼린저, 중심선, 심리선 후보를 모아 현재가 위·아래 가까운 순으로 돌려줍니다(종가 기준)."""  # 함수 설명
    window = df.tail(cfg.LEVEL_LOOKBACK).reset_index(drop=True)  # 탐지 구간
    closes = window["close"].to_numpy(dtype=float)  # 종가 배열
    last_close = float(closes[-1])  # 현재가
    dg = level_digits(last_close)  # 설명 문구에 쓸 자릿수
    candidates = []  # 후보 목록(값, 이름, 설명, 우선순위)

    swing_values = [closes[i] for i in swing_indices(closes, 2, "high")]  # 스윙 고점 가격들
    swing_values += [closes[i] for i in swing_indices(closes, 2, "low")]  # 스윙 저점 가격 추가
    for mean_value, count in cluster_values(swing_values, cfg.LEVEL_CLUSTER_TOL):  # 가까운 스윙끼리 묶기
        if count >= 2:  # 두 번 이상 모인 자리만
            candidates.append((mean_value, f"스윙 {count}회", f"최근 {len(window)}봉에서 스윙 고저점 {count}개가 모인 자리", 3 + 0.1 * count))  # 후보 추가

    fib_win = df.tail(cfg.FIB_WINDOW).reset_index(drop=True)  # 피보나치 구간
    fib_close = fib_win["close"].to_numpy(dtype=float)  # 구간 종가
    hi_idx = int(np.argmax(fib_close))  # 구간 최고 종가 위치
    lo_idx = int(np.argmin(fib_close))  # 구간 최저 종가 위치
    hi_val = float(fib_close.max())  # 구간 최고 종가
    lo_val = float(fib_close.min())  # 구간 최저 종가
    if hi_val - lo_val > 0 and hi_idx != lo_idx:  # 폭이 있고 위치가 다르면
        for ratio in (0.382, 0.5, 0.618):  # 대표 되돌림 비율
            if hi_idx > lo_idx:  # 저점 뒤에 고점이 왔으면(상승분)
                value = hi_val - ratio * (hi_val - lo_val)  # 고점에서 되돌림
                basis = f"최근 {len(fib_win)}봉 상승분 {fmt_price(lo_val, dg)}→{fmt_price(hi_val, dg)}의 {ratio:.1%} 되돌림"  # 설명
            else:  # 고점 뒤에 저점이 왔으면(하락분)
                value = lo_val + ratio * (hi_val - lo_val)  # 저점에서 되돌림
                basis = f"최근 {len(fib_win)}봉 하락분 {fmt_price(hi_val, dg)}→{fmt_price(lo_val, dg)}의 {ratio:.1%} 되돌림"  # 설명
            candidates.append((value, f"피보 {ratio * 100:.1f}%".replace(".0%", "%"), basis, 2))  # 후보 추가

    nb = int(bb_last.get("n", 20))  # 볼린저 기간(설명용)
    candidates.append((bb_last["up"], "볼린저 상단", f"{nb}봉 볼린저밴드 상단(2σ)", 2))  # 볼린저 상단 후보
    candidates.append((bb_last["lo"], "볼린저 하단", f"{nb}봉 볼린저밴드 하단(2σ)", 2))  # 볼린저 하단 후보
    candidates.append((bb_last["mid"], f"{nb}봉선", f"{nb}봉 이동평균(볼린저 중심선)", 1.5))  # 중심선 후보

    if last_close > 0:  # 양수 가격일 때만 심리선 생성
        step = nice_step(last_close * cfg.PSY_STEP_PCT)  # 심리선 간격(현재가의 약 5%를 1·2·5 계열로)
        first = math.ceil(last_close * 0.9 / step) * step  # 현재가 -10% 이상의 첫 간격 배수
        value = float(first)  # 순회 시작값
        while value <= last_close * 1.1:  # 현재가 +10% 이하까지
            candidates.append((value, f"심리선 {value:,g}", f"{value:,g} 라운드 넘버", 1))  # 후보 추가
            value += step  # 다음 배수로

    candidates.sort(key=lambda c: (-c[3], abs(c[0] - last_close)))  # 우선순위 높은 것부터, 같으면 현재가에 가까운 것부터
    kept = []  # 채택된 레벨
    for value, label, basis, priority in candidates:  # 후보를 하나씩 검토
        if value <= 0:  # 비정상 값은 건너뜀
            continue  # 다음 후보로
        if any(abs(value - k["v"]) / k["v"] <= cfg.LEVEL_MERGE_TOL for k in kept):  # 이미 가까운 레벨이 있으면
            continue  # 중복이므로 건너뜀
        kept.append({"v": round(float(value), 2), "label": label, "basis": basis, "priority": priority})  # 레벨 채택

    above = sorted([k for k in kept if k["v"] > last_close], key=lambda k: k["v"])[: cfg.LEVELS_PER_SIDE]  # 위쪽 가까운 순
    below = sorted([k for k in kept if k["v"] <= last_close], key=lambda k: -k["v"])[: cfg.LEVELS_PER_SIDE]  # 아래쪽 가까운 순
    levels = [dict(k, kind="R") for k in above] + [dict(k, kind="S") for k in below]  # 저항/지지 표시 추가
    levels.sort(key=lambda k: -k["v"])  # 높은 가격부터 정렬
    return levels  # 레벨 목록 반환
