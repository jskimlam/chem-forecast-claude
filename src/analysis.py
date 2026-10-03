"""해설 문장 생성 모듈(요약 한 줄, 차트가 보여주는 것). 숫자는 모두 계산 결과에서 가져옵니다."""  # 모듈 설명
# 필요 라이브러리 설치: pip install pandas numpy
import pandas as pd  # 표 데이터 처리용

from . import config as cfg  # 설정 상수 불러오기
from .levels import level_digits  # 레벨 표시 자릿수 함수


def pb_position(pb: float) -> str:  # %b 위치를 말로 바꾸는 함수
    """%b 값을 '하단 부근' 같은 표현으로 바꿉니다."""  # 함수 설명
    if pb < 0:  # 0 미만이면
        return "하단 밖"  # 밴드를 아래로 벗어남
    if pb < 0.2:  # 0.2 미만이면
        return "하단 부근"  # 하단 가까이
    if pb < 0.8:  # 0.8 미만이면
        return "중간"  # 밴드 중간
    if pb <= 1:  # 1 이하이면
        return "상단 부근"  # 상단 가까이
    return "상단 밖"  # 밴드를 위로 벗어남


def pick_level(levels: list, close: float, side: str, max_gap: float = 0.05):  # 기준 레벨 선택 함수
    """위(R) 또는 아래(S)에서 가장 가까운 '의미 있는' 레벨을 고릅니다.

    우선순위 2 이상(스윙·피보나치·볼린저)이면서 현재가에서 max_gap 이내인 가장 가까운 레벨을 쓰고,
    없으면 심리선 같은 약한 레벨을 포함해 가장 가까운 레벨을 씁니다. 하나도 없으면 None입니다.
    """  # 함수 설명
    cands = [lv for lv in levels if lv.get("kind") == side]  # 해당 방향 레벨
    cands.sort(key=lambda lv: abs(lv["v"] - close))  # 현재가에 가까운 순
    strong = [lv for lv in cands if lv.get("priority", 3) >= 2 and abs(lv["v"] / close - 1) <= max_gap]  # 의미 있고 가까운 레벨
    if strong:  # 있으면
        return strong[0]  # 가장 가까운 것
    return cands[0] if cands else None  # 없으면 가장 가까운 아무 레벨


def build_verdict(close: float, patterns: dict, levels: list, win: dict) -> str:  # 요약 한 줄 생성 함수
    """현재 위치와 패턴을 보고 한 줄 결론을 만듭니다."""  # 함수 설명
    dg = level_digits(close)  # 레벨 표시 자릿수
    band = patterns["floor_band"]  # 바닥 밴드
    align = patterns["ma_alignment"]  # 이동평균 배열
    unit = win["unit"]  # 봉 단위
    res_lv = pick_level(levels, close, "R")  # 가까운 저항
    sup_lv = pick_level(levels, close, "S")  # 가까운 지지
    resistance = res_lv["v"] if res_lv else None  # 저항 가격
    support = sup_lv["v"] if sup_lv else None  # 지지 가격
    if band is not None and close <= band["hi"] * 1.01:  # 바닥 밴드 근처에 있으면
        text = f"{band['lo']:,.{dg}f}~{band['hi']:,.{dg}f} 바닥을 다시 시험하는 중입니다. 종가가 이 밴드 아래로 내려가면 하방이 열립니다."  # 기본 문장
        if resistance is not None:  # 위쪽 저항이 있으면
            text += f" 반등하려면 {resistance:,.{dg}f} 위로 올라와야 합니다."  # 반등 조건 추가
        return text  # 문장 반환
    if align["state"] == "bear":  # 역배열이면
        return f"단기 하락 배열입니다. {align['periods'][2]}{unit}선 {align['sma3']:,.{dg}f}을 되찾기 전까지 반등은 제한적입니다."  # 문장 반환
    if align["state"] == "bull":  # 정배열이면
        tail = f" 가까운 지지는 {support:,.{dg}f}입니다." if support is not None else ""  # 지지 안내
        return "단기 상승 배열입니다." + tail  # 문장 반환
    return "방향이 뚜렷하지 않은 구간입니다. 가까운 레벨의 돌파 여부를 확인하세요."  # 혼조일 때 문장


