"""페이지 데이터 생성 모듈: 품목별 지표·예측·레벨·해설을 계산해 탭 대시보드에 심을 데이터로 묶습니다."""  # 모듈 설명
# 필요 라이브러리 설치: pip install pandas numpy
from datetime import datetime, timedelta, timezone  # 생성 시각(한국 시간) 표기용

import numpy as np  # 영업일 계산용
import pandas as pd  # 표 데이터 처리용

from . import config as cfg  # 설정 상수 불러오기
from .analysis import build_findings, build_verdict, pick_level  # 해설 문장 생성
from .forecast import compute_forecast, next_dates  # 확률 예측
from .indicators import bollinger, robust_vol  # 볼린저·변동성 계산
from .levels import detect_patterns, find_levels  # 패턴·레벨 탐지
from .signals import build_signals, compute_series  # 장기선·RSI·MACD 계산과 상태 요약


def kst_now_text() -> str:  # 한국 시간 문자열 함수
    """현재 시각을 'YYYY-MM-DD HH:MM KST' 형태로 돌려줍니다."""  # 함수 설명
    kst = timezone(timedelta(hours=9))  # 한국 시간대
    return datetime.now(kst).strftime("%Y-%m-%d %H:%M ") + cfg.KST_NAME  # 문자열 반환


def min_bars_needed(win: dict) -> int:  # 필요 최소 봉 수 함수
    """지표와 예측이 모두 계산되려면 필요한 최소 봉 수를 돌려줍니다."""  # 함수 설명
    return max(win["ma"][3] + win["ma_slope_bars"] + 1, win["macd"][1] + win["macd"][2], win["bb"] + 1, win["vol"] + 2, cfg.HIGH_TREND_WINDOW + 1)  # 가장 큰 요구치


def choose_thresholds(close: pd.Series, patterns: dict, levels: list, bb_last: dict) -> dict:  # 기준 가격 레벨 선택 함수
    """'이 아래/위에서 마감할 확률'을 구할 가격을 정합니다. 아래=바닥 밴드 하단(없으면 가까운 지지), 위=가까운 저항."""  # 함수 설명
    last = float(close.iloc[-1])  # 마지막 종가
    band = patterns["floor_band"]  # 바닥 밴드
    if band is not None:  # 바닥 밴드가 있으면
        below = band["lo"]  # 밴드 하단
    else:  # 없으면
        sup = pick_level(levels, last, "S")  # 가까운 지지
        below = sup["v"] if sup else float(close.tail(20).min())  # 지지 레벨 또는 최근 20봉 최저 종가
    res = pick_level(levels, last, "R")  # 가까운 저항
    above = res["v"] if res else bb_last["up"]  # 저항 레벨 또는 볼린저 상단
    if below >= last:  # 아래 기준이 종가 이상이면(이미 밴드 아래 마감)
        below = last * 0.98  # 종가의 2% 아래로 대체
    if above <= last:  # 위 기준이 종가 이하이면
        above = last * 1.02  # 종가의 2% 위로 대체
    return {"below": round(float(below), 2), "above": round(float(above), 2)}  # 반올림해서 반환


def round_rows(rows: list) -> list:  # 예측 줄 반올림 함수
    """페이지 용량을 줄이기 위해 숫자를 소수 6자리로 반올림합니다."""  # 함수 설명
    return [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in row.items()} for row in rows]  # 줄마다 반올림


def position_stats(close: pd.Series, win: dict) -> dict:  # 가격 위치 통계 함수
    """마지막 종가가 최근 1년·전체 기간에서 어느 위치인지(백분위, Z-score)를 계산합니다."""  # 함수 설명
    last = float(close.iloc[-1])  # 마지막 종가
    year = close.tail(win["year_bars"])  # 최근 1년 구간
    sd = float(year.std(ddof=0))  # 1년 표준편차
    return {  # 결과 묶음
        "p1y": round(float((year <= last).mean() * 100), 1),  # 최근 1년 백분위(낮을수록 싼 구간)
        "pall": round(float((close <= last).mean() * 100), 1),  # 전체 기간 백분위
        "z1y": round((last - float(year.mean())) / sd, 2) if sd > 0 else 0.0,  # 1년 Z-score
        "n1y": int(len(year)),  # 1년 구간 봉 수
        "nall": int(len(close)),  # 전체 봉 수
    }


