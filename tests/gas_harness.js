// Code.gs 검증용 하네스: 구글 서비스(SpreadsheetApp 등)를 흉내 낸 가짜 객체 위에서 Code.gs 를 실제로 실행합니다.
// 사용법: node tests/gas_harness.js  (표준 출력에 시나리오별 결과를 JSON 한 줄로 냅니다)
const fs = require('fs'); // 파일 읽기
const path = require('path'); // 경로 처리
const vm = require('vm'); // Code.gs 를 격리해서 실행

// ── 가짜 시트 ──────────────────────────────────────────────
function makeSheet(initial) { // initial: 2차원 배열(첫 행 헤더). 날짜 칸은 Date 객체 또는 글자
  const grid = initial.map(r => r.slice()); // 값 복사
  const formats = {}; // 서식 기록
  function range(r, c, nr, nc) { // Range 흉내
    nr = nr || 1; nc = nc || 1;
    return {
      getValues() { const out = []; for (let i = 0; i < nr; i++) { const row = []; for (let j = 0; j < nc; j++) row.push((grid[r - 1 + i] || [])[c - 1 + j] === undefined ? '' : grid[r - 1 + i][c - 1 + j]); out.push(row); } return out; },
      getValue() { const v = (grid[r - 1] || [])[c - 1]; return v === undefined ? '' : v; },
      setValue(v) { while (grid.length < r) grid.push([]); while (grid[r - 1].length < c) grid[r - 1].push(''); if (c === 1 && typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v)) v = new Date(v + 'T00:00:00Z'); grid[r - 1][c - 1] = v; return this; }, // 시트처럼 날짜 글자는 날짜로 변환
      setNumberFormat(f) { formats[r + ',' + c] = f; return this; },
    };
  }
  return {
    grid, formats,
    getDataRange() { const w = Math.max.apply(null, grid.map(r => r.length)); return { getValues: () => grid.map(r => { const x = r.slice(); while (x.length < w) x.push(''); return x; }) }; },
    getRange: range,
    getLastRow() { return grid.length; },
    insertRowBefore(n) { grid.splice(n - 1, 0, []); },
  };
}

function load(sheet, props, opts) { // Code.gs 를 가짜 서비스와 함께 불러오기
  opts = opts || {};
  const cacheStore = {}; // CacheService 저장소
  const calls = []; // UrlFetchApp 호출 기록
  const ctx = {
    Logger: { log() {} },
    PropertiesService: { getScriptProperties: () => ({ getProperty: k => (k in props ? props[k] : null) }) },
    CacheService: { getScriptCache: () => ({ get: k => (k in cacheStore ? cacheStore[k] : null), put: (k, v) => { cacheStore[k] = v; }, remove: k => { delete cacheStore[k]; } }) },
    LockService: { getScriptLock: () => ({ waitLock() {}, releaseLock() {} }) },
    ContentService: { MimeType: { JSON: 'json' }, createTextOutput: t => ({ text: t, setMimeType() { return this; } }) },
    SpreadsheetApp: { getActiveSpreadsheet: () => ({ getSheetByName: n => (n === 'prices' ? sheet : null), getSheets: () => [sheet], getSpreadsheetTimeZone: () => 'Asia/Seoul' }) },
    Utilities: { formatDate(d, tz, fmt) { // 'yyyy-MM-dd' 와 시각 형식만 흉내(하네스는 UTC 기준)
      const p = n => ('0' + n).slice(-2); const base = d.getUTCFullYear() + '-' + p(d.getUTCMonth() + 1) + '-' + p(d.getUTCDate());
      return fmt.indexOf('HH') >= 0 ? base + 'T' + p(d.getUTCHours()) + ':' + p(d.getUTCMinutes()) + ':' + p(d.getUTCSeconds()) : base; } },
    UrlFetchApp: { fetch(u, o) { calls.push({ url: u, options: o }); return { getResponseCode: () => (opts.fetchCode || 204) }; } },
  };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'apps_script', 'Code.gs'), 'utf8'), ctx, { filename: 'Code.gs' });
  const post = obj => JSON.parse(ctx.doPost({ postData: { contents: typeof obj === 'string' ? obj : JSON.stringify(obj) } }).text);
  const get = params => JSON.parse(ctx.doGet({ parameter: params }).text);
  return { ctx, post, get, calls, cacheStore };
}

const D = s => new Date(s + 'T00:00:00Z'); // 날짜 헬퍼
const baseGrid = () => [ // 헤더 + 3행(두 번째 코드는 주간 품목 흉내로 일부 비움)
  ['date', 'AAA', 'BBB'],
  [D('2026-09-21'), 100, ''],
  [D('2026-09-23'), 101, 50],
  [D('2026-09-25'), 102, ''],
];
const props = () => ({ ADMIN_PASSWORD: 'pw-1', READ_TOKEN: 'tok-1' });

const out = {}; // 시나리오 결과 모음

// 1) 데이터 읽기
{ const s = makeSheet(baseGrid()); const h = load(s, props());
  out.get_ok = h.get({ action: 'data', token: 'tok-1' });
  out.get_bad = h.get({ action: 'data', token: 'nope' });
  out.get_ping = h.get({ action: 'ping' });
  out.get_noaction = h.get({}); }

