"""시트 연동 테스트: Code.gs(가짜 시트 하네스), 시트 동기화(sync), 입력 페이지(admin.html) 생성."""  # 모듈 설명
# 필요 라이브러리 설치: pip install pandas numpy openpyxl pytest
import json  # JSON 입출력용
import shutil  # node 존재 확인용
import subprocess  # node 실행용
import sys  # 경로 설정용
import threading  # 임시 웹서버 실행용
from http.server import BaseHTTPRequestHandler, HTTPServer  # 임시 웹서버
from pathlib import Path  # 경로 처리용

import pandas as pd  # 표 데이터 처리용
import pytest  # 테스트 프레임워크

ROOT = Path(__file__).resolve().parent.parent  # 프로젝트 최상위 폴더
sys.path.insert(0, str(ROOT))  # 프로젝트 패키지를 불러올 수 있게 경로 추가

from src import config as cfg  # noqa: E402  설정
from src.build_site import admin_items, render_admin, to_fragment  # noqa: E402  입력 페이지 생성
from src.cli import run as cli_run  # noqa: E402  명령행 실행 함수
from src.data_io import DataError, read_prices, write_prices  # noqa: E402  가격 입출력
from src.sheet_sync import build_url, fetch_payload, payload_to_frame, sync_prices  # noqa: E402  시트 동기화

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node가 없어 건너뜁니다")  # node 없으면 건너뜀


# ───────────────────────── Code.gs (가짜 시트 위에서 실행) ─────────────────────────
@pytest.fixture(scope="module")
def gas():  # 하네스를 한 번만 실행해 결과를 공유
    if shutil.which("node") is None:  # node가 없으면
        pytest.skip("node가 없어 건너뜁니다")  # 건너뜀
    proc = subprocess.run(["node", str(ROOT / "tests" / "gas_harness.js")], capture_output=True, text=True, timeout=60)  # 하네스 실행
    assert proc.returncode == 0, proc.stderr  # 정상 종료
    return json.loads(proc.stdout)  # 시나리오별 결과


def test_gas_get_data_and_token(gas):  # 읽기 요청
    assert gas["get_ok"]["ok"] and gas["get_ok"]["codes"] == ["AAA", "BBB"]  # 코드 목록
    assert gas["get_ok"]["rows"][1] == ["2026-09-23", 101, 50]  # 값
    assert gas["get_ok"]["rows"][0][2] is None  # 빈 칸은 null
    assert gas["get_bad"]["code"] == "bad_secret" and "토큰이" in gas["get_bad"]["error"]  # 토큰 오류 문구
    assert gas["get_ping"]["ok"] and "rows" not in gas["get_ping"]  # ping은 데이터를 주지 않음
    assert gas["get_noaction"]["code"] == "bad_request"  # action 없음


def test_gas_latest(gas):  # 직전 가격 조회
    assert gas["latest"]["last"]["AAA"] == {"date": "2026-09-25", "price": 102}  # 마지막 값
    assert gas["latest"]["last"]["BBB"] == {"date": "2026-09-23", "price": 50}  # 비어 있는 날은 건너뛰고 마지막 값


def test_gas_save_insert_update_order(gas):  # 저장: 추가·중간 삽입·덮어쓰기
    assert gas["save_append"]["ok"] and gas["save_append"]["added"][0]["code"] == "AAA"  # 맨 아래 추가
    assert gas["save_middle"]["ok"]  # 중간 삽입
    assert gas["save_update"]["updated"] == [{"code": "BBB", "old": 50, "price": 51}]  # 덮어쓰기는 수정으로 기록
    assert gas["dates_after"] == ["date", "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-25", "2026-09-28"]  # 날짜 오름차순 유지
    assert gas["grid_after"][3] == [101, 51]  # 기존 값 보존 + 수정
    assert gas["grid_after"][2] == [100.5]  # 중간 삽입 행에 입력 품목만 채워짐


