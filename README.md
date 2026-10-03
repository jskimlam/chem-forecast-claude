# chem-forecast-claude

Platts 대표 지표 12개의 종가로 이동평균·볼린저·RSI·MACD·지지저항·방향 확률을 보여주는 대시보드입니다.
가격은 **구글시트**가 원본이고, GitHub Actions 가 시트를 읽어 페이지를 만들어 **GitHub Pages** 로 배포합니다.

```
admin.html (비밀번호) ──저장──▶ Apps Script 웹앱 ──▶ 구글시트(prices 탭)
                                      │ 저장 직후 / 평일 08:00 KST
                                      ▼
                  GitHub Actions: 시트 읽기 → 테스트 → 대시보드 빌드 → Pages 배포
```

- 대시보드: `https://<계정>.github.io/chem-forecast-claude/`
- 가격 입력: `https://<계정>.github.io/chem-forecast-claude/admin.html`

## 표시 품목 (src/config.py 의 SHOW_CODES)
NMCL001 WTI · PAAAD00 납사 · AAMFI00 SM CFR 중국 · AAOTU00 SM 동중국(위안) · AAOTM00 에틸렌 · PHASM05 벤젠 FOB 한국 · AAWWK00 프로필렌 · PHAOO00 AN(주간) · AAWWL00 BD CFR 중국 · PHAIL00 PS(주간) · PHAIR00 HIPS(주간) · PHAHF00 ABS(주간)

품목을 바꾸려면 `SHOW_CODES` 를 고치고 시트 헤더에도 같은 코드를 둡니다(탭 이름은 `price` 또는 `prices`, 없으면 첫 번째 탭). 주간/일간은 같은 파일의 품목별 `freq` 한 글자(W/D)로 바꿉니다.

## 최초 설정 (한 번만)
1. **시트:** `price` 탭 A1 에 `date`, B1부터 12개 코드를 두고 과거 데이터를 붙여 넣습니다. (날짜 오름차순, 주간 품목은 가격이 나온 날만 값)
2. **Apps Script:** 시트에서 *확장 프로그램 > Apps Script* → `apps_script/Code.gs` 전체를 붙여 넣기.
   *프로젝트 설정 > 스크립트 속성*에 추가:
   - `ADMIN_PASSWORD` : 입력 페이지 비밀번호
   - `READ_TOKEN` : 길고 무작위인 문자열(빌드용)
   - (선택) `GITHUB_TOKEN`, `GITHUB_REPO=jskimlam/chem-forecast-claude` : 저장 직후 바로 재빌드
   편집기에서 `setupCheck` 를 실행해 `[OK]` 인지 확인한 뒤 *배포 > 새 배포 > 웹 앱*(실행: 나, 액세스: 모든 사용자)으로 배포하고 `/exec` 주소를 복사합니다.
3. **GitHub:** *Settings > Secrets and variables > Actions* 에 `CHEM_GAS_URL`(배포 주소), `CHEM_GAS_TOKEN`(= READ_TOKEN 값) 추가.
   *Settings > Pages > Source* 를 **GitHub Actions** 로 바꾸고, *Actions > build-site > Run workflow* 를 한 번 실행합니다.
4. `GITHUB_TOKEN`(선택): 이 레포에 한정한 fine-grained 토큰, 권한 *Actions: Read and write*.

## 매일 쓰는 법
`admin.html` 에서 비밀번호 입력 → 날짜 선택 → 가격 입력 → 저장. 직전 대비 ±25% 초과와 주말 날짜는 확인 후에만 저장됩니다.
(시트에 직접 입력해도 됩니다. 이 경우 Actions 의 *Run workflow* 를 누르거나 다음 평일 아침을 기다립니다.)

## 로컬에서 돌리기
```
pip install -r requirements.txt pytest
python -m src.cli sync --url <웹앱주소> --token <READ_TOKEN>   # 시트 → data/prices.csv → 빌드
python -m src.cli build                                         # data/prices.csv 로 site/ 빌드
python -m src.cli update --date 2026-10-05 SM_CFR_CN=1420       # CSV 에 직접 입력
python -m pytest tests -q
```

## 주의
- `data/prices.csv`(Platts 원본)는 `.gitignore` 로 레포에서 제외됩니다. 단, 배포되는 대시보드 페이지에는 차트용 최근 130봉 가격이 들어갑니다.
- 비밀번호·토큰은 코드에 넣지 않습니다(스크립트 속성, GitHub Secrets 에만).
- 주간 품목의 지표 기간·보합 폭 등 임계값은 검증하지 않은 가정입니다. 투자 판단의 근거로만 단독 사용하지 마세요.