// 2) 최신가 조회
{ const s = makeSheet(baseGrid()); const h = load(s, props());
  out.latest = h.post({ action: 'latest', password: 'pw-1' }); }

// 3) 저장: 새 날짜(맨 아래), 중간 삽입, 덮어쓰기
{ const s = makeSheet(baseGrid()); const h = load(s, props());
  out.save_append = h.post({ action: 'save', password: 'pw-1', date: '2026-09-28', values: { AAA: '103.5', BBB: '' } });
  out.save_middle = h.post({ action: 'save', password: 'pw-1', date: '2026-09-22', values: { AAA: 100.5 } });
  out.save_update = h.post({ action: 'save', password: 'pw-1', date: '2026-09-23', values: { AAA: 101, BBB: '51' } });
  out.dates_after = s.grid.map(r => (r[0] instanceof Date ? r[0].toISOString().slice(0, 10) : r[0]));
  out.grid_after = s.grid.map(r => r.slice(1)); }

// 4) 검증 오류
{ const s = makeSheet(baseGrid()); const h = load(s, props());
  out.err_date = h.post({ action: 'save', password: 'pw-1', date: '어제', values: { AAA: 1 } });
  out.err_future = h.post({ action: 'save', password: 'pw-1', date: '2099-01-01', values: { AAA: 1 } });
  out.err_empty = h.post({ action: 'save', password: 'pw-1', date: '2026-09-28', values: { AAA: '' } });
  out.err_nan = h.post({ action: 'save', password: 'pw-1', date: '2026-09-28', values: { AAA: 'abc' } });
  out.err_zero = h.post({ action: 'save', password: 'pw-1', date: '2026-09-28', values: { AAA: 0 } });
  out.ok_negative = h.post({ action: 'save', password: 'pw-1', date: '2026-09-29', values: { AAA: -5 }, allowNonpositive: true, confirm: true });
  out.err_code = h.post({ action: 'save', password: 'pw-1', date: '2026-09-28', values: { ZZZ: 1 } });
  out.err_json = h.post('이건 JSON 이 아님');
  out.err_action = h.post({ action: 'drop', password: 'pw-1' }); }

// 5) 경고(급변동·주말) 확인 절차
{ const s = makeSheet(baseGrid()); const h = load(s, props());
  out.warn_big = h.post({ action: 'save', password: 'pw-1', date: '2026-09-28', values: { AAA: 200 } });
  out.warn_big_rows = s.grid.length; // 확인 전에는 저장되지 않아야 함
  out.warn_big_confirm = h.post({ action: 'save', password: 'pw-1', date: '2026-09-28', values: { AAA: 200 }, confirm: true });
  out.warn_weekend = h.post({ action: 'save', password: 'pw-1', date: '2026-09-26', values: { AAA: 102.5 } }); }

// 6) 비밀번호 차단
{ const s = makeSheet(baseGrid()); const h = load(s, props());
  out.pw_bad = []; for (let i = 0; i < 6; i++) out.pw_bad.push(h.post({ action: 'latest', password: 'wrong' }));
  out.pw_after_lock = h.post({ action: 'latest', password: 'pw-1' }); }
{ const s = makeSheet(baseGrid()); const h = load(s, props());
  h.post({ action: 'latest', password: 'wrong' }); out.pw_ok_resets = h.post({ action: 'latest', password: 'pw-1' }); out.pw_counter_after_ok = h.cacheStore.fails_password === undefined; }
{ const s = makeSheet(baseGrid()); const h = load(s, {}); out.not_configured = h.post({ action: 'latest', password: 'x' }); out.not_configured_get = h.get({ action: 'data', token: 'x' }); }

// 7) GitHub 재빌드 호출
{ const s = makeSheet(baseGrid()); const p = props(); p.GITHUB_TOKEN = 'ghp_x'; p.GITHUB_REPO = 'me/repo'; const h = load(s, p);
  out.rebuild = h.post({ action: 'save', password: 'pw-1', date: '2026-09-28', values: { AAA: 103 } }).rebuild;
  out.rebuild_call = h.calls.map(c => ({ url: c.url, method: c.options.method, auth: c.options.headers.Authorization, body: c.options.payload })); }
{ const s = makeSheet(baseGrid()); const p = props(); p.GITHUB_TOKEN = 'ghp_x'; p.GITHUB_REPO = 'me/repo'; const h = load(s, p, { fetchCode: 404 });
  out.rebuild_fail = h.post({ action: 'save', password: 'pw-1', date: '2026-09-28', values: { AAA: 103 } }).rebuild; }

// 8) 헤더 양식 오류, 글자 날짜·쉼표 숫자
{ const s = makeSheet([['x', 'AAA'], [D('2026-09-25'), 1]]); const h = load(s, props()); out.bad_header = h.get({ action: 'data', token: 'tok-1' }); }
{ const s = makeSheet([['date', 'AAA'], ['2026/10/01', '1,234.5'], ['2026-09-25', 1300]]); const h = load(s, props()); out.text_cells = h.get({ action: 'data', token: 'tok-1' }); }

// 9) setupCheck
{ const s = makeSheet(baseGrid()); const h = load(s, props()); out.setup_check = h.ctx.setupCheck(); }

console.log(JSON.stringify(out));