def test_gas_validation_errors_are_korean(gas):  # 입력 검증
    assert gas["err_date"]["code"] == "bad_date"  # 날짜 형식
    assert gas["err_future"]["code"] == "future_date"  # 미래 날짜
    assert gas["err_empty"]["code"] == "empty"  # 입력 없음
    assert gas["err_nan"]["code"] == "bad_value" and "숫자" in gas["err_nan"]["error"]  # 숫자 아님
    assert gas["err_zero"]["code"] == "bad_value" and "0 이하" in gas["err_zero"]["error"]  # 0 이하
    assert gas["err_code"]["code"] == "bad_value" and "헤더에 없는" in gas["err_code"]["error"]  # 모르는 코드
    assert gas["err_json"]["code"] == "bad_request"  # JSON 아님
    assert gas["err_action"]["code"] == "bad_request"  # 모르는 요청


def test_gas_confirm_flow(gas):  # 경고는 확인 후에만 저장
    assert gas["warn_big"]["needConfirm"] and "급변동" in gas["warn_big"]["warnings"][0]  # 급변동 경고
    assert gas["warn_big_rows"] == 4  # 확인 전에는 저장되지 않음
    assert gas["warn_big_confirm"]["ok"]  # 확인하면 저장
    assert gas["warn_weekend"]["needConfirm"] and "주말" in gas["warn_weekend"]["warnings"][0]  # 주말 경고
    assert gas["ok_negative"]["ok"]  # 음수 허용 옵션


def test_gas_password_lock(gas):  # 비밀번호 연속 실패 차단
    codes = [r["code"] for r in gas["pw_bad"]]  # 응답 코드 목록
    assert codes[:5] == ["bad_secret"] * 5 and codes[5] == "locked"  # 5번 틀리면 차단
    assert gas["pw_after_lock"]["code"] == "locked"  # 차단 중에는 맞는 비밀번호도 거부
    assert gas["pw_ok_resets"]["ok"] and gas["pw_counter_after_ok"]  # 성공하면 실패 횟수 초기화
    assert gas["not_configured"]["code"] == "not_configured" and "ADMIN_PASSWORD" in gas["not_configured"]["error"]  # 설정 누락 안내
    assert "READ_TOKEN" in gas["not_configured_get"]["error"]  # 토큰 설정 누락 안내


def test_gas_rebuild_trigger(gas):  # GitHub 재빌드 호출
    assert gas["rebuild"] == "started"  # 204면 시작
    call = gas["rebuild_call"][0]  # 호출 기록
    assert call["url"].endswith("/repos/me/repo/actions/workflows/build.yml/dispatches")  # 주소
    assert call["method"] == "post" and call["auth"] == "Bearer ghp_x" and json.loads(call["body"]) == {"ref": "main"}  # 요청 내용
    assert gas["rebuild_fail"] == "failed:404"  # 실패 코드 전달


def test_gas_sheet_format_edge_cases(gas):  # 시트 양식
    assert gas["bad_header"]["ok"] is False and "date" in gas["bad_header"]["error"]  # 헤더 오류 안내
    assert gas["text_cells"]["rows"] == [["2026-10-01", 1234.5], ["2026-09-25", 1300]]  # 글자 날짜·쉼표 숫자 처리
    assert "마지막 날짜: 2026-09-25" in gas["setup_check"]  # 점검 함수


# ───────────────────────── 시트 동기화 ─────────────────────────
def sample_payload() -> dict:  # 가상 시트 응답
    codes = list(cfg.SHOW_CODES)  # 표시 품목 코드
    rows = [[f"2026-09-{d:02d}"] + [100.0 + d + i for i in range(len(codes))] for d in (21, 22, 23, 24, 25)]  # 5일치
    return {"ok": True, "codes": codes, "rows": rows}  # 응답 형태


def test_build_url_validates():  # 주소 만들기
    assert build_url("https://x/exec", "t k").endswith("?action=data&token=t+k")  # 토큰 인코딩
    assert "&action=data" in build_url("https://x/exec?a=1", "t")  # 이미 인자가 있는 주소
    with pytest.raises(DataError, match="웹앱 주소"):  # 주소 없음
        build_url("", "t")  # 호출
    with pytest.raises(DataError, match="토큰"):  # 토큰 없음
        build_url("https://x", "")  # 호출


