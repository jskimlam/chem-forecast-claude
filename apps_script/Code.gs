/**
 * chem-forecast-claude 가격 시트 연동 (Google Apps Script)
 *
 * 사용법: 가격 시트에서 [확장 프로그램 > Apps Script] 를 열고 이 파일 내용을 통째로 붙여넣은 뒤 [배포 > 새 배포 > 웹 앱]으로 배포합니다.
 *   - 실행 사용자: 나(Execute as: Me)
 *   - 액세스 권한: 모든 사용자(Anyone)  ← 비밀번호·토큰이 없으면 아무것도 못 하므로 안전합니다.
 * 비밀번호와 토큰은 코드가 아니라 [프로젝트 설정 > 스크립트 속성]에 넣습니다. (레포가 공개라 코드에 적으면 안 됩니다)
 *   ADMIN_PASSWORD  : admin.html 에서 가격을 입력할 때 쓰는 비밀번호
 *   READ_TOKEN      : 대시보드 자동 빌드(GitHub Actions)가 시트를 읽을 때 쓰는 토큰(길고 무작위로)
 *   GITHUB_TOKEN    : (선택) 저장 직후 대시보드를 바로 다시 만들게 하는 GitHub 토큰(Actions 쓰기 권한)
 *   GITHUB_REPO     : (선택) 예) jskimlam/chem-forecast-claude
 *
 * 시트 양식: 첫 행은 헤더(A1 = date, B1부터 품목 코드), 둘째 행부터 날짜 오름차순 데이터.
 */

var SHEET_NAME = 'prices'; // 가격 데이터가 있는 탭 이름(이 이름이 없으면 첫 번째 탭을 사용)
var TZ = 'Asia/Seoul'; // 오늘 날짜를 판단할 때 쓰는 시간대
var BIG_MOVE = 0.25; // 직전 값 대비 이 비율을 넘게 변하면 경고(0.25 = 25%)
var MAX_FAILS = 5; // 비밀번호·토큰을 연속으로 틀릴 수 있는 횟수
var LOCK_SECONDS = 600; // 틀린 횟수를 넘으면 막아 두는 시간(초)
var WORKFLOW_FILE = 'build.yml'; // 저장 후 실행할 GitHub Actions 워크플로 파일 이름
var GIT_REF = 'main'; // 워크플로를 실행할 브랜치

/** 스크립트 속성 값을 읽는 함수 */
function prop_(name) {
  return PropertiesService.getScriptProperties().getProperty(name) || ''; // 값이 없으면 빈 문자열
}

/** JSON 응답을 만드는 함수 */
function jsonOut_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON); // JSON 문자열로 응답
}

/** 가격 시트(탭)를 찾는 함수 */
function getSheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet(); // 이 스크립트가 붙어 있는 스프레드시트
  return ss.getSheetByName(SHEET_NAME) || ss.getSheets()[0]; // 지정한 탭이 없으면 첫 번째 탭
}

/** 셀 값(날짜 또는 글자)을 'YYYY-MM-DD' 글자로 바꾸는 함수. 날짜로 읽을 수 없으면 빈 문자열 */
function dateText_(v) {
  if (Object.prototype.toString.call(v) === '[object Date]') { // 시트가 날짜로 저장한 경우
    if (isNaN(v.getTime())) return ''; // 잘못된 날짜
    return Utilities.formatDate(v, SpreadsheetApp.getActiveSpreadsheet().getSpreadsheetTimeZone(), 'yyyy-MM-dd'); // 시트 시간대 기준 글자로
  }
  var m = String(v === null || v === undefined ? '' : v).trim().replace(/[./]/g, '-').match(/^(\d{4})-(\d{1,2})-(\d{1,2})/); // 글자로 저장된 경우 형식 확인
  if (!m) return ''; // 형식이 다르면 빈 문자열
  var mm = ('0' + m[2]).slice(-2); // 월 두 자리
  var dd = ('0' + m[3]).slice(-2); // 일 두 자리
  return m[1] + '-' + mm + '-' + dd; // 표준 형식으로 반환
}

