/* ============================================================
   바로그 블로그 글 만들기 — 화면 로직 (3단계)

   - 기준정보·키워드·제목·본문: 서버(FastAPI)를 부른다
   - API 키는 서버 환경변수에만 있다. 이 파일에는 키가 없다.
   - 의료법 검사: 서버가 금지어 사전 + 문맥 판정으로 본다
   ============================================================ */

'use strict';

// ─────────────────────────── 서버 주소 ───────────────────────────

// 로컬에서 화면을 띄웠을 때는 내 컴퓨터의 서버를, 배포된 화면에서는 Render 서버를 부른다.
const IS_LOCAL = ['localhost', '127.0.0.1'].includes(location.hostname);
const API_BASE = IS_LOCAL
  ? 'http://127.0.0.1:8001'
  : 'https://barog-blog-generator-api.onrender.com';

// ─────────────────────────── 저장 키 ───────────────────────────

const KEY_DRAFT_STATE = 'barog.draft';       // 작성 중이던 입력 (새로고침 대비)
const KEY_LAST_SETTING = 'barog.lastSetting'; // 직전 설정 불러오기
const KEY_HISTORY = 'barog.history';         // 이력 (6단계에서 서버 저장으로 교체)
const KEY_TOKEN = 'barog.token';             // 로그인 토큰 (30일)

// ─────────────────────────── 글 목적 (모드) ───────────────────────────

// SPEC §5.6. 이 선택이 입력 항목 구성과 서버 프롬프트를 바꾼다.
const MODES = [
  {
    id: 'information',
    name: '정보성',
    description: '시술 원리·관리법 설명',
    note: '가격·이벤트·예약 유도가 들어가지 않아요. 자사 홈페이지나 해외 사이트, AI 검색에 걸리게 하는 글이에요.',
  },
  {
    id: 'promotion',
    name: '홍보성',
    description: '이벤트·가격 안내 포함',
    note: '이벤트와 예약 안내를 넣을 수 있어요. 국내 네이버 블로그용이에요.',
  },
];

// ─────────────────────────── 상태 ───────────────────────────

let config = null;

const state = {
  mode: 'information',
  branch: null,
  category: null,
  procedure: null,
  persona: null,
  personaCustom: '',
  audience: null,
  tone: null,
  platform: null,
  length: null,
  cta: '',
  reference: '',
  keywords: [],        // 선택한 키워드 text 배열
  keywordPool: [],     // 화면에 보여줄 키워드 후보
  titlePool: [],
  title: '',
  draft: null,         // {sections:[{heading, body}], hashtags:[], meta_description}
  issues: [],
  contextChecked: true,  // 2차(문맥) 검사가 돌았는지
};

// ─────────────────────────── 도우미 ───────────────────────────

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function announce(message) {
  $('#announcer').textContent = message;
}

let toastTimer = null;
function toast(message) {
  const el = $('#toast');
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 2200);
  announce(message);
}

function showLoading(text) {
  $('#loading-text').textContent = text;
  $('#loading').hidden = false;
  announce(text);
}
function hideLoading() {
  $('#loading').hidden = true;
}

function saveLocal(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* 저장 공간이 없으면 그냥 넘어간다 */ }
}
function readLocal(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (e) { return fallback; }
}

function saveDraftState() {
  saveLocal(KEY_DRAFT_STATE, state);
}

// ─────────────────────────── 기준정보 읽기 ───────────────────────────

/**
 * 3단계에서 이 함수만 GET /api/config 호출로 바꾼다.
 * 응답 모양(branches/procedures/personas/audiences/tones/platforms/lengths)은 서버가 정한다.
 */

// ─────────────────────────── 서버 호출 ───────────────────────────

/** 로그인 토큰. 없으면 빈 문자열. */
function getToken() {
  return readLocal(KEY_TOKEN, '') || '';
}

/** 토큰이 만료·무효라서 다시 로그인해야 하는 상황. */
class NeedsLogin extends Error {}

/**
 * 서버를 부른다. 실패하면 화면에 그대로 보여줄 한국어 문장을 담아 던진다.
 * 서버가 내려주는 message 를 우선 쓰고, 없을 때만 기본 문장을 쓴다.
 */
async function api(path, body) {
  const headers = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    // 네트워크가 끊겼거나 서버가 자고 있는 경우
    throw new Error('서버에 연결하지 못했어요. 인터넷 연결을 확인하고 다시 눌러볼까요?');
  }

  if (res.status === 401) {
    saveLocal(KEY_TOKEN, '');
    throw new NeedsLogin('로그인이 만료됐어요. 비밀번호를 다시 입력해 주세요.');
  }

  let data = null;
  try { data = await res.json(); } catch (e) { data = null; }

  if (!res.ok) {
    throw new Error((data && data.message) || '잠시 문제가 생겼어요. 다시 눌러볼까요?');
  }
  return data;
}

/** 무료 플랜은 한동안 요청이 없으면 잠든다. 첫 화면에서 미리 깨워둔다. */
async function wakeServer() {
  try {
    await fetch(`${API_BASE}/api/health`, { method: 'GET' });
  } catch (e) {
    // 깨우기는 실패해도 그냥 넘어간다. 실제 요청에서 다시 안내한다.
  }
}

