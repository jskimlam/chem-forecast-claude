"""전체 테스트: 지표, 예측 확률, 데이터 입출력, 자바스크립트 모델 일치, 기존 WTI 앱 이식 검증, CLI."""  # 모듈 설명
# 필요 라이브러리 설치: pip install pandas numpy openpyxl pytest
import importlib.util  # 다른 폴더의 패키지를 불러오기 위한 모듈
import json  # JSON 입출력용
import math  # 수학 함수 사용
import shutil  # 파일 복사용
import subprocess  # node 실행용
import sys  # 파이썬 경로 설정용
from pathlib import Path  # 경로 처리용

import numpy as np  # 수치 계산용
import pandas as pd  # 표 데이터 처리용
import pytest  # 테스트 프레임워크

ROOT = Path(__file__).resolve().parent.parent  # chem-ta 최상위 폴더
sys.path.insert(0, str(ROOT))  # 프로젝트 패키지를 불러올 수 있게 경로 추가

from src import config as cfg  # noqa: E402  설정
from src import indicators as ind  # noqa: E402  지표
from src.cli import run as cli_run  # noqa: E402  명령행 실행 함수
from src.data_io import DataError, import_xlsx, parse_assignments, read_prices, resolve_item, upsert_row, write_prices  # noqa: E402  데이터 입출력
from src.forecast import compute_forecast, level_probability, next_dates  # noqa: E402  예측
from src.payload import build_all  # noqa: E402  페이지 데이터 생성
from src.build_site import render_site  # noqa: E402  사이트 생성

WTI_REPO = Path("/home/claude/wti-forecast-claude")  # 기존 WTI 앱 폴더(있을 때만 이식 검증)


def sample_closes(n: int = 120, seed: int = 7, start: float = 100.0) -> list:  # 가상 가격 생성 함수
    """재현 가능한 가상 종가(랜덤워크)를 만듭니다."""  # 함수 설명
    rng = np.random.default_rng(seed)  # 난수 생성기
    steps = rng.normal(0.0005, 0.015, n)  # 일간 수익률
    return [float(v) for v in start * np.exp(np.cumsum(steps))]  # 가격 경로(순수 float 리스트)


def sample_frame(n: int = 150) -> pd.DataFrame:  # 가상 가격표 생성 함수
    """모든 품목 열이 있는 가상 가격표(영업일 n개)를 만듭니다."""  # 함수 설명
    idx = pd.bdate_range("2026-01-01", periods=n)  # 영업일 인덱스
    data = {it["code"]: sample_closes(n, seed=i + 1, start=50.0 + 20 * i) for i, it in enumerate(cfg.ITEMS)}  # 품목별 가상 가격
    df = pd.DataFrame(data, index=idx)  # 표 생성
    df.index.name = "date"  # 인덱스 이름
    return df  # 표 반환


# ───────────────────────── 지표 ─────────────────────────
def test_bollinger_matches_manual():  # 볼린저 수동 계산 비교
    closes = pd.Series(sample_closes(40))  # 가상 종가
    bb = ind.bollinger(closes, 20, 2.0)  # 볼린저 계산
    window = closes.tail(20).to_numpy()  # 마지막 20개
    assert bb["mid"].iloc[-1] == pytest.approx(window.mean())  # 중심선
    assert bb["up"].iloc[-1] == pytest.approx(window.mean() + 2 * window.std())  # 상단(모표준편차)


def test_bollinger_zero_width_gives_half():  # 밴드폭 0일 때 %b
    closes = pd.Series([100.0] * 30)  # 모두 같은 가격
    bb = ind.bollinger(closes, 20)  # 볼린저 계산
    assert bb["pb"].iloc[-1] == 0.5  # %b는 0.5
    assert bb["bw"].iloc[-1] == 0.0  # 밴드폭은 0


def test_rsi_extremes():  # RSI 극단값
    up = pd.Series(np.arange(1.0, 40.0))  # 계속 상승
    assert ind.rsi_wilder(up, 14).iloc[-1] == 100.0  # 상승만 있으면 100
    flat = pd.Series([5.0] * 40)  # 변화 없음
    assert ind.rsi_wilder(flat, 14).iloc[-1] == 50.0  # 변화 없으면 50


