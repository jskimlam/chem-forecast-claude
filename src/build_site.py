"""사이트 빌드 모듈(데이터를 HTML 템플릿에 심어 정적 페이지를 만듭니다)."""  # 모듈 설명
# 필요 라이브러리 설치: 없음(표준 라이브러리만 사용)
import json  # JSON 변환용
import os  # 환경변수 읽기용
import math  # NaN 검사용
import re  # 태그 정리용
from pathlib import Path  # 경로 처리용

from . import config as cfg  # 설정 상수 불러오기


class BuildError(Exception):  # 빌드 오류를 구분하기 위한 예외
    """사이트 빌드 단계에서 발생하는 오류(메시지는 한글)."""  # 예외 설명


def to_jsonable(obj):  # JSON으로 바꿀 수 있게 정리하는 함수
    """NaN·무한대를 None으로 바꾸고 넘파이 타입을 파이썬 기본 타입으로 바꿉니다."""  # 함수 설명
    if isinstance(obj, dict):  # 사전이면
        return {str(k): to_jsonable(v) for k, v in obj.items()}  # 값을 재귀로 정리
    if isinstance(obj, (list, tuple)):  # 리스트이면
        return [to_jsonable(v) for v in obj]  # 항목을 재귀로 정리
    if hasattr(obj, "item") and not isinstance(obj, (str, bytes)):  # 넘파이 스칼라이면
        return to_jsonable(obj.item())  # 파이썬 기본 타입으로 변환
    if isinstance(obj, float):  # 실수이면
        return None if (math.isnan(obj) or math.isinf(obj)) else obj  # NaN·무한대는 None
    if obj is None or isinstance(obj, (str, int, bool)):  # 기본 타입이면
        return obj  # 그대로 반환
    return str(obj)  # 그 밖의 타입은 문자열로


def embed_json(payload: dict) -> str:  # 페이지에 심을 JSON 문자열을 만드는 함수
    """HTML 안에 안전하게 넣을 수 있는 JSON 문자열을 돌려줍니다."""  # 함수 설명
    text = json.dumps(to_jsonable(payload), ensure_ascii=False, allow_nan=False, separators=(",", ":"))  # JSON 문자열
    text = text.replace("</", "<\\/").replace("<!--", "<\\!--")  # 스크립트 태그를 닫는 문자열을 무력화
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")  # 줄바꿈 특수문자 처리


def to_fragment(html: str) -> str:  # 아티팩트 게시용 조각을 만드는 함수
    """doctype·html·head·body 태그와 meta(charset, viewport)를 걷어내 게시 도구가 감쌀 수 있는 조각으로 만듭니다."""  # 함수 설명
    out = re.sub(r"(?is)<!doctype[^>]*>", "", html)  # doctype 제거
    out = re.sub(r"(?is)</?(html|head|body)\b[^>]*>", "", out)  # html/head/body 태그 제거
    out = re.sub(r"(?is)<meta\s+(charset|name=\"viewport\")[^>]*>", "", out)  # charset·viewport meta 제거
    return out.strip() + "\n"  # 앞뒤 공백 정리


def admin_items() -> list:  # 입력 페이지용 품목 목록 함수
    """admin.html 에 심을 표시 품목 정보(코드·이름·그룹·주기·단위)를 만듭니다."""  # 함수 설명
    gname = {g["id"]: g["label"] for g in cfg.GROUPS}  # 그룹 이름 사전
    return [{"code": it["code"], "key": it["key"], "label": it["label"], "group": it["group"], "groupLabel": gname[it["group"]], "freq": it["freq"], "unit": cfg.unit_label(it)} for it in cfg.shown_items()]  # 표시 품목만


def render_admin(template_dir: Path, site_dir: Path, gas_url: str = None) -> Path:  # 입력 페이지 생성 함수
    """templates/admin.html 에 품목 목록과 웹앱 주소를 심어 site/admin.html 을 만듭니다. 템플릿이 없으면 None을 돌려줍니다."""  # 함수 설명
    tpl = Path(template_dir) / "admin.html"  # 입력 페이지 템플릿
    if not tpl.exists():  # 없으면
        return None  # 건너뜀
    gas_url = os.environ.get("CHEM_GAS_URL", "") if gas_url is None else gas_url  # 웹앱 주소(기본: 환경변수)
    html = tpl.read_text(encoding="utf-8")  # 템플릿 읽기
    for key in ("__GAS_URL__", "__ITEMS_JSON__"):  # 자리 표시 확인
        if key not in html:  # 없으면
            raise BuildError(f"입력 페이지 템플릿에 {key} 자리 표시가 없습니다.")  # 한글 오류 안내
    html = html.replace("__GAS_URL__", embed_json(gas_url.strip())).replace("__ITEMS_JSON__", embed_json(admin_items()))  # 값 심기
    out = Path(site_dir) / "admin.html"  # 산출물 경로
    out.write_text(html, encoding="utf-8")  # 저장
    return out  # 경로 반환


def render_site(payload: dict, template_path: Path = None, site_dir: Path = None) -> Path:  # 사이트를 만드는 함수
    """템플릿에 데이터를 심어 index.html을 만들고 경로를 돌려줍니다."""  # 함수 설명
    template_path = Path(template_path) if template_path else cfg.TEMPLATE_PATH  # 템플릿 경로
    site_dir = Path(site_dir) if site_dir else cfg.SITE_DIR  # 산출물 폴더
    if not template_path.exists():  # 템플릿이 없으면
        raise BuildError(f"파일을 찾을 수 없습니다: {template_path}")  # 한글 오류 안내
    html = template_path.read_text(encoding="utf-8")  # 템플릿 읽기
    if cfg.PLACEHOLDER not in html:  # 자리 표시가 없으면
        raise BuildError(f"템플릿에 데이터 자리 표시({cfg.PLACEHOLDER})가 없습니다.")  # 한글 오류 안내
    site_dir.mkdir(parents=True, exist_ok=True)  # 산출물 폴더 만들기
    full = html.replace(cfg.PLACEHOLDER, embed_json(payload))  # 데이터를 심은 전체 페이지
    out = site_dir / "index.html"  # 산출물 파일
    out.write_text(full, encoding="utf-8")  # 페이지 저장
    (site_dir / "artifact.html").write_text(to_fragment(full), encoding="utf-8")  # 아티팩트 게시용 조각 저장
    render_admin(template_path.parent, site_dir)  # 입력 페이지(admin.html) 생성
    return out  # 경로 반환