def test_payload_to_frame_ok_and_errors():  # 응답 변환
    frame, notes = payload_to_frame(sample_payload())  # 변환
    assert len(frame) == 5 and frame.index.is_monotonic_increasing  # 행 수·정렬
    assert list(frame.columns) == [it["code"] for it in cfg.ITEMS]  # 전체 열이 채워짐
    assert frame["NMCL001"].iloc[0] == 121.0  # 값
    assert frame["AAMFL00"].isna().all()  # 표시하지 않는 품목은 빈 열
    assert notes == []  # 안내 없음
    extra = sample_payload(); extra["codes"].append("ZZZ9999"); [r.append(1) for r in extra["rows"]]  # 모르는 코드 추가
    _, notes2 = payload_to_frame(extra)  # 변환
    assert any("ZZZ9999" in n for n in notes2)  # 안내
    short = sample_payload(); short["codes"] = short["codes"][:-1]; short["rows"] = [r[:-1] for r in short["rows"]]  # 한 품목 누락
    _, notes3 = payload_to_frame(short)  # 변환
    assert any("PHAHF00" in n for n in notes3)  # 누락 안내
    with pytest.raises(DataError, match="행이 없습니다"):  # 빈 시트
        payload_to_frame({"ok": True, "codes": ["NMCL001"], "rows": []})  # 호출
    with pytest.raises(DataError, match="길이"):  # 행 길이 불일치
        payload_to_frame({"ok": True, "codes": ["NMCL001"], "rows": [["2026-09-21"]]})  # 호출
    with pytest.raises(DataError, match="형식"):  # 형식 오류
        payload_to_frame({"ok": True})  # 호출


def test_sync_prices_writes_and_protects(tmp_path):  # 저장과 덮어쓰기 보호
    path = tmp_path / "prices.csv"  # 저장 경로
    frame, notes = sync_prices("https://x", "t", path, fetcher=lambda u, t: sample_payload())  # 첫 동기화
    assert path.exists() and len(read_prices(path)) == 5  # 저장됨
    small = {"ok": True, "codes": ["NMCL001"], "rows": [["2026-09-21", 1.0]]}  # 데이터가 훨씬 적은 응답
    before = path.read_text(encoding="utf-8")  # 기존 내용
    with pytest.raises(DataError, match="절반 미만"):  # 덮어쓰기 거부
        sync_prices("https://x", "t", path, fetcher=lambda u, t: small)  # 호출
    assert path.read_text(encoding="utf-8") == before  # 파일은 그대로
    sync_prices("https://x", "t", path, fetcher=lambda u, t: sample_payload())  # 정상 재동기화
    assert path.with_suffix(".csv.bak").exists()  # 백업 생성


class FakeGas(BaseHTTPRequestHandler):  # 임시 웹앱(실제 HTTP 통신 검증용)
    def do_GET(self):  # GET 처리
        if self.path.startswith("/html"):  # 로그인 화면 같은 HTML
            body = b"<html>login</html>"  # JSON 아님
        elif "token=good" in self.path and "action=data" in self.path:  # 올바른 토큰
            body = json.dumps(sample_payload()).encode("utf-8")  # 정상 응답
        else:  # 토큰 오류
            body = json.dumps({"ok": False, "error": "토큰이 맞지 않습니다."}).encode("utf-8")  # 실패 응답
        if self.path.startswith("/err500"):  # 서버 오류
            self.send_response(500); self.end_headers(); return  # 500 응답
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)  # 응답 전송

    def log_message(self, *args):  # 로그 출력 끄기
        pass  # 아무것도 안 함


@pytest.fixture()
def server():  # 임시 서버 실행
    srv = HTTPServer(("127.0.0.1", 0), FakeGas)  # 빈 포트에 서버 생성
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()  # 백그라운드 실행
    yield f"http://127.0.0.1:{srv.server_address[1]}"  # 주소 전달
    srv.shutdown()  # 종료