def test_rsi_range_and_warmup():  # RSI 범위와 초반 NaN
    rsi = ind.rsi_wilder(pd.Series(sample_closes(100)), 14)  # RSI 계산
    assert rsi.iloc[:14].isna().all()  # 앞 14개는 NaN
    valid = rsi.dropna()  # 유효값
    assert ((valid >= 0) & (valid <= 100)).all()  # 0~100 범위


def test_macd_histogram_identity():  # MACD 히스토그램 = MACD − 시그널
    m = ind.macd(pd.Series(sample_closes(100)), 12, 26, 9)  # MACD 계산
    ok = m.dropna()  # 유효 구간
    assert len(ok) > 0  # 값이 있어야 함
    assert (ok["hist"] - (ok["macd"] - ok["signal"])).abs().max() < 1e-12  # 항등식


def test_log_returns_skip_nonpositive():  # 음수 가격 제외
    s = pd.Series([10.0, 11.0, -5.0, 8.0, 9.0])  # 음수 포함
    r = ind.log_returns(s)  # 로그수익률
    assert len(r) == 2  # 10→11, 8→9 두 개만
    assert np.isfinite(r).all()  # 모두 유한


def test_robust_vol_flat_prices_uses_floor():  # 가격이 전혀 안 변할 때 하한 적용
    sd, note = ind.robust_vol(pd.Series([100.0] * 80), 20)  # 방어적 변동성
    assert sd == cfg.SD_FLOOR  # 하한 사용
    assert note is not None  # 안내 문구 있음


# ───────────────────────── 예측 ─────────────────────────
@pytest.mark.parametrize("freq", ["D", "W"])  # 일간·주간 모두 검증
def test_probabilities_sum_to_one(freq):  # 확률 합 검증
    win = cfg.WINDOWS[freq]  # 프리셋
    closes = sample_closes(120)  # 가상 종가
    sd = ind.realized_vol(pd.Series(closes), win["vol"])  # 변동성
    res = compute_forecast(closes, 0.5, 0.5, win["forecast_bars"], closes[-1] * 0.95, closes[-1] * 1.05, win, sd)  # 예측
    assert len(res["rows"]) == win["forecast_bars"]  # 봉 수
    for r in res["rows"]:  # 봉마다
        assert r["p3_up"] + r["p3_flat"] + r["p3_dn"] == pytest.approx(1.0)  # 세 확률의 합은 1
        assert 0 <= r["p3_flat"] <= 1  # 보합 확률 범위
        assert r["lo2"] < r["lo1"] < r["center"] < r["hi1"] < r["hi2"]  # 범위 순서


def test_zero_weights_center_is_flat():  # 반영도 0이면 중심이 그대로
    closes = sample_closes(60)  # 가상 종가
    win = cfg.WINDOWS["D"]  # 일간 프리셋
    res = compute_forecast(closes, 0.0, 0.0, 5, closes[-1] * 0.9, closes[-1] * 1.1, win, 0.01)  # 예측
    for r in res["rows"]:  # 봉마다
        assert r["center"] == pytest.approx(closes[-1])  # 기대 종가 불변
        assert r["cum"] == pytest.approx(0.5)  # 누적 상승 확률 50%


def test_forecast_errors_are_korean():  # 오류 문구는 한글
    win = cfg.WINDOWS["D"]  # 프리셋
    with pytest.raises(ValueError, match="부족"):  # 종가 부족
        compute_forecast([1.0] * 5, 0.5, 0.5, 5, 0.9, 1.1, win, 0.01)  # 호출
    with pytest.raises(ValueError, match="변동성"):  # 변동성 0
        compute_forecast([1.0] * 40, 0.5, 0.5, 5, 0.9, 1.1, win, 0.0)  # 호출


def test_level_probability_touch_cap():  # 터치 근사는 100% 상한
    lp = level_probability(100.0, 0.01, 0.0, 5, 100.0)  # 현재가와 같은 레벨
    assert lp["touch"] <= 1.0  # 상한
    assert lp["beyond"] == pytest.approx(0.5)  # 현재가 레벨은 50%


def test_next_dates_skip_weekend_and_weekly():  # 예측 날짜 규칙
    d = next_dates("2026-10-02", 3, "D")  # 금요일 다음 3영업일
    assert d == ["2026-10-05", "2026-10-06", "2026-10-07"]  # 주말 건너뜀
    w = next_dates("2026-10-02", 2, "W")  # 주간
    assert w == ["2026-10-09", "2026-10-16"]  # 7일 간격