async function loadConfig() {
  const result = await api('/api/config');

  // active: false 인 항목은 서버가 이미 걸러서 내려준다. 혹시 몰라 한 번 더 거른다.
  const onlyActive = (list) => (list || []).filter((item) => item.active !== false);
  result.branches = onlyActive(result.branches);
  result.personas = onlyActive(result.personas);
  result.audiences = onlyActive(result.audiences);
  result.tones = onlyActive(result.tones);
  result.procedures = onlyActive(result.procedures).map((cat) => ({
    ...cat,
    items: onlyActive(cat.items),
  }));

  return result;
}

/** 여러 카테고리에 같은 이름으로 들어 있는 시술 (검색 결과에서 카테고리를 함께 보여주기 위함) */
function findDuplicateNames(procedures) {
  const seen = new Map();
  procedures.forEach((cat) => cat.items.forEach((item) => {
    seen.set(item.name, (seen.get(item.name) || 0) + 1);
  }));
  return new Set(Array.from(seen.entries()).filter(([, n]) => n > 1).map(([name]) => name));
}

let duplicateNames = new Set();

// ─────────────────────────── 화면 전환 ───────────────────────────

const SCREENS = ['input', 'keywords', 'titles', 'result', 'history'];

function goTo(name) {
  SCREENS.forEach((s) => { $(`#screen-${s}`).hidden = (s !== name); });
  $$('.tab').forEach((tab) => {
    const isActive = (tab.dataset.tab === 'history') === (name === 'history');
    tab.classList.toggle('is-active', isActive);
    tab.setAttribute('aria-selected', String(isActive));
  });
  window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
  if (name === 'history') renderHistory();
}

// ─────────────────────────── 칩 그리기 ───────────────────────────

/**
 * 단일 선택 칩 묶음을 그린다.
 * @param {string} selector  담을 요소
 * @param {Array}  items     {id, name, description}
 * @param {string} stateKey  state 의 어느 값에 넣을지
 * @param {Function} [onPick] 선택 후 추가로 할 일
 */
function renderChipGroup(selector, items, stateKey, onPick) {
  const box = $(selector);
  box.innerHTML = '';

  items.forEach((item) => {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'chip';
    chip.setAttribute('aria-pressed', String(state[stateKey] === item.id));
    chip.dataset.id = item.id;

    const label = document.createElement('span');
    label.textContent = item.name;
    chip.appendChild(label);

    if (item.description) {
      const note = document.createElement('span');
      note.className = 'chip-note';
      note.textContent = item.description;
      chip.appendChild(note);
    }

    chip.addEventListener('click', () => {
      // 글 목적은 해제할 수 없다. 항상 둘 중 하나가 선택돼 있어야 한다.
      const canClear = stateKey !== 'mode';
      state[stateKey] = (canClear && state[stateKey] === item.id) ? null : item.id;
      Array.from(box.children).forEach((c) => {
        c.setAttribute('aria-pressed', String(c.dataset.id === state[stateKey]));
      });
      if (onPick) onPick(state[stateKey]);
      saveDraftState();
      updateSummary();
      validateInput();
    });

    box.appendChild(chip);
  });
}

// ─────────────────────────── 시술 선택 (2단계 + 검색) ───────────────────────────

function renderProcedureCategories() {
  const box = $('#proc-categories');
  box.innerHTML = '';

  config.procedures.forEach((cat) => {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'chip';
    chip.dataset.id = cat.id;
    chip.setAttribute('aria-pressed', String(state.category === cat.id));
    chip.innerHTML = `${escapeHtml(cat.name)}<span class="chip-cat-count">${cat.items.length}</span>`;

    chip.addEventListener('click', () => {
      state.category = cat.id;
      $('#proc-search').value = '';
      $('#proc-search-clear').hidden = true;
      Array.from(box.children).forEach((c) => {
        c.setAttribute('aria-pressed', String(c.dataset.id === state.category));
      });
      renderProcedureItems();
      saveDraftState();
    });

    box.appendChild(chip);
  });
}

/** 검색어가 있으면 전체에서 찾고, 없으면 선택한 카테고리 안에서만 보여준다. */
function renderProcedureItems() {
  const box = $('#proc-items');
  const query = $('#proc-search').value.trim().toLowerCase();
  box.innerHTML = '';

  let list = [];
  if (query) {
    config.procedures.forEach((cat) => cat.items.forEach((item) => {
      const haystack = [item.name].concat(item.aliases || []).join(' ').toLowerCase();
      if (haystack.includes(query)) list.push({ item, cat });
    }));
  } else if (state.category) {
    const cat = config.procedures.find((c) => c.id === state.category);
    if (cat) list = cat.items.map((item) => ({ item, cat }));
  }

  $('#proc-empty').hidden = !(query && list.length === 0);

  if (!query && !state.category) {
    box.innerHTML = '<p class="empty-line">위에서 카테고리를 고르거나 시술 이름을 검색해 주세요.</p>';
    return;
  }

  list.forEach(({ item, cat }) => {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'chip' + (item.signature ? ' chip-signature' : '');
    chip.dataset.id = item.id;
    chip.setAttribute('aria-pressed', String(state.procedure === item.id));

    const label = document.createElement('span');
    label.textContent = item.name;
    chip.appendChild(label);

    // 검색 중이거나 두 카테고리에 겹쳐 있는 시술은 카테고리를 함께 보여준다
    if (query || duplicateNames.has(item.name)) {
      const note = document.createElement('span');
      note.className = 'chip-note';
      note.textContent = cat.name;
      chip.appendChild(note);
    }

    chip.addEventListener('click', () => {
      state.procedure = item.id;
      state.category = cat.id;
      Array.from(box.children).forEach((c) => {
        c.setAttribute('aria-pressed', String(c.dataset.id === state.procedure));
      });
      Array.from($('#proc-categories').children).forEach((c) => {
        c.setAttribute('aria-pressed', String(c.dataset.id === state.category));
      });
      saveDraftState();
      updateSummary();
      updateDuplicateBanner();
      validateInput();
    });

    box.appendChild(chip);
  });
}