/** 셀 값을 숫자로 바꾸는 함수. 비었거나 숫자가 아니면 null */
function toNumber_(v) {
  if (v === '' || v === null || v === undefined) return null; // 빈 칸
  if (typeof v === 'number') return isFinite(v) ? v : null; // 이미 숫자
  var n = Number(String(v).replace(/,/g, '').trim()); // 쉼표를 없애고 숫자로 변환
  return isFinite(n) && String(v).trim() !== '' ? n : null; // 변환 실패면 null
}

/** 시트 전체를 읽어 헤더·날짜·가격 표로 만드는 함수 */
function readTable_(sheet) {
  var values = sheet.getDataRange().getValues(); // 시트의 모든 값
  if (!values.length || String(values[0][0]).trim().toLowerCase() !== 'date') { // A1이 date가 아니면
    throw new Error('시트 A1 칸이 date 가 아닙니다. 첫 행은 date, 품목 코드... 형식이어야 합니다.'); // 양식 오류 안내
  }
  var codes = []; // 품목 코드 목록
  var colOf = {}; // 코드 → 열 번호(1부터)
  for (var c = 1; c < values[0].length; c++) { // 헤더의 B열부터
    var code = String(values[0][c]).trim(); // 코드 글자
    if (code) { codes.push(code); colOf[code] = c + 1; } // 비어 있지 않으면 등록
  }
  var rows = []; // 데이터 행 목록
  for (var r = 1; r < values.length; r++) { // 둘째 행부터
    var d = dateText_(values[r][0]); // 날짜 글자
    if (!d) continue; // 날짜를 읽을 수 없는 행은 건너뜀
    var nums = codes.map(function (code2) { return toNumber_(values[r][colOf[code2] - 1]); }); // 코드 순서대로 숫자 추출
    rows.push({ rowNo: r + 1, date: d, nums: nums }); // 행 번호·날짜·숫자 저장
  }
  return { codes: codes, colOf: colOf, rows: rows, width: values[0].length }; // 읽은 결과 반환
}

/** 두 글자를 같은 시간에 비교하는 함수(비밀번호 비교 시 시간차 공격 방지) */
function safeEqual_(a, b) {
  a = String(a); b = String(b); // 글자로 통일
  var diff = a.length ^ b.length; // 길이 차이를 먼저 반영
  var n = Math.max(a.length, b.length); // 더 긴 쪽 길이
  for (var i = 0; i < n; i++) { // 모든 글자를 끝까지 비교
    diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0); // 다르면 diff가 0이 아니게 됨
  }
  return diff === 0; // 모두 같으면 true
}

/** 비밀번호·토큰을 검사하는 함수. 통과하면 null, 아니면 오류 응답 객체 */
function checkSecret_(kind, given, propName) {
  var cache = CacheService.getScriptCache(); // 실패 횟수 저장소
  var key = 'fails_' + kind; // 종류별 실패 횟수 키
  var fails = Number(cache.get(key) || 0); // 지금까지 틀린 횟수
  if (fails >= MAX_FAILS) { // 한도를 넘었으면
    return { ok: false, code: 'locked', error: '시도 횟수를 넘어 ' + Math.round(LOCK_SECONDS / 60) + '분간 막혔습니다. 잠시 후 다시 시도하세요.' }; // 차단 안내
  }
  var expected = prop_(propName); // 설정된 값
  if (!expected) { // 설정이 없으면
    return { ok: false, code: 'not_configured', error: '스크립트 속성에 ' + propName + ' 가 없습니다. 프로젝트 설정에서 추가하세요.' }; // 설정 안내
  }
  if (!safeEqual_(given || '', expected)) { // 값이 다르면
    cache.put(key, String(fails + 1), LOCK_SECONDS); // 실패 횟수 증가
    var left = MAX_FAILS - fails - 1; // 남은 시도 횟수
    return { ok: false, code: 'bad_secret', error: (kind === 'password' ? '비밀번호가' : '토큰이') + ' 맞지 않습니다. (남은 시도 ' + left + '회)' }; // 오류 안내
  }
  cache.remove(key); // 성공하면 실패 횟수 초기화
  return null; // 통과
}