def test_weekly_bars_collapses_daily_filled_data():  # 일간으로 채워진 데이터를 주간 봉으로
    from src.payload import weekly_bars  # 주간 봉 변환 함수
    idx = pd.bdate_range("2026-09-14", periods=10)  # 2주치 영업일
    s = pd.Series([1, 1, 1, 1, 2, 2, 2, 3, 3, 4], index=idx, dtype=float)  # 주 단위로만 바뀌는 가격
    w = weekly_bars(s)  # 주간 변환
    assert list(w.values) == [2.0, 4.0]  # 주마다 마지막 값
    assert [d.strftime("%Y-%m-%d") for d in w.index] == ["2026-09-18", "2026-09-25"]  # 날짜는 그 값의 실제 날짜
    sparse = pd.Series([10.0, 11.0], index=pd.to_datetime(["2026-09-16", "2026-09-23"]))  # 이미 주 1회인 데이터
    assert list(weekly_bars(sparse).values) == [10.0, 11.0]  # 변화 없음
    assert weekly_bars(pd.Series(dtype=float)).empty  # 빈 입력


def test_weekly_items_get_weekly_presets():  # 주간 품목 지정 확인
    freq = {it["key"]: it["freq"] for it in cfg.ITEMS}  # 키별 주기
    for key in ("ABS", "PS", "HIPS", "AN_CFR_FE", "ETHYLENE", "PROPYLENE", "BD_CFR_CN"):  # 주간 가격 품목
        assert freq[key] == "W", key  # 주간으로 지정됨
    for key in ("WTI_NYMEX", "NAPHTHA", "BZ_FOB_KR", "SM_CFR_CN", "SM_EAST_CN"):  # 일간 품목
        assert freq[key] == "D", key  # 일간 유지


# ───────────────────────── 기존 WTI 앱 이식 검증 ─────────────────────────
def load_wti_forecast():  # 기존 WTI 앱 forecast 모듈 불러오기
    """기존 WTI 앱의 src 패키지를 별도 이름으로 불러옵니다."""  # 함수 설명
    spec = importlib.util.spec_from_file_location("wtirepo", WTI_REPO / "src" / "__init__.py", submodule_search_locations=[str(WTI_REPO / "src")])  # 패키지 스펙
    pkg = importlib.util.module_from_spec(spec)  # 패키지 생성
    sys.modules["wtirepo"] = pkg  # 등록
    spec.loader.exec_module(pkg)  # 실행
    return importlib.import_module("wtirepo.forecast")  # forecast 모듈 반환


@pytest.mark.skipif(not WTI_REPO.exists() or not cfg.PRICES_CSV.exists(), reason="기존 WTI 앱 폴더 또는 data/prices.csv 가 없어 건너뜁니다")  # 없으면 건너뜀
def test_port_matches_original_wti_app():  # 이식 정확도
    old = load_wti_forecast()  # 기존 모듈
    closes = read_prices()["NMCL001"].dropna().tolist()[-300:]  # 실제 WTI 종가 최근 300개
    win = cfg.WINDOWS["D"]  # 일간 프리셋
    sd = ind.realized_vol(pd.Series(closes), win["vol"])  # 변동성
    new = compute_forecast(closes, 0.5, 0.5, 5, closes[-1] * 0.97, closes[-1] * 1.03, win, sd)  # 이 프로젝트 결과
    ref = old.compute_forecast(closes, 0.5, 0.5, 5, closes[-1] * 0.97, closes[-1] * 1.03)  # 기존 앱 결과
    assert new["pb"] == pytest.approx(ref["pb"])  # %b 일치
    assert new["slope"] == pytest.approx(ref["slope"])  # 기울기 일치
    for a, b in zip(new["rows"], ref["rows"]):  # 봉별 비교
        for key in ("m", "p_up", "cum", "center", "lo1", "hi2", "p3_up", "p3_flat", "p3_dn", "p_below", "p_above"):  # 주요 항목
            assert a[key] == pytest.approx(b[key], rel=1e-9, abs=1e-12), key  # 완전 일치