// ─────────────────────────── 요약 · 검증 ───────────────────────────

function findName(list, id) {
  const found = (list || []).find((x) => x.id === id);
  return found ? found.name : null;
}

function findProcedure(id) {
  for (const cat of config.procedures) {
    const item = cat.items.find((x) => x.id === id);
    if (item) return { item, cat };
  }
  return null;
}

function updateSummary() {
  const picked = [];
  if (state.branch) picked.push(findName(config.branches, state.branch));
  const proc = state.procedure ? findProcedure(state.procedure) : null;
  if (proc) picked.push(proc.item.name);
  if (state.persona) picked.push(findName(config.personas, state.persona));
  if (state.audience) picked.push(findName(config.audiences, state.audience));
  if (state.tone) picked.push(findName(config.tones, state.tone));
  if (state.platform) picked.push(findName(config.platforms, state.platform));
  if (state.length) picked.push(findName(config.lengths, state.length));

  const bar = $('#summary-bar');
  bar.hidden = picked.length === 0;
  $('#summary-chips').innerHTML = picked
    .map((text) => `<span class="summary-chip">${escapeHtml(text)}</span>`)
    .join('');
}

function validateInput() {
  const needCustom = state.persona === 'custom' && !state.personaCustom.trim();
  const ready = Boolean(
    state.mode && state.branch && state.procedure && state.persona &&
    state.audience && state.tone && state.platform && state.length
  ) && !needCustom;

  $('#btn-to-keywords').disabled = !ready;
  $('#input-hint').textContent = ready
    ? '준비됐어요'
    : (needCustom ? '어떤 시점으로 쓸지 적어주세요' : '필수 항목을 모두 골라주세요');
  return ready;
}

/** 후기형 페르소나 경고 · 직접 입력 칸 */
function onPersonaPicked(id) {
  const persona = (config.personas || []).find((p) => p.id === id);
  const warnBox = $('#persona-warning');
  if (persona && persona.warning) {
    warnBox.textContent = persona.warning;
    warnBox.hidden = false;
  } else {
    warnBox.hidden = true;
  }
  $('#persona-custom').hidden = !(persona && persona.custom_input);
}

/** 30일 안에 같은 지점 + 시술로 쓴 글이 있으면 알려준다 */
function updateDuplicateBanner() {
  const banner = $('#dup-banner');
  if (!state.branch || !state.procedure) { banner.hidden = true; return; }

  const limit = Date.now() - 30 * 24 * 60 * 60 * 1000;
  const recent = readLocal(KEY_HISTORY, []).filter((row) =>
    row.branch === state.branch && row.procedure === state.procedure && row.createdAt >= limit
  );

  if (recent.length === 0) { banner.hidden = true; return; }
  const proc = findProcedure(state.procedure);
  banner.textContent =
    `최근 30일 안에 ${findName(config.branches, state.branch)} · ${proc ? proc.item.name : ''} 글이 ` +
    `${recent.length}건 있어요. 같은 내용이 겹치지 않게 각도를 바꿔보세요.`;
  banner.hidden = false;
}

/** 서버로 보낼 입력 묶음. id 만 보내고 이름 변환은 서버가 한다. */
function requestPayload() {
  return {
    mode: state.mode,
    lang: 'ko',
    branch: state.branch || '',
    procedure: state.procedure || '',
    persona: state.persona || '',
    persona_custom: state.personaCustom || '',
    audience: state.audience || '',
    tone: state.tone || '',
    platform: state.platform || '',
    length: state.length || 'medium',
    reference: state.reference || '',
    // 정보성 모드에서는 보내지 않는다. 서버도 한 번 더 비운다.
    cta: state.mode === 'information' ? '' : (state.cta || ''),
  };
}

/**
 * 생성 요청을 감싼다. 실패하면 한국어 안내를 띄우고 false 를 돌려준다.
 * 토큰이 만료됐으면 잠금 화면으로 되돌린다.
 */
async function runStep(steps, work) {
  const timers = [];
  showLoading(steps[0]);
  steps.slice(1).forEach((text, i) => {
    timers.push(setTimeout(() => showLoading(text), (i + 1) * 7000));
  });

  try {
    return await work();
  } catch (err) {
    if (err instanceof NeedsLogin) {
      lock(err.message);
      return null;
    }
    toast(err.message);
    return null;
  } finally {
    timers.forEach(clearTimeout);
    hideLoading();
  }
}