/** GET 요청: 빌드용 전체 가격 데이터를 내려줍니다. ?action=data&token=READ_TOKEN */
function doGet(e) {
  try {
    var p = (e && e.parameter) || {}; // 요청 인자
    if (p.action === 'ping') return jsonOut_({ ok: true, message: 'chem-forecast-claude 시트 연동이 동작 중입니다.' }); // 연결 확인용(데이터 없음)
    if (p.action !== 'data') return jsonOut_({ ok: false, code: 'bad_request', error: 'action=data 또는 action=ping 이 필요합니다.' }); // 지원하지 않는 요청
    var bad = checkSecret_('token', p.token, 'READ_TOKEN'); // 토큰 검사
    if (bad) return jsonOut_(bad); // 실패하면 오류 응답
    var t = readTable_(getSheet_()); // 시트 읽기
    var rows = t.rows.map(function (r) { return [r.date].concat(r.nums); }); // [날짜, 값...] 형태로 변환
    return jsonOut_({ ok: true, codes: t.codes, rows: rows, updated: Utilities.formatDate(new Date(), TZ, "yyyy-MM-dd'T'HH:mm:ss"), n_rows: rows.length }); // 데이터 응답
  } catch (err) {
    return jsonOut_({ ok: false, code: 'error', error: String(err && err.message ? err.message : err) }); // 예상 못 한 오류도 JSON으로
  }
}

/** POST 요청: admin.html 에서 오는 최신 가격 조회(latest)와 저장(save) */
function doPost(e) {
  try {
    var body; // 요청 본문
    try { body = JSON.parse(e.postData.contents); } catch (x) { return jsonOut_({ ok: false, code: 'bad_request', error: '요청 형식이 올바르지 않습니다.' }); } // JSON 해석
    var bad = checkSecret_('password', body.password, 'ADMIN_PASSWORD'); // 비밀번호 검사
    if (bad) return jsonOut_(bad); // 실패하면 오류 응답
    if (body.action === 'latest') return jsonOut_(handleLatest_()); // 품목별 마지막 가격 조회
    if (body.action === 'save') return jsonOut_(handleSave_(body)); // 가격 저장
    return jsonOut_({ ok: false, code: 'bad_request', error: '알 수 없는 요청입니다.' }); // 지원하지 않는 요청
  } catch (err) {
    return jsonOut_({ ok: false, code: 'error', error: String(err && err.message ? err.message : err) }); // 예상 못 한 오류도 JSON으로
  }
}

/** 품목별 마지막 가격·날짜를 돌려주는 함수 */
function handleLatest_() {
  var t = readTable_(getSheet_()); // 시트 읽기
  var last = {}; // 코드 → {date, price}
  t.codes.forEach(function (code, i) { // 품목마다
    for (var k = t.rows.length - 1; k >= 0; k--) { // 아래(최신)부터 거슬러 올라가며
      if (t.rows[k].nums[i] !== null) { last[code] = { date: t.rows[k].date, price: t.rows[k].nums[i] }; break; } // 값이 있는 첫 행을 저장
    }
  });
  return { ok: true, codes: t.codes, last: last, today: Utilities.formatDate(new Date(), TZ, 'yyyy-MM-dd') }; // 결과 반환
}