# ───────────────────────── 자바스크립트 모델 일치 ─────────────────────────
def extract_js_model() -> str:  # 템플릿에서 모델 코드 추출 함수
    """템플릿의 MODEL-START ~ MODEL-END 사이 코드를 문자열로 돌려줍니다."""  # 함수 설명
    text = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")  # 템플릿 읽기
    start = text.index("// MODEL-START")  # 시작 표시
    end = text.index("// MODEL-END")  # 끝 표시
    return text[start:end]  # 사이 코드 반환


@pytest.mark.skipif(shutil.which("node") is None, reason="node가 없어 건너뜁니다")  # node 없으면 건너뜀
@pytest.mark.parametrize("freq", ["D", "W"])  # 일간·주간
def test_js_model_matches_python(freq, tmp_path):  # JS와 파이썬 일치
    win = cfg.WINDOWS[freq]  # 프리셋
    closes = sample_closes(120, seed=11)  # 가상 종가
    sd = ind.realized_vol(pd.Series(closes), win["vol"])  # 변동성
    lo, hi = float(closes[-1] * 0.96), float(closes[-1] * 1.04)  # 아래·위 레벨(순수 float로 변환)
    py = compute_forecast(closes, 0.7, 0.3, win["forecast_bars"], lo, hi, win, sd)  # 파이썬 결과
    pr = {"sd": sd, "trend_decay": cfg.TREND_DECAY, "kappa_scale": cfg.KAPPA_SCALE, "flat_band_first": win["flat_first"], "flat_band_last": win["flat_last"]}  # 모델 설정
    script = extract_js_model() + (  # 모델 코드 + 실행부
        f"\nconst out = computeModel({json.dumps(closes)}, 0.7, 0.3, {win['forecast_bars']}, {lo!r}, {hi!r}, {json.dumps(pr)}, {json.dumps({'bb': win['bb'], 'trend': win['trend']})});\n"
        "console.log(JSON.stringify(out.rows));\n"
    )  # 스크립트 끝
    path = tmp_path / "model.js"  # 임시 파일
    path.write_text(script, encoding="utf-8")  # 저장
    proc = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=60)  # node 실행
    assert proc.returncode == 0, proc.stderr  # 정상 종료
    js_rows = json.loads(proc.stdout)  # JS 결과
    assert len(js_rows) == len(py["rows"])  # 봉 수 일치
    pairs = [("pUp", "p_up"), ("cum", "cum"), ("p3Up", "p3_up"), ("p3Flat", "p3_flat"), ("p3Dn", "p3_dn"), ("pBelow", "p_below"), ("pAbove", "p_above")]  # 확률 항목
    for j, p in zip(js_rows, py["rows"]):  # 봉별 비교
        for jk, pk in pairs:  # 항목별
            assert abs(j[jk] - p[pk]) < 1e-5, (jk, j[jk], p[pk])  # erf 근사 오차 이내
        for k in ("center", "lo1", "hi2"):  # 가격 항목
            assert abs(j[k] / p[k] - 1) < 1e-5, k  # 상대 오차 이내


# ───────────────────────── 데이터 입출력 ─────────────────────────
def test_resolve_item_variants():  # 품목 이름 해석
    assert resolve_item("AAMFI00")["key"] == "SM_CFR_CN"  # 코드
    assert resolve_item("sm_cfr_cn")["code"] == "AAMFI00"  # 키(소문자)
    assert resolve_item("SM CFR 중국")["key"] == "SM_CFR_CN"  # 탭 이름
    assert resolve_item("ABS")["code"] == "PHAHF00"  # 짧은 키


def test_hidden_items_are_not_resolvable():  # 표시하지 않는 품목은 입력 대상이 아님
    with pytest.raises(DataError, match="찾을 수 없습니다"):  # SM FOB 한국(AAMFL00)은 제외됨
        resolve_item("AAMFL00")  # 호출


def test_resolve_item_errors_are_korean():  # 해석 오류는 한글
    with pytest.raises(DataError, match="찾을 수 없습니다"):  # 없는 품목
        resolve_item("없는품목XYZ")  # 호출
    with pytest.raises(DataError, match="여러 개"):  # 모호한 이름
        resolve_item("SM")  # 호출
    with pytest.raises(DataError, match="비어"):  # 빈 입력
        resolve_item("  ")  # 호출