/** 서버는 해시태그를 # 없이 단어만 준다. 붙여넣을 때 쓰기 좋게 # 을 붙인다. */
function formatHashtags(tags) {
  return (tags || [])
    .map((t) => '#' + String(t).replace(/^#/, '').replace(/\s+/g, ''))
    .join(' ');
}

/** 검사에 보낼 본문 전체. 소제목도 함께 본다(소제목에도 금지 표현이 들어간다). */
function draftText() {
  if (!state.draft) return '';
  return state.draft.sections
    .map((s) => (s.heading ? s.heading + '\n' : '') + s.body)
    .join('\n\n');
}

/**
 * 의료법 검사를 돌린다.
 * quick=true 면 금지어 사전만 본다(문구를 바꾼 뒤 즉시 재확인용).
 * 실패해도 화면은 살려두되, 검사를 못 했다는 사실은 숨기지 않는다.
 */
async function runCompliance(quick) {
  const text = draftText();
  if (!text.trim()) return;

  try {
    const data = await api('/api/compliance', {
      text,
      mode: state.mode,
      lang: 'ko',
      quick: Boolean(quick),
    });
    state.issues = data.issues;
    state.contextChecked = data.context_checked;
  } catch (err) {
    if (err instanceof NeedsLogin) { lock(err.message); return; }
    // 검사를 못 했으면 통과한 것처럼 보이면 안 된다. 복사를 막고 다시 시도하게 한다.
    state.issues = [{
      level: 'danger',
      phrase: '',
      reason: '표현 검사를 하지 못했어요. 다시 검사해 주세요.',
      suggestion: '',
      source: 'error',
    }];
    state.contextChecked = false;
    toast(err.message);
  }
}

function currentContext() {
  const proc = findProcedure(state.procedure);
  return {
    branchName: findName(config.branches, state.branch) || '',
    procedureName: proc ? proc.item.name : '',
    categoryName: proc ? proc.cat.name : '',
    personaName: findName(config.personas, state.persona) || '',
    audienceName: findName(config.audiences, state.audience) || '',
    toneName: findName(config.tones, state.tone) || '',
    platformName: findName(config.platforms, state.platform) || '',
    lengthName: findName(config.lengths, state.length) || '',
    keywords: state.keywords,
    cta: state.cta,
  };
}

// ─────────────────────────── [2] 키워드 화면 ───────────────────────────

function renderKeywordCards() {
  const box = $('#keyword-cards');
  box.innerHTML = '';

  state.keywordPool.forEach((kw) => {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'card';
    card.setAttribute('aria-pressed', String(state.keywords.includes(kw.text)));
    card.innerHTML =
      `<span class="card-text">${escapeHtml(kw.text)}</span>` +
      `<span class="card-tag">${escapeHtml(kw.intent)}</span>`;

    card.addEventListener('click', () => {
      const picked = state.keywords.includes(kw.text);
      if (picked) {
        state.keywords = state.keywords.filter((t) => t !== kw.text);
      } else {
        if (state.keywords.length >= 5) { toast('키워드는 5개까지 고를 수 있어요'); return; }
        state.keywords.push(kw.text);
      }
      card.setAttribute('aria-pressed', String(!picked));
      saveDraftState();
      updateKeywordHint();
    });

    box.appendChild(card);
  });
}

function updateKeywordHint() {
  const n = state.keywords.length;
  const ready = n >= 3 && n <= 5;
  $('#btn-to-titles').disabled = !ready;
  $('#keyword-hint').textContent = ready
    ? `${n}개 선택됨`
    : `${n}개 선택됨 · 3개 이상 골라주세요`;
}

// ─────────────────────────── [3] 제목 화면 ───────────────────────────

function renderTitleCards() {
  const box = $('#title-cards');
  box.innerHTML = '';

  state.titlePool.forEach((t) => {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'card card-full';
    card.setAttribute('aria-pressed', String(state.title === t.text));
    card.innerHTML =
      `<span class="card-text">${escapeHtml(t.text)}</span>` +
      `<span class="card-note">${t.text.length}자 · ${escapeHtml(t.hook_type || t.hook || '')}</span>`;

    card.addEventListener('click', () => {
      state.title = t.text;
      Array.from(box.children).forEach((c, i) => {
        c.setAttribute('aria-pressed', String(state.titlePool[i].text === state.title));
      });
      $('#title-edit-wrap').hidden = false;
      $('#title-edit').value = state.title;
      $('#title-count').textContent = String(state.title.length);
      $('#btn-to-result').disabled = false;
      saveDraftState();
    });

    box.appendChild(card);
  });
}

// ─────────────────────────── [4] 결과 화면 ───────────────────────────

function renderResult() {
  const ctx = currentContext();

  $('#result-title').textContent = state.title;
  $('#result-meta-text').textContent =
    [ctx.branchName, ctx.procedureName, ctx.personaName, ctx.platformName, ctx.lengthName]
      .filter(Boolean).join(' · ');

  const box = $('#result-sections');
  box.innerHTML = '';

  state.draft.sections.forEach((section, index) => {
    const block = document.createElement('section');
    block.className = 'section-block';

    const heading = document.createElement('h2');
    heading.className = 'section-heading';
    heading.textContent = section.heading;

    const body = document.createElement('div');
    body.className = 'section-body';
    body.innerHTML = highlightIssues(section.body);

    const redo = document.createElement('button');
    redo.type = 'button';
    redo.className = 'btn btn-secondary btn-sm section-redo';
    redo.textContent = '이 부분만 다시';
    redo.addEventListener('click', async () => {
      const data = await runStep(
        ['이 부분을 다시 쓰고 있어요…'],
        () => api('/api/draft/section', {
          ...requestPayload(),
          selected_keywords: state.keywords,
          title: state.title,
          heading: section.heading || '',
          body: section.body,
          instruction: '',
        }),
      );
      if (!data) return;

      section.heading = data.heading;
      section.body = data.body;

      // 다시 쓴 문단에 새 위험이 들어갔을 수 있다. 반드시 다시 검사한다.
      showLoading('다시 살펴보고 있어요…');
      await runCompliance(false);
      hideLoading();

      renderResult();
      saveDraftState();
      toast('문단을 다시 썼어요');
    });

    block.append(heading, body, redo);
    box.appendChild(block);
  });

  const tags = $('#result-hashtags');
  if (state.platform === 'naver' || state.platform === 'sns') {
    tags.textContent = formatHashtags(state.draft.hashtags);
    tags.hidden = false;
  } else {
    tags.hidden = true;
  }

  renderCompliance();
  renderFormatOptions();
}

/** 검사에서 잡힌 표현에 표시를 남긴다 */
function highlightIssues(text) {
  let html = escapeHtml(text);
  state.issues.forEach((issue) => {
    if (issue.resolved || issue.level === 'info') return;
    if (!issue.phrase) return;   // 검사 실패 항목은 본문에 표시할 게 없다
    const safe = escapeHtml(issue.phrase);
    if (!html.includes(safe)) return;
    const cls = issue.level === 'warn' ? ' class="is-warn"' : '';
    html = html.split(safe).join(`<mark${cls}>${safe}</mark>`);
  });
  return html;
}

/** 본문 전체에서 한 표현을 바꾼다. 소제목도 함께 본다. */
function replacePhrase(phrase, replacement) {
  if (!phrase || !state.draft) return;
  state.draft.sections.forEach((sec) => {
    sec.heading = sec.heading.split(phrase).join(replacement);
    sec.body = sec.body.split(phrase).join(replacement);
  });
}

/** 지적된 표현이 들어 있는 문단을 통째로 다시 쓴다. */
async function rewriteSectionFor(issue) {
  const index = state.draft.sections.findIndex(
    (sec) => sec.heading.includes(issue.phrase) || sec.body.includes(issue.phrase)
  );
  if (index < 0) { toast('그 표현을 본문에서 찾지 못했어요'); return; }

  const target = state.draft.sections[index];
  const data = await runStep(
    ['이 문단을 다시 쓰고 있어요…'],
    () => api('/api/draft/section', {
      ...requestPayload(),
      selected_keywords: state.keywords,
      title: state.title,
      heading: target.heading || '',
      body: target.body,
      instruction: `'${issue.phrase}' 라는 표현과 그 내용을 완전히 빼고 다시 써라. ${issue.reason}`,
    }),
  );
  if (!data) return;

  target.heading = data.heading;
  target.body = data.body;

  showLoading('다시 살펴보고 있어요…');
  await runCompliance(false);
  hideLoading();

  renderResult();
  saveDraftState();
  toast('문단을 다시 썼어요');
}

function renderCompliance() {
  const list = $('#compliance-list');
  const badge = $('#compliance-badge');
  list.innerHTML = '';

  const open = state.issues.filter((i) => !i.resolved);
  const danger = open.filter((i) => i.level === 'danger');

  if (open.length === 0) {
    list.innerHTML = '<p class="issue-empty">걸리는 표현이 없어요. 복사해서 쓰셔도 됩니다.</p>';
  }

  open.forEach((issue) => {
    const el = document.createElement('div');
    el.className = 'issue';

    const levelText = { danger: '● 위험', warn: '● 주의', info: '● 참고' }[issue.level];
    const levelClass = { danger: 'level-danger', warn: 'level-warn', info: 'level-info' }[issue.level];

    el.innerHTML =
      `<div class="issue-head">` +
        `<span class="issue-level ${levelClass}">${levelText}</span>` +
        `<span class="issue-phrase">${escapeHtml(issue.phrase)}</span>` +
      `</div>` +
      `<p class="issue-reason">${escapeHtml(issue.reason)}</p>`;

    const fix = document.createElement('div');
    fix.className = 'issue-fix';

    if (issue.suggestion) {
      fix.innerHTML = `<span class="issue-fix-text">→ ${escapeHtml(issue.suggestion)}</span>`;

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-secondary btn-sm';
      btn.textContent = '이 문구로 바꾸기';
      btn.addEventListener('click', async () => {
        replacePhrase(issue.phrase, issue.suggestion);
        // 바꾼 뒤 곧바로 다시 검사한다. 사람이 스스로 해결됐다고 표시하지 못하게 한다.
        showLoading('다시 살펴보고 있어요…');
        await runCompliance(true);
        hideLoading();
        renderResult();
        toast('문구를 바꿨어요');
      });
      fix.appendChild(btn);
    } else if (issue.phrase) {
      // 대안 문구가 없는 항목(가격·이벤트·예약 유도 등)은 문장을 통째로 다시 써야 한다.
      fix.innerHTML = '<span class="issue-fix-text">이 표현은 빼야 해요</span>';

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-secondary btn-sm';
      btn.textContent = '이 문단 다시 쓰기';
      btn.addEventListener('click', () => rewriteSectionFor(issue));
      fix.appendChild(btn);
    } else {
      // 검사 자체가 실패한 경우
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-secondary btn-sm';
      btn.textContent = '다시 검사하기';
      btn.addEventListener('click', async () => {
        showLoading('의료법 표현을 살펴보고 있어요…');
        await runCompliance(false);
        hideLoading();
        renderResult();
      });
      fix.appendChild(btn);
    }

    el.appendChild(fix);
    list.appendChild(el);
  });

  if (state.contextChecked === false && open.length > 0) {
    const note = document.createElement('p');
    note.className = 'issue-empty';
    note.textContent = '문맥 검사는 하지 못했어요. 눈으로 한 번 더 확인해 주세요.';
    list.appendChild(note);
  }

  if (danger.length > 0) {
    badge.className = 'badge badge-danger';
    badge.textContent = `위험 ${danger.length}`;
  } else if (open.length > 0) {
    badge.className = 'badge badge-warn';
    badge.textContent = `주의 ${open.length}`;
  } else {
    badge.className = 'badge badge-success';
    badge.textContent = '통과';
  }

  // 위험 항목이 남아 있으면 복사를 막는다 (우회 경로를 만들지 않는다)
  const blocked = danger.length > 0;
  $('#btn-copy').disabled = blocked;
  $('#copy-blocked-note').hidden = !blocked;
}

function renderFormatOptions() {
  const select = $('#format-select');
  if (select.options.length > 0) return;
  config.platforms.forEach((p) => {
    const option = document.createElement('option');
    option.value = p.id;
    option.textContent = `${p.name} 형식으로 복사`;
    select.appendChild(option);
  });
  select.value = state.platform || 'naver';
}

/**
 * 플랫폼별 글 조립.
 * 5단계에서 플랫폼마다 제대로 나누고, 지금은 붙여넣어 확인할 수 있는 정도만 만든다.
 */
function buildText(format) {
  const lines = [];
  if (format === 'wordpress' || format === 'blog-md') {
    lines.push(`# ${state.title}`, '');
    state.draft.sections.forEach((s) => {
      lines.push(`## ${s.heading}`, '', s.body, '');
    });
  } else {
    lines.push(state.title, '');
    state.draft.sections.forEach((s) => {
      lines.push(`■ ${s.heading}`, '', s.body, '');
    });
  }
  if (format === 'naver' || format === 'sns') {
    lines.push(formatHashtags(state.draft.hashtags));
  }
  return lines.join('\n');
}

// ─────────────────────────── [5] 이력 ───────────────────────────

function renderHistory() {
  const rows = readLocal(KEY_HISTORY, []);
  const query = $('#history-search').value.trim().toLowerCase();
  const filtered = query
    ? rows.filter((r) => [r.branchName, r.procedureName, r.title].join(' ').toLowerCase().includes(query))
    : rows;

  $('#history-empty').hidden = filtered.length > 0;
  $('#history-table-wrap').hidden = filtered.length === 0;

  if (filtered.length === 0) {
    if (query) {
      $('#history-empty').hidden = false;
      $('#history-empty').querySelector('.empty-title').textContent = '찾는 글이 없어요';
      $('#history-empty').querySelector('.empty-sub').textContent = '다른 말로 검색해 보세요.';
    } else {
      $('#history-empty').querySelector('.empty-title').textContent = '아직 만든 글이 없어요';
      $('#history-empty').querySelector('.empty-sub').textContent = '첫 글을 만들면 여기에 쌓입니다.';
    }
    return;
  }

  $('#history-rows').innerHTML = filtered.map((r) => {
    const date = new Date(r.createdAt);
    const stamp = `${date.getFullYear()}.${String(date.getMonth() + 1).padStart(2, '0')}.${String(date.getDate()).padStart(2, '0')}`;
    return `<tr>
      <td>${stamp}</td>
      <td>${escapeHtml(r.author || '-')}</td>
      <td>${escapeHtml(r.branchName)}</td>
      <td>${escapeHtml(r.procedureName)}</td>
      <td class="col-title">${escapeHtml(r.title)}</td>
      <td>${escapeHtml(r.platformName)}</td>
      <td>${escapeHtml(r.status)}</td>
    </tr>`;
  }).join('');
}

// ─────────────────────────── 잡다 ───────────────────────────

function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ─────────────────────────── 이벤트 연결 ───────────────────────────

function bindEvents() {
  // 잠금 화면 — 3단계에서 POST /api/auth 호출로 바꾼다
  $('#lock-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const value = $('#lock-password').value.trim();
    const error = $('#lock-error');
    const button = $('#lock-form button[type="submit"]');

    if (!value) {
      error.textContent = '비밀번호를 입력해 주세요.';
      error.hidden = false;
      return;
    }

    error.hidden = true;
    button.disabled = true;
    showLoading('들어가는 중이에요…');

    try {
      // 비밀번호 검증은 서버에서만 한다. 이 파일에는 비밀번호도 해시도 없다.
      const auth = await api('/api/auth', { password: value });
      saveLocal(KEY_TOKEN, auth.token);
      $('#lock-password').value = '';

      showLoading('선택 목록을 가져오고 있어요…');
      await startApp();
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
    } finally {
      button.disabled = false;
      hideLoading();
    }
  });

  // 탭 · 화면 이동 버튼
  $$('.tab').forEach((tab) => tab.addEventListener('click', () => goTo(tab.dataset.tab)));
  $$('[data-go]').forEach((el) => el.addEventListener('click', (e) => {
    e.preventDefault();
    goTo(el.dataset.go);
  }));

  // 시술 검색
  const search = $('#proc-search');
  search.addEventListener('input', () => {
    $('#proc-search-clear').hidden = search.value.length === 0;
    renderProcedureItems();
  });
  $('#proc-search-clear').addEventListener('click', () => {
    search.value = '';
    $('#proc-search-clear').hidden = true;
    renderProcedureItems();
    search.focus();
  });

  // 페르소나 직접 입력
  $('#persona-custom-text').addEventListener('input', (e) => {
    state.personaCustom = e.target.value;
    saveDraftState();
    validateInput();
  });

  // 고급 옵션
  $('#input-cta').addEventListener('input', (e) => { state.cta = e.target.value; saveDraftState(); });
  $('#input-reference').addEventListener('input', (e) => {
    state.reference = e.target.value;
    $('#ref-count').textContent = e.target.value.length.toLocaleString();
    saveDraftState();
  });

  // 직전 설정 불러오기
  $('#btn-load-last').addEventListener('click', () => {
    const last = readLocal(KEY_LAST_SETTING, null);
    if (!last) return;
    Object.assign(state, last);
    renderInputScreen();
    toast('직전 설정을 불러왔어요');
  });

  // [1] → [2]
  $('#btn-to-keywords').addEventListener('click', async () => {
    if (!validateInput()) return;
    saveLocal(KEY_LAST_SETTING, {
      branch: state.branch, category: state.category, procedure: state.procedure,
      persona: state.persona, personaCustom: state.personaCustom, audience: state.audience,
      tone: state.tone, platform: state.platform, length: state.length,
    });
    const data = await runStep(
      ['검색 키워드를 찾고 있어요…', '조금만 더 기다려 주세요…'],
      () => api('/api/keywords', requestPayload()),
    );
    if (!data) return;

    state.keywordPool = data.keywords;
    state.keywords = [];
    renderKeywordCards();
    updateKeywordHint();
    saveDraftState();
    goTo('keywords');
  });

  // 키워드 직접 추가
  const addKeyword = () => {
    const input = $('#keyword-add');
    const text = input.value.trim();
    if (!text) return;
    if (state.keywordPool.some((k) => k.text === text)) { toast('이미 있는 키워드예요'); return; }
    state.keywordPool.unshift({ text, intent: '직접 추가' });
    if (state.keywords.length < 5) state.keywords.push(text);
    input.value = '';
    renderKeywordCards();
    updateKeywordHint();
    saveDraftState();
  };
  $('#keyword-add-btn').addEventListener('click', addKeyword);
  $('#keyword-add').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); addKeyword(); }
  });

  // [2] → [3]
  $('#btn-to-titles').addEventListener('click', async () => {
    const data = await runStep(
      ['제목을 뽑고 있어요…', '조금만 더 기다려 주세요…'],
      () => api('/api/titles', { ...requestPayload(), selected_keywords: state.keywords }),
    );
    if (!data) return;

    state.titlePool = data.titles;
    state.title = '';
    renderTitleCards();
    $('#title-edit-wrap').hidden = true;
    $('#btn-to-result').disabled = true;
    saveDraftState();
    goTo('titles');
  });

  $('#btn-retry-titles').addEventListener('click', async () => {
    const data = await runStep(
      ['제목을 다시 뽑고 있어요…'],
      () => api('/api/titles', { ...requestPayload(), selected_keywords: state.keywords }),
    );
    if (!data) return;

    state.titlePool = data.titles;
    renderTitleCards();
    toast('제목을 다시 추천했어요');
  });

  $('#title-edit').addEventListener('input', (e) => {
    state.title = e.target.value;
    $('#title-count').textContent = String(e.target.value.length);
    $('#btn-to-result').disabled = e.target.value.trim().length === 0;
    saveDraftState();
  });

  // [3] → [4]
  $('#btn-to-result').addEventListener('click', async () => {
    // 본문은 20~40초 걸린다. 무슨 일이 일어나는지 문장으로 계속 알린다.
    const data = await runStep(
      ['글 구조를 잡고 있어요…', '본문을 쓰고 있어요…', '문장을 다듬고 있어요…', '거의 다 됐어요…'],
      () => api('/api/draft', {
        ...requestPayload(),
        selected_keywords: state.keywords,
        title: state.title,
      }),
    );
    if (!data) return;

    state.draft = {
      sections: data.sections,
      hashtags: data.hashtags,
      meta_description: data.meta_description,
      char_count: data.char_count,
      target_chars: data.target_chars,
    };
    // 본문이 나왔으면 곧바로 검사한다. 검사 없이 결과 화면을 보여주지 않는다.
    showLoading('의료법 표현을 살펴보고 있어요…');
    await runCompliance(false);
    hideLoading();

    renderResult();
    saveDraftState();
    goTo('result');
  });

  // 결과 화면 버튼
  $('#format-select').addEventListener('change', (e) => {
    toast(`${e.target.selectedOptions[0].textContent.replace(' 형식으로 복사', '')} 형식으로 바꿨어요`);
  });

  $('#btn-copy').addEventListener('click', async () => {
    const text = buildText($('#format-select').value);
    try {
      await navigator.clipboard.writeText(text);
      toast('복사했어요. 붙여넣기 하세요');
    } catch (e) {
      toast('복사가 안 됐어요. 글을 직접 선택해 복사해 주세요');
    }
  });

  $('#btn-download').addEventListener('click', () => {
    const text = buildText($('#format-select').value);
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${state.title.slice(0, 30) || '블로그글'}.txt`;
    link.click();
    URL.revokeObjectURL(url);
    toast('내려받았어요');
  });

  // 6단계에서 서버 저장으로 바꾼다
  $('#btn-save').addEventListener('click', () => {
    const ctx = currentContext();
    const rows = readLocal(KEY_HISTORY, []);
    const hasDanger = state.issues.some((i) => !i.resolved && i.level === 'danger');
    rows.unshift({
      id: String(Date.now()),
      createdAt: Date.now(),
      author: '',
      branch: state.branch, branchName: ctx.branchName,
      procedure: state.procedure, procedureName: ctx.procedureName,
      platformName: ctx.platformName,
      title: state.title,
      status: hasDanger ? '수정 필요' : '완료',
    });
    saveLocal(KEY_HISTORY, rows);
    toast('이력에 저장했어요');
  });

  $('#btn-new').addEventListener('click', () => {
    Object.assign(state, {
      keywords: [], keywordPool: [], titlePool: [], title: '', draft: null, issues: [],
    });
    saveDraftState();
    goTo('input');
  });

  $('#history-search').addEventListener('input', renderHistory);
}

// ─────────────────────────── 시작 ───────────────────────────

/**
 * 글 목적에 따라 입력 항목 구성을 바꾼다 (SPEC §5.6).
 * - 정보성: 이벤트·가격 입력란을 숨기고, 페르소나에서 후기형을 뺀다
 * - 홍보성: 현행 그대로
 *
 * 화면에서 숨기는 것은 편의일 뿐이다. 실제 차단은 서버가 한다.
 */
function applyMode() {
  const mode = MODES.find((m) => m.id === state.mode) || MODES[0];
  const isInfo = mode.id === 'information';

  $('#mode-note').textContent = mode.note;

  $('#cta-field').hidden = isInfo;
  $('#advanced-title').textContent = isInfo
    ? '참고자료 넣기'
    : '이벤트·가격 정보나 참고자료 넣기';

  // 정보성에서 후기형을 이미 고른 상태였다면 풀어준다
  if (isInfo && state.persona === 'review') {
    state.persona = null;
    state.personaCustom = '';
    toast('정보성 글에는 후기형을 쓸 수 없어 선택을 풀었어요');
  }

  renderChipGroup('#group-persona', personaChoices(), 'persona', onPersonaPicked);
  onPersonaPicked(state.persona);
}

/** 지금 모드에서 고를 수 있는 페르소나 목록. */
function personaChoices() {
  if (state.mode === 'information') {
    return config.personas.filter((p) => p.id !== 'review');
  }
  return config.personas;
}

function renderInputScreen() {
  renderChipGroup('#group-mode', MODES, 'mode', () => { applyMode(); validateInput(); });
  renderChipGroup('#group-branch', config.branches, 'branch', () => updateDuplicateBanner());
  renderProcedureCategories();
  renderProcedureItems();
  renderChipGroup('#group-persona', personaChoices(), 'persona', onPersonaPicked);
  renderChipGroup('#group-audience', config.audiences, 'audience');
  renderChipGroup('#group-tone', config.tones, 'tone');
  renderChipGroup('#group-platform', config.platforms, 'platform');
  renderChipGroup('#group-length', config.lengths, 'length');

  $('#persona-custom-text').value = state.personaCustom || '';
  $('#input-cta').value = state.cta || '';
  $('#input-reference').value = state.reference || '';
  $('#ref-count').textContent = String((state.reference || '').length);

  applyMode();
  updateSummary();
  updateDuplicateBanner();
  validateInput();
}

function unlock() {
  $('#screen-lock').hidden = true;
  $('#app-header').hidden = false;
  $('#app-main').hidden = false;
  goTo('input');
}

/** 토큰이 만료됐을 때 잠금 화면으로 되돌린다. 입력해 둔 내용은 남겨둔다. */
function lock(message) {
  saveLocal(KEY_TOKEN, '');
  $('#app-header').hidden = true;
  $('#app-main').hidden = true;
  $('#screen-lock').hidden = false;
  $('#lock-error').textContent = message || '비밀번호를 다시 입력해 주세요.';
  $('#lock-error').hidden = false;
  window.scrollTo({ top: 0 });
}

/** 로그인 이후 — 기준정보를 받아 화면을 그린다. */
async function startApp() {
  config = await loadConfig();
  duplicateNames = findDuplicateNames(config.procedures);

  // 새로고침·뒤로가기에도 입력이 날아가지 않게 복원한다
  const saved = readLocal(KEY_DRAFT_STATE, null);
  if (saved) Object.assign(state, saved);
  if (!MODES.some((m) => m.id === state.mode)) state.mode = MODES[0].id;

  renderInputScreen();
  $('#btn-load-last').hidden = !readLocal(KEY_LAST_SETTING, null);
  unlock();
}

async function boot() {
  bindEvents();

  // 무료 플랜은 첫 요청이 느리다. 비밀번호를 치는 동안 미리 깨워둔다.
  const waking = wakeServer();

  const token = getToken();
  if (!token) {
    await waking;
    return; // 잠금 화면에 그대로 머문다
  }

  // 저장된 토큰이 아직 살아 있으면 비밀번호 없이 바로 들어간다 (30일)
  showLoading('준비하고 있어요…');
  try {
    await waking;
    await startApp();
  } catch (err) {
    saveLocal(KEY_TOKEN, '');
    if (!(err instanceof NeedsLogin)) {
      $('#lock-error').textContent = err.message;
      $('#lock-error').hidden = false;
    }
  } finally {
    hideLoading();
  }
}

boot();