def build_findings(df: pd.DataFrame, patterns: dict, bb_last: dict, pb: float, bw: float, win: dict) -> list:  # 해설 목록 생성 함수
    """'차트가 보여주는 것' 항목(제목과 본문) 목록을 만듭니다."""  # 함수 설명
    findings = []  # 결과 목록
    close = float(df["close"].iloc[-1])  # 마지막 종가
    dg = level_digits(close)  # 레벨 표시 자릿수
    full = cfg.digits_for(close)  # 일반 표시 자릿수
    unit = win["unit"]  # 봉 단위
    band = patterns["floor_band"]  # 바닥 밴드
    if band is not None:  # 바닥 밴드가 있으면
        dates = ", ".join(band["dates"])  # 터치한 날짜들
        body = (  # 본문 구성
            f"최근 {band['window']}봉 중 {band['touches']}번({dates}) 종가가 이 밴드에 내려앉았습니다. "
            f"마지막 종가는 {close:,.{full}f}입니다. "
            "같은 자리를 여러 번 건드린 지지는 종가로 깨질 때 손절 물량이 몰리기 쉽습니다. (종가 기준이며 장중 저점은 반영되지 않았습니다.)"
        )
        if close < band["lo"]:  # 종가가 이미 밴드 아래이면
            body += " 마지막 종가는 이미 밴드 아래입니다."  # 상황 추가
        findings.append({"title": f"바닥 {band['lo']:,.{dg}f}~{band['hi']:,.{dg}f}을 {band['touches']}번 받쳤습니다", "body": body})  # 항목 추가
    else:  # 바닥 밴드가 없으면
        low_min = float(df.tail(cfg.FLOOR_WINDOW)["close"].min())  # 최근 구간 최저 종가
        findings.append({"title": "뚜렷한 지지 밴드가 없습니다", "body": f"최근 {cfg.FLOOR_WINDOW}봉 최저 종가 {low_min:,.{full}f} 부근에 종가가 2번 이하로만 내려앉았습니다."})  # 항목 추가

    trend = patterns["high_trend"]  # 고점 추세
    thr = abs(win["high_fall"]) * 100  # 판정 기준(%)
    if trend["direction"] == "falling":  # 고점 하락이면
        body = f"최근 {trend['window']}봉 종가의 회귀선이 {trend['v0']:,.{full}f}에서 {trend['v1']:,.{full}f}로 내려옵니다(한 봉에 {trend['slope_pct'] * 100:.2f}%)."  # 본문
        if patterns["triangle"] is not None:  # 삼각형이면
            body += " 바닥은 반복해서 지지받고 있어 하락 삼각형에 가깝습니다."  # 설명 추가
        findings.append({"title": "반등할 때마다 고점이 낮아졌습니다", "body": body})  # 항목 추가
    elif trend["direction"] == "rising":  # 고점 상승이면
        findings.append({"title": "고점이 높아지고 있습니다", "body": f"최근 {trend['window']}봉 종가의 회귀선이 {trend['v0']:,.{full}f}에서 {trend['v1']:,.{full}f}로 올라갑니다(한 봉에 +{trend['slope_pct'] * 100:.2f}%)."})  # 항목 추가
    else:  # 뚜렷하지 않으면
        findings.append({"title": "고점 흐름이 뚜렷하지 않습니다", "body": f"최근 {trend['window']}봉 종가의 기울기가 한 봉에 ±{thr:.1f}% 안에 있습니다."})  # 항목 추가

    align = patterns["ma_alignment"]  # 이동평균 배열
    p1, p2, p3 = align["periods"]  # 세 기간
    title = {"bear": "이동평균은 역배열입니다", "bull": "이동평균은 정배열입니다", "mixed": "이동평균 배열이 섞여 있습니다"}[align["state"]]  # 제목 선택
    body = f"종가 {align['close']:,.{full}f}, {p1}{unit}선 {align['sma1']:,.{full}f}, {p2}{unit}선 {align['sma2']:,.{full}f}, {p3}{unit}선 {align['sma3']:,.{full}f}."  # 기본 수치 문장
    longs = []  # 장기선 문장 목록
    for n in win["longs"]:  # 장기 이동평균 기간
        if len(df) >= n:  # 봉이 충분하면
            value = float(df["close"].tail(n).mean())  # 이동평균 값
            longs.append(f"{n}{unit}선 {value:,.{full}f}({'위' if close >= value else '아래'})")  # 위치 문장 추가
    if longs:  # 장기선이 있으면
        body += " 종가는 " + ", ".join(longs) + "에 있습니다."  # 문장 추가
    else:  # 봉이 부족하면
        body += " 장기 이동평균은 봉이 부족해 계산하지 못했습니다."  # 안내 추가
    findings.append({"title": title, "body": body})  # 항목 추가

    nb = win["bb"]  # 볼린저 기간
    findings.append(  # 볼린저 항목 추가
        {
            "title": f"볼린저 %b {pb:.2f}, 밴드 {pb_position(pb)}",
            "body": f"{nb}{unit} 볼린저 하단 {bb_last['lo']:,.{full}f}, 중심 {bb_last['mid']:,.{full}f}, 상단 {bb_last['up']:,.{full}f}. 밴드폭은 {bw * 100:.1f}%입니다.",
        }
    )
    return findings  # 해설 목록 반환