def test_parse_assignments():  # 입력 토큰 해석
    got = parse_assignments(["SM_CFR_CN=1,420.5", "ABS=1500"])  # 쉼표 포함 입력
    assert got == {"AAMFI00": 1420.5, "PHAHF00": 1500.0}  # 결과
    with pytest.raises(DataError, match="형식"):  # 등호 없음
        parse_assignments(["SM_CFR_CN1420"])  # 호출
    with pytest.raises(DataError, match="숫자"):  # 숫자 아님
        parse_assignments(["SM_CFR_CN=abc"])  # 호출
    with pytest.raises(DataError, match="두 번"):  # 중복
        parse_assignments(["ABS=1", "PHAHF00=2"])  # 호출


def test_upsert_add_update_and_warnings():  # 입력·수정·경고
    df = sample_frame(30)  # 가상 표
    last = df.index[-1]  # 마지막 날짜
    when = last + pd.Timedelta(days=3)  # 마지막 날짜 뒤 월요일
    code = "AAMFI00"  # SM_CFR_CN
    new, rep = upsert_row(df, when, {code: float(df[code].iloc[-1]) * 1.01})  # 추가
    assert when.normalize() in new.index  # 새 행 생김
    assert rep["added"] and not rep["updated"]  # 추가로 기록
    new2, rep2 = upsert_row(new, when, {code: float(df[code].iloc[-1]) * 1.02})  # 같은 날 덮어쓰기
    assert rep2["updated"] and not rep2["added"]  # 수정으로 기록
    _, rep3 = upsert_row(df, when, {code: float(df[code].iloc[-1]) * 2})  # 100% 급변동
    assert any("급변동" in w for w in rep3["warnings"])  # 경고 발생
    sat = pd.Timestamp("2026-09-26")  # 토요일
    _, rep4 = upsert_row(df, sat, {code: float(df[code].iloc[-1])})  # 주말 입력
    assert any("주말" in w for w in rep4["warnings"])  # 주말 경고
    assert len(df) == 30  # 원본은 변하지 않음


def test_upsert_rejects_bad_input():  # 잘못된 입력 거부
    df = sample_frame(30)  # 가상 표
    with pytest.raises(DataError, match="0 이하"):  # 0 이하 가격
        upsert_row(df, "2026-10-01", {"AAMFI00": 0.0})  # 호출
    upsert_row(df, "2026-10-01", {"AAMFI00": -1.0}, allow_nonpositive=True)  # 허용 옵션이면 통과
    with pytest.raises(DataError, match="미래"):  # 먼 미래
        upsert_row(df, "2099-01-01", {"AAMFI00": 1.0})  # 호출
    with pytest.raises(DataError, match="날짜"):  # 잘못된 날짜
        upsert_row(df, "어제", {"AAMFI00": 1.0})  # 호출
    with pytest.raises(DataError, match="입력된 가격이 없습니다"):  # 빈 입력
        upsert_row(df, "2026-10-01", {})  # 호출


def test_csv_roundtrip(tmp_path):  # CSV 저장·읽기 왕복
    df = sample_frame(20)  # 가상 표
    path = write_prices(df, tmp_path / "p.csv")  # 저장
    back = read_prices(path)  # 읽기
    assert list(back.columns) == [it["code"] for it in cfg.ITEMS]  # 열 순서
    assert np.allclose(back.to_numpy(), df.to_numpy())  # 값 일치
    with pytest.raises(DataError, match="찾을 수 없습니다"):  # 없는 파일
        read_prices(tmp_path / "없음.csv")  # 호출


def test_import_xlsx_roundtrip(tmp_path):  # 엑셀 불러오기(가상 파일)
    df = sample_frame(10)  # 가상 표
    rows = [["Platts 가상 헤더"] + [""] * len(cfg.ITEMS), ["Symbol"] + [it["code"] for it in cfg.ITEMS]]  # 헤더 2행
    for d, r in df.iloc[::-1].iterrows():  # 내림차순으로 기록(실제 파일과 같은 형태)
        rows.append([d.to_pydatetime()] + r.tolist())  # 날짜 + 가격
    path = tmp_path / "fake.xlsx"  # 임시 엑셀
    pd.DataFrame(rows).to_excel(path, header=False, index=False)  # 저장
    frame, notes = import_xlsx(path)  # 불러오기
    assert len(frame) == 10  # 행 수
    assert frame.index.is_monotonic_increasing  # 오름차순으로 정리
    assert np.allclose(frame.to_numpy(), df.to_numpy())  # 값 일치
    bad = tmp_path / "bad.xlsx"  # 형식이 다른 엑셀
    pd.DataFrame([["a", "b"], [1, 2]]).to_excel(bad, header=False, index=False)  # 저장
    with pytest.raises(DataError, match="품목 코드 행"):  # 코드 행 없음
        import_xlsx(bad)  # 호출
    with pytest.raises(DataError, match="찾을 수 없습니다"):  # 없는 파일
        import_xlsx(tmp_path / "없음.xlsx")  # 호출