def quality_notes(close: pd.Series, item: dict, win: dict, sd_note) -> tuple:  # 데이터 품질 점검 함수
    """(경고 목록, 참고 목록)을 돌려줍니다. 경고는 화면 상단 배너, 참고는 하단 안내에 표시됩니다."""  # 함수 설명
    warnings, notes = [], []  # 결과 목록
    unit = win["unit"]  # 봉 단위
    chg = close.pct_change().replace([np.inf, -np.inf], np.nan)  # 봉별 변화율
    recent = chg.tail(cfg.STALE_LOOKBACK).dropna()  # 최근 변화율
    if len(recent) >= 20:  # 충분히 있으면
        stale = float((recent == 0).mean())  # 전봉과 같은 가격 비율
        if stale >= win["stale_warn"]:  # 기준 이상이면
            tail = "사실상 주 단위로 갱신되는 평가가격일 수 있어 " if item["freq"] == "D" else ""  # 보조 설명
            warnings.append(f"최근 {len(recent)}봉 중 {stale * 100:.0f}%가 전봉과 같은 가격입니다. {tail}{unit}간 방향·변동성 확률이 실제 움직임보다 단순하게 나올 수 있습니다.")  # 경고
    big = chg.tail(120)  # 최근 120봉 변화율
    big = big[big.abs() > cfg.BIG_MOVE]  # 급변동 봉
    if len(big):  # 있으면
        days = ", ".join(f"{d:%m/%d}({v * 100:+.0f}%)" for d, v in list(big.items())[-3:])  # 최근 3건 나열
        warnings.append(f"최근 120봉 안에 ±{cfg.BIG_MOVE * 100:.0f}%를 넘는 변동이 있습니다: {days}. 변동성(σ)이 커져 예측 폭이 넓게 나올 수 있습니다.")  # 경고
    if sd_note:  # 변동성 대체 안내가 있으면
        warnings.append(sd_note)  # 경고에 추가
    bad = close[close <= 0]  # 0 이하 가격
    if len(bad):  # 있으면
        txt = ", ".join(f"{d:%Y-%m-%d} {v:g}" for d, v in list(bad.items())[:3])  # 앞의 3건 나열
        notes.append(f"0 이하 가격이 있습니다({txt}). 로그수익률(변동성) 계산에서는 이 구간을 제외했고, 이동평균·RSI·백분위에는 실제 값이 그대로 들어갑니다.")  # 참고
    return warnings, notes  # 결과 반환


def build_bars(close: pd.Series, dates: pd.Series, series: pd.DataFrame) -> list:  # 페이지용 봉 목록 생성 함수
    """최근 JSON_BARS개 봉을 페이지에 심을 형태로 바꿉니다(지표는 전체 이력으로 계산한 값)."""  # 함수 설명
    prev = close.shift()  # 직전 봉 가격
    chg = (close / prev - 1).where(prev > 0)  # 전봉 대비 변화율(직전 가격이 양수일 때만)

    def num(value, digits):  # 값이 없으면 None, 있으면 반올림해 돌려주는 도우미
        return None if pd.isna(value) else round(float(value), digits)  # 결측 처리

    bars = []  # 결과 목록
    for i in range(max(0, len(close) - cfg.JSON_BARS), len(close)):  # 최근 봉만
        bars.append(  # 봉 추가
            {
                "date": pd.Timestamp(dates.iloc[i]).strftime("%Y-%m-%d"),  # 날짜
                "c": float(close.iloc[i]),  # 종가
                "chg": None if pd.isna(chg.iloc[i]) else float(chg.iloc[i]),  # 전봉 대비 변화율
                "rsi": num(series["rsi"].iloc[i], 2),  # RSI
                "macd": num(series["macd"].iloc[i], 4),  # MACD선
                "sig": num(series["signal"].iloc[i], 4),  # 시그널선
                "hist": num(series["hist"].iloc[i], 4),  # 히스토그램
            }
        )
    return bars  # 봉 목록 반환


def weekly_bars(s: pd.Series) -> pd.Series:  # 주간 봉 변환 함수
    """일간으로 쌓인 가격을 주간 봉으로 줄입니다. 월~일 한 주 안의 마지막 값을 쓰고, 날짜는 그 값의 실제 날짜로 둡니다.
    이미 주 1회만 있는 품목은 그대로이고, 가격이 매일 채워진 품목(주 단위로만 바뀌는 평가가격)은 한 주에 한 봉이 됩니다."""  # 함수 설명
    s = s.dropna()  # 빈 값 제거
    if s.empty:  # 비었으면
        return s  # 그대로 반환
    keep = s.groupby(s.index.to_period("W")).tail(1)  # 주마다 마지막 값 한 개
    return keep.sort_index()  # 날짜순으로 반환