/** 가격을 저장하는 함수. body = {date, values:{코드:가격}, confirm, allowNonpositive} */
function handleSave_(body) {
  var date = dateText_(body.date); // 날짜 확인
  if (!date) return { ok: false, code: 'bad_date', error: '날짜를 YYYY-MM-DD 형식으로 써 주세요.' }; // 날짜 오류
  var today = Utilities.formatDate(new Date(), TZ, 'yyyy-MM-dd'); // 오늘(한국 시간)
  var limit = new Date(); limit.setDate(limit.getDate() + 1); // 내일까지는 허용
  if (date > Utilities.formatDate(limit, TZ, 'yyyy-MM-dd')) return { ok: false, code: 'future_date', error: date + ' 는 미래 날짜입니다. 날짜를 확인하세요.' }; // 미래 날짜 거부
  var input = body.values || {}; // 입력된 가격들
  var lock = LockService.getScriptLock(); // 동시에 저장하는 경우를 막는 잠금
  lock.waitLock(20000); // 최대 20초 기다림
  try {
    var sheet = getSheet_(); // 시트
    var t = readTable_(sheet); // 현재 시트 내용
    var picked = {}; // 저장할 {코드: 숫자}
    var errors = []; // 입력 오류 목록
    Object.keys(input).forEach(function (code) { // 입력한 코드마다
      var raw = input[code]; // 입력값
      if (raw === '' || raw === null || raw === undefined) return; // 빈 칸은 건너뜀
      if (!t.colOf[code]) { errors.push(code + ': 시트 헤더에 없는 코드입니다.'); return; } // 모르는 코드
      var n = toNumber_(raw); // 숫자로 변환
      if (n === null) { errors.push(code + ': 가격 "' + raw + '" 를 숫자로 읽을 수 없습니다.'); return; } // 숫자 아님
      if (n <= 0 && !body.allowNonpositive) { errors.push(code + ': 가격 ' + n + ' 은 0 이하입니다.'); return; } // 0 이하
      picked[code] = n; // 통과한 값 저장
    });
    if (errors.length) return { ok: false, code: 'bad_value', error: errors.join(' / ') }; // 입력 오류가 있으면 저장하지 않음
    var codes = Object.keys(picked); // 저장할 코드 목록
    if (!codes.length) return { ok: false, code: 'empty', error: '입력된 가격이 없습니다.' }; // 입력이 하나도 없음
    var warnings = []; // 경고 목록
    var dow = new Date(date + 'T00:00:00Z').getUTCDay(); // 요일(0=일, 6=토)
    if (dow === 0 || dow === 6) warnings.push(date + ' 는 주말입니다. 날짜가 맞는지 확인하세요.'); // 주말 경고
    codes.forEach(function (code) { // 품목마다 직전 값과 비교
      var idx = t.codes.indexOf(code); // 코드 순번
      var prev = null; // 입력일 이전의 마지막 값
      for (var k = 0; k < t.rows.length; k++) { // 시트의 모든 행을 보며
        if (t.rows[k].date < date && t.rows[k].nums[idx] !== null) prev = t.rows[k].nums[idx]; // 날짜가 더 이른 값 중 가장 늦은 것
      }
      if (prev !== null && prev > 0) { // 비교할 값이 있으면
        var chg = picked[code] / prev - 1; // 변화율
        if (Math.abs(chg) > BIG_MOVE) warnings.push(code + ': 직전 ' + prev + ' → ' + picked[code] + ' (' + (chg * 100 >= 0 ? '+' : '') + (chg * 100).toFixed(1) + '%) 급변동입니다.'); // 급변동 경고
      }
    });
    if (warnings.length && !body.confirm) return { ok: false, code: 'confirm_required', needConfirm: true, warnings: warnings, error: '경고를 확인하고 다시 저장하세요.' }; // 확인 전에는 저장하지 않음
    var rowNo = 0; // 저장할 행 번호
    for (var i = 0; i < t.rows.length; i++) { // 같은 날짜 행이 있는지 찾기
      if (t.rows[i].date === date) { rowNo = t.rows[i].rowNo; break; } // 있으면 그 행에 덮어씀
    }
    if (!rowNo) { // 새 날짜이면
      var before = 0; // 새 행을 넣을 위치(이 행 앞)
      for (var j = 0; j < t.rows.length; j++) { // 날짜가 더 늦은 첫 행을 찾음
        if (t.rows[j].date > date) { before = t.rows[j].rowNo; break; } // 찾으면 그 앞에 삽입
      }
      if (before) { sheet.insertRowBefore(before); rowNo = before; } // 중간에 끼워 넣기
      else { rowNo = sheet.getLastRow() + 1; } // 가장 최신이면 맨 아래에 추가
      sheet.getRange(rowNo, 1).setNumberFormat('yyyy-mm-dd'); // 날짜 칸 형식
      sheet.getRange(rowNo, 1).setValue(date); // 날짜 입력
    }
    var added = []; // 새로 채운 품목
    var updated = []; // 값을 바꾼 품목
    codes.forEach(function (code) { // 품목마다 저장
      var cell = sheet.getRange(rowNo, t.colOf[code]); // 저장할 칸
      var old = toNumber_(cell.getValue()); // 기존 값
      if (old === null) added.push({ code: code, price: picked[code] }); // 비어 있었으면 추가
      else if (old !== picked[code]) updated.push({ code: code, old: old, price: picked[code] }); // 값이 달라지면 수정
      cell.setValue(picked[code]); // 값 입력
    });
    var trig = triggerBuild_(); // 저장 후 대시보드 재빌드 요청(설정된 경우)
    return { ok: true, date: date, added: added, updated: updated, warnings: warnings, rebuild: trig, today: today }; // 저장 결과
  } finally {
    lock.releaseLock(); // 잠금 해제
  }
}