# ───────────────────────── 페이지 데이터 · 사이트 · CLI ─────────────────────────
def test_build_all_on_sample_data():  # 가상 데이터로 전체 생성
    payload, errors = build_all(sample_frame(150))  # 생성
    assert errors == []  # 오류 없음
    assert len(payload["items"]) == len(cfg.SHOW_CODES) == 12  # 표시 품목 수(12개)
    assert set(payload["items"]) == set(cfg.SHOW_CODES)  # 지정한 코드만 포함
    for code, it in payload["items"].items():  # 품목마다
        assert it["forecast"]["rows"], code  # 예측 행 존재
        for r in it["forecast"]["rows"]:  # 행마다
            assert math.isfinite(r["p3_up"]) and math.isfinite(r["center"]), code  # 유한 값


def test_build_all_short_history_is_graceful():  # 봉이 부족한 품목은 오류 문구만
    df = sample_frame(150)  # 가상 표
    df.loc[df.index[:-10], "AAMFI00"] = np.nan  # 한 품목은 10개만 남김
    payload, _ = build_all(df)  # 생성
    item = payload["items"]["AAMFI00"]  # 해당 품목
    assert item.get("error")  # 안내 문구 존재
    assert "부족" in item["error"]  # 한글 안내


def test_render_site_embeds_data(tmp_path):  # 사이트 생성
    payload, _ = build_all(sample_frame(150))  # 생성
    out = render_site(payload, site_dir=tmp_path)  # 렌더링
    html = Path(out).read_text(encoding="utf-8")  # 읽기
    assert cfg.PLACEHOLDER not in html  # 자리 표시가 치환됨
    assert "CHEMDATA" in html  # 전역 변수 존재


def test_cli_update_flow(tmp_path, monkeypatch, capsys):  # 명령행 입력 흐름(임시 폴더, 실데이터 보호)
    monkeypatch.setattr(cfg, "PRICES_CSV", tmp_path / "prices.csv")  # CSV 경로를 임시 폴더로 교체
    write_prices(sample_frame(150), tmp_path / "prices.csv")  # 가상 가격 저장
    code = cli_run(["update", "--date", "2026-09-01", "SM_CFR_CN=100", "--no-build"])  # 가격 입력
    assert code == 0  # 정상 종료
    assert read_prices(tmp_path / "prices.csv").loc["2026-09-01", "AAMFI00"] == 100.0  # 저장됨
    capsys.readouterr()  # 앞선 출력 비우기
    before = (tmp_path / "prices.csv").read_text(encoding="utf-8")  # 실패 전 파일 내용
    bad = cli_run(["update", "--date", "2026-09-02", "없는품목=1", "--no-build"])  # 잘못된 품목
    out = capsys.readouterr().out  # 출력 읽기
    assert bad == 1  # 실패 종료 코드
    assert "[오류]" in out and "찾을 수 없습니다" in out  # 한글 오류 안내
    assert (tmp_path / "prices.csv").read_text(encoding="utf-8") == before  # 실패하면 파일이 바뀌지 않음


def test_real_data_builds_without_errors():  # 실제 데이터(prices.csv)로 전체 생성
    if not cfg.PRICES_CSV.exists():  # 파일이 없으면
        pytest.skip("data/prices.csv 가 없어 건너뜁니다")  # 건너뜀
    payload, errors = build_all(read_prices())  # 생성
    assert errors == []  # 오류 없음
    assert list(payload["items"]) == [c for c in [it["code"] for it in cfg.ITEMS] if c in cfg.SHOW_CODES]  # 지정한 12개만, 탭 순서대로
    assert len(payload["items"]) == 12  # 12개 품목