def stale_info(last_date: pd.Timestamp, latest: pd.Timestamp, freq: str) -> tuple:  # 미갱신 판정 함수
    """기준일(전체 데이터의 최신 입력일) 대비 이 품목이 얼마나 늦는지 (미갱신 여부, 지연 일수)를 돌려줍니다."""  # 함수 설명
    if freq == "W":  # 주간이면
        days = int((latest - last_date).days)  # 달력일 차이
        return days >= cfg.STALE_DAYS_WEEKLY, days  # 기준 이상이면 미갱신
    days = int(np.busday_count(last_date.date(), latest.date()))  # 영업일 차이
    return days >= cfg.STALE_DAYS_DAILY, days  # 기준 이상이면 미갱신


def base_meta(item: dict, win: dict) -> dict:  # 기본 메타 생성 함수
    """품목의 고정 정보(이름·단위·주기)를 묶습니다."""  # 함수 설명
    return {  # 메타 묶음
        "code": item["code"], "key": item["key"], "label": item["label"], "name": item["name"],  # 식별 정보
        "group": item["group"], "freq": item["freq"], "unit_label": cfg.unit_label(item),  # 분류·단위
        "unit": win["unit"],  # 봉 단위(일/주)
    }


def build_item(item: dict, frame: pd.DataFrame, latest: pd.Timestamp, wt: float, wm: float, generated_at: str) -> dict:  # 품목 데이터 생성 함수
    """한 품목의 페이지 데이터를 만듭니다. 봉이 부족하면 안내 문구만 담은 데이터를 돌려줍니다."""  # 함수 설명
    win = cfg.WINDOWS[item["freq"]]  # 주기별 프리셋
    meta = base_meta(item, win)  # 기본 메타
    s = frame[item["code"]].dropna()  # 유효 가격
    if item["freq"] == "W":  # 주간 품목이면
        s = weekly_bars(s)  # 주 1봉으로 정리(일간으로 채워진 데이터도 안전하게 처리)
    need = min_bars_needed(win)  # 필요한 봉 수
    win_out = {k: (list(v) if isinstance(v, tuple) else v) for k, v in win.items()}  # JSON 변환 가능한 프리셋
    if len(s) < need:  # 봉이 부족하면
        meta.update({"digits": 2, "last_bar_date": None if s.empty else s.index[-1].strftime("%Y-%m-%d"), "warnings": [], "notes": []})  # 메타 보완
        return {"meta": meta, "win": win_out, "error": f"가격 데이터가 부족합니다({len(s)}개). 최소 {need}개가 필요합니다. 엑셀에서 이 품목 열을 확인하세요."}  # 안내 데이터
    prices = pd.DataFrame({"date": s.index, "close": s.to_numpy(dtype=float)}).reset_index(drop=True)  # 날짜·종가 표
    close = prices["close"]  # 종가 열
    last_date = pd.Timestamp(prices["date"].iloc[-1])  # 마지막 봉 날짜
    last = float(close.iloc[-1])  # 마지막 종가
    digits = cfg.digits_for(abs(last))  # 표시 자릿수
    sd, sd_note = robust_vol(close, win["vol"])  # 봉당 변동성(방어 포함)
    bb = bollinger(close, win["bb"], cfg.BB_K).iloc[-1]  # 마지막 볼린저 값
    bb_last = {"mid": float(bb["mid"]), "up": float(bb["up"]), "lo": float(bb["lo"]), "n": win["bb"]}  # 사전으로 정리
    patterns = detect_patterns(prices, win)  # 패턴 탐지
    levels = find_levels(prices, bb_last)  # 레벨 탐지
    thresholds = choose_thresholds(close, patterns, levels, bb_last)  # 기준 레벨 선택
    result = compute_forecast([float(v) for v in close], wt, wm, win["forecast_bars"], thresholds["below"], thresholds["above"], win, sd)  # 예측 계산
    dates = next_dates(last_date, win["forecast_bars"], item["freq"])  # 예측 날짜
    series = compute_series(prices, win)  # 지표 시계열
    dated_close = pd.Series(close.to_numpy(dtype=float), index=pd.DatetimeIndex(prices["date"]))  # 날짜 인덱스를 가진 종가(경고 문구에 날짜를 쓰기 위함)
    warnings, notes = quality_notes(dated_close, item, win, sd_note)  # 데이터 품질 점검
    is_stale, behind = stale_info(last_date, latest, item["freq"])  # 미갱신 판정
    if is_stale:  # 미갱신이면
        warnings.insert(0, f"마지막 입력일({last_date:%Y-%m-%d})이 기준일({latest:%Y-%m-%d})보다 늦습니다({behind}{'일' if item['freq'] == 'W' else '영업일'}). 예측은 마지막 입력 기준입니다.")  # 맨 앞에 경고
    meta.update({  # 메타 보완
        "digits": digits, "last_bar_date": last_date.strftime("%Y-%m-%d"), "first_bar_date": pd.Timestamp(prices["date"].iloc[0]).strftime("%Y-%m-%d"),  # 날짜 정보
        "generated_at": generated_at, "stale": bool(is_stale), "stale_days": behind, "warnings": warnings, "notes": notes,  # 생성·경고
        "n_bars_total": int(len(prices)), "source": "Platts 평가가격(수동 입력)",  # 봉 수·출처
    })
    labels = {  # 화면 문구(주기별)
        "unit": win["unit"],  # 봉 단위
        "first": "다음 거래일" if item["freq"] == "D" else "다음 주",  # 첫 예측 이름
        "last": f"1주 뒤 · {win['forecast_bars']}거래일" if item["freq"] == "D" else f"{win['forecast_bars']}주 뒤",  # 마지막 예측 이름
        "per": "하루 방향" if item["freq"] == "D" else "주간 방향",  # 봉 방향 이름
        "n_chg": win["ma_slope_bars"],  # 누적 변화를 보는 봉 수
    }
    return {  # 품목 데이터 묶음
        "meta": meta,  # 메타
        "win": win_out,  # 주기별 프리셋
        "labels": labels,  # 화면 문구
        "bars": build_bars(close, prices["date"], series),  # 봉 목록
        "view_bars": cfg.VIEW_BARS,  # 차트에 보여줄 봉 수
        "indicators": {"pb": result["pb"], "bw": result["bw"], "sd": result["sd"], "slope": result["slope"], "bb": result["bb"]},  # 지표 요약
        "forecast": {  # 예측
            "asof": last_date.strftime("%Y-%m-%d"), "p0": round(result["p0"], 4), "dates": dates, "thresholds": thresholds,  # 기준 정보
            "params": {  # 모델 설정
                "wt": wt, "wm": wm, "sd": round(result["sd"], 8), "slope": round(result["slope"], 6),  # 반영도·변동성·기울기
                "trend_decay": cfg.TREND_DECAY, "kappa_scale": cfg.KAPPA_SCALE,  # 감쇠·회귀 속도
                "flat_band_first": win["flat_first"], "flat_band_last": win["flat_last"], "edge_min_gap": cfg.EDGE_MIN_GAP,  # 보합 폭·우위 기준
            },
            "rows": round_rows(result["rows"]),  # 봉별 결과
        },
        "levels": levels,  # 지지·저항 레벨
        "patterns": patterns,  # 패턴
        "signals": build_signals(prices, win, digits),  # 장기선·RSI·MACD 현재 상태(표시 전용)
        "findings": build_findings(prices, patterns, bb_last, result["pb"], result["bw"], win),  # 해설
        "verdict": build_verdict(last, patterns, levels, win),  # 한 줄 결론
        "position": position_stats(close, win),  # 가격 위치 통계
    }