/** GitHub Actions 워크플로를 실행시켜 대시보드를 바로 다시 만들게 하는 함수(선택 기능) */
function triggerBuild_() {
  var token = prop_('GITHUB_TOKEN'); // GitHub 토큰
  var repo = prop_('GITHUB_REPO'); // 레포 이름(소유자/이름)
  if (!token || !repo) return 'skipped'; // 설정이 없으면 건너뜀(평일 아침 자동 빌드만 동작)
  try {
    var res = UrlFetchApp.fetch('https://api.github.com/repos/' + repo + '/actions/workflows/' + WORKFLOW_FILE + '/dispatches', { // 워크플로 실행 요청
      method: 'post', // POST
      contentType: 'application/json', // JSON 본문
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' }, // 인증 헤더
      payload: JSON.stringify({ ref: GIT_REF }), // 실행할 브랜치
      muteHttpExceptions: true // 실패해도 예외를 던지지 않음
    });
    return res.getResponseCode() === 204 ? 'started' : 'failed:' + res.getResponseCode(); // 204면 성공
  } catch (err) {
    return 'failed'; // 통신 오류
  }
}

/** 설정이 제대로 됐는지 편집기에서 직접 실행해 보는 점검 함수([실행] 버튼) */
function setupCheck() {
  var report = []; // 점검 결과 목록
  ['ADMIN_PASSWORD', 'READ_TOKEN'].forEach(function (k) { // 필수 속성
    report.push((prop_(k) ? '[OK] ' : '[없음] ') + k); // 있는지 표시(값은 출력하지 않음)
  });
  ['GITHUB_TOKEN', 'GITHUB_REPO'].forEach(function (k) { // 선택 속성
    report.push((prop_(k) ? '[OK] ' : '[선택·없음] ') + k); // 있는지 표시
  });
  try {
    var t = readTable_(getSheet_()); // 시트 읽기 시도
    report.push('[OK] 시트 읽기: 품목 ' + t.codes.length + '개, 데이터 ' + t.rows.length + '행'); // 읽은 규모
    if (t.rows.length) report.push('[OK] 마지막 날짜: ' + t.rows[t.rows.length - 1].date); // 마지막 날짜
  } catch (err) {
    report.push('[오류] ' + err.message); // 시트 양식 오류
  }
  Logger.log(report.join('\n')); // 실행 로그에 출력
  return report.join('\n'); // 결과 반환
}