def test_fetch_payload_over_http(server):  # 실제 통신
    assert fetch_payload(server + "/exec", "good")["ok"]  # 정상
    with pytest.raises(DataError, match="토큰이 맞지 않습니다"):  # 토큰 오류 전달
        fetch_payload(server + "/exec", "bad")  # 호출
    with pytest.raises(DataError, match="읽지 못했습니다"):  # HTML 응답
        fetch_payload(server + "/html", "good")  # 호출
    with pytest.raises(DataError, match="HTTP 500"):  # 서버 오류
        fetch_payload(server + "/err500", "good")  # 호출
    with pytest.raises(DataError, match="연결하지 못했습니다"):  # 연결 불가
        fetch_payload("http://127.0.0.1:9/exec", "good", timeout=3)  # 호출


def test_cli_sync_flow(server, tmp_path, monkeypatch, capsys):  # 명령행 sync
    monkeypatch.setattr(cfg, "PRICES_CSV", tmp_path / "prices.csv")  # 저장 경로를 임시 폴더로 교체
    code = cli_run(["sync", "--url", server + "/exec", "--token", "good", "--no-build"])  # 동기화
    assert code == 0 and (tmp_path / "prices.csv").exists()  # 성공
    assert "5행" in capsys.readouterr().out  # 완료 안내
    code = cli_run(["sync", "--url", server + "/exec", "--token", "bad", "--no-build"])  # 토큰 오류
    out = capsys.readouterr().out  # 출력
    assert code == 1 and "[오류]" in out and "토큰이 맞지 않습니다" in out  # 한글 오류
    monkeypatch.delenv("CHEM_GAS_URL", raising=False); monkeypatch.delenv("CHEM_GAS_TOKEN", raising=False)  # 환경변수 제거
    assert cli_run(["sync", "--no-build"]) == 1  # 주소·토큰 없음
    assert "웹앱 주소가 없습니다" in capsys.readouterr().out  # 한글 안내


# ───────────────────────── 입력 페이지(admin.html) ─────────────────────────
def test_admin_items_match_shown_items():  # 입력 페이지 품목 = 표시 품목
    items = admin_items()  # 품목 목록
    assert [i["code"] for i in items] == [it["code"] for it in cfg.shown_items()]  # 같은 순서
    assert all({"code", "label", "groupLabel", "freq", "unit"} <= set(i) for i in items)  # 필요한 키


def test_render_admin_embeds_values(tmp_path):  # 값 심기
    out = render_admin(ROOT / "templates", tmp_path, gas_url="https://script.google.com/macros/s/ABC/exec")  # 생성
    html = out.read_text(encoding="utf-8")  # 읽기
    assert "__GAS_URL__" not in html and "__ITEMS_JSON__" not in html  # 자리 표시 치환
    assert '"https://script.google.com/macros/s/ABC/exec"' in html  # 주소 심김
    assert "NMCL001" in html and "AAMFL00" not in html  # 표시 품목만
    out2 = render_admin(ROOT / "templates", tmp_path, gas_url="")  # 주소 없이 생성
    assert 'var GAS_URL = ""' in out2.read_text(encoding="utf-8")  # 빈 주소


@needs_node
def test_admin_script_parses(tmp_path):  # 입력 페이지 스크립트 문법 검사
    html = render_admin(ROOT / "templates", tmp_path, gas_url="").read_text(encoding="utf-8")  # 생성
    start = html.index("<script>") + len("<script>")  # 스크립트 시작
    end = html.index("</script>", start)  # 스크립트 끝
    js = tmp_path / "admin.js"  # 임시 파일
    js.write_text(html[start:end], encoding="utf-8")  # 저장
    proc = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)  # 문법 검사
    assert proc.returncode == 0, proc.stderr  # 통과


def test_to_fragment_strips_document_tags():  # 게시용 조각 변환
    frag = to_fragment('<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>t</title></head><body><header>x</header></body></html>')  # 변환
    assert "<html" not in frag and "<head>" not in frag and "<body" not in frag and "doctype" not in frag.lower()  # 문서 태그 제거
    assert "<header>x</header>" in frag and "<title>t</title>" in frag  # 내용 보존