def overview_row(item: dict, payload: dict) -> dict:  # 전체 요약 한 줄 생성 함수
    """전체 요약 탭에 보여줄 한 줄(최근 가격·등락·RSI·%b·방향 확률)을 만듭니다."""  # 함수 설명
    meta = payload["meta"]  # 메타
    row = {"code": item["code"], "key": item["key"], "label": item["label"], "group": item["group"], "freq": item["freq"], "unit_label": meta["unit_label"], "last_date": meta.get("last_bar_date")}  # 기본 정보
    if "error" in payload:  # 데이터 부족이면
        row.update({"error": payload["error"], "digits": 2})  # 오류 표시
        return row  # 반환
    bars = payload["bars"]  # 봉 목록
    last, n = bars[-1], payload["labels"]["n_chg"]  # 마지막 봉과 누적 변화 봉 수
    base = bars[-1 - n]["c"] if len(bars) > n else None  # n봉 전 종가
    ind = payload["indicators"]  # 지표 요약
    sig = {s["key"]: s for s in payload["signals"]}  # 신호 사전
    long_gap = None  # 장기선 대비 간격
    ma_long = sum(b["c"] for b in bars[-payload["win"]["ma"][3]:]) / payload["win"]["ma"][3] if len(bars) >= payload["win"]["ma"][3] else None  # 장기선 값
    if ma_long:  # 값이 있으면
        long_gap = (last["c"] / ma_long - 1) * 100  # 간격(%)
    first = payload["forecast"]["rows"][0]  # 첫 예측 봉
    diff = first["p3_up"] - first["p3_dn"]  # 상승·하락 확률 차이
    edge = "none" if abs(diff) < cfg.EDGE_MIN_GAP else ("up" if diff > 0 else "dn")  # 우위 판정
    row.update({  # 수치 추가
        "digits": meta["digits"], "last": last["c"], "chg1": None if last["chg"] is None else last["chg"] * 100,  # 종가·전봉 대비
        "chgN": None if not base or base <= 0 else (last["c"] / base - 1) * 100, "nN": n, "unitN": payload["labels"]["unit"],  # n봉 대비
        "rsi": last["rsi"], "pb": ind["pb"], "long_gap": long_gap,  # RSI·%b·장기선 간격
        "macd_tone": sig.get("macd", {}).get("tone"), "ma_tone": sig.get("ma_long", {}).get("tone"),  # MACD·장기선 톤
        "p3_up": first["p3_up"], "p3_dn": first["p3_dn"], "edge": edge,  # 방향 확률
        "stale": meta["stale"], "stale_days": meta["stale_days"], "n_warn": len(meta["warnings"]),  # 미갱신·경고 수
        "p1y": payload["position"]["p1y"],  # 최근 1년 백분위
    })
    return row  # 반환


def build_all(frame: pd.DataFrame, wt: float = None, wm: float = None) -> tuple:  # 전체 데이터 생성 함수
    """모든 품목의 데이터를 만들어 (페이지 데이터, 오류 목록)을 돌려줍니다. 한 품목이 실패해도 나머지는 계속 만듭니다."""  # 함수 설명
    wt = cfg.DEFAULT_WT if wt is None else wt  # 추세 반영도 기본값
    wm = cfg.DEFAULT_WM if wm is None else wm  # 평균회귀 반영도 기본값
    valid = frame.dropna(how="all")  # 값이 하나라도 있는 행
    if valid.empty:  # 데이터가 없으면
        raise ValueError("가격 데이터가 비어 있습니다.")  # 한글 오류 안내
    latest = valid.index.max()  # 전체 데이터의 최신 입력일
    generated_at = kst_now_text()  # 생성 시각
    items, overview, errors = {}, [], []  # 결과 모음
    for it in cfg.shown_items():  # 화면에 보일 품목마다
        try:  # 한 품목의 실패가 전체를 막지 않도록
            payload = build_item(it, frame, latest, wt, wm, generated_at)  # 품목 데이터 생성
        except Exception as exc:  # 예상 밖 오류
            win = cfg.WINDOWS[it["freq"]]  # 프리셋
            meta = base_meta(it, win)  # 기본 메타
            meta.update({"digits": 2, "last_bar_date": None, "warnings": [], "notes": []})  # 메타 보완
            payload = {"meta": meta, "win": {k: (list(v) if isinstance(v, tuple) else v) for k, v in win.items()}, "error": f"계산 중 문제가 생겼습니다: {exc}"}  # 안내 데이터
            errors.append(f"{it['key']}: {exc}")  # 오류 목록에 추가
        if "error" in payload and not any(e.startswith(it["key"]) for e in errors):  # 데이터 부족도 기록
            errors.append(f"{it['key']}: {payload['error']}")  # 오류 목록에 추가
        items[it["code"]] = payload  # 품목 데이터 저장
        overview.append(overview_row(it, payload))  # 요약 줄 저장
    groups = [{"id": g["id"], "label": g["label"], "items": [it["code"] for it in cfg.shown_items() if it["group"] == g["id"]]} for g in cfg.shown_groups()]  # 그룹 구성
    meta = {"generated_at": generated_at, "latest_date": latest.strftime("%Y-%m-%d"), "n_items": len(cfg.shown_items()), "wt": wt, "wm": wm, "n_rows": int(len(valid))}  # 전체 메타
    return {"meta": meta, "groups": groups, "overview": overview, "items": items}, errors  # 데이터와 오류 반환
