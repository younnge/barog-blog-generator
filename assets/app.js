/* ============================================================
   바로그 블로그 글 만들기 — 화면 로직 (2단계)

   이 단계에서는 서버를 부르지 않는다.
   - 기준정보: config/*.json 을 직접 읽어 버튼을 그린다
   - 키워드·제목·본문·의료법 검사: 화면 확인용 예시 데이터 (아래 SAMPLE)
   3단계에서 SAMPLE 부분과 loadConfig() 만 서버 호출로 바꾸면 된다.
   ============================================================ */

'use strict';

// ─────────────────────────── 저장 키 ───────────────────────────

const KEY_DRAFT_STATE = 'barog.draft';       // 작성 중이던 입력 (새로고침 대비)
const KEY_LAST_SETTING = 'barog.lastSetting'; // 직전 설정 불러오기
const KEY_HISTORY = 'barog.history';         // 이력 (6단계에서 서버 저장으로 교체)
const KEY_UNLOCKED = 'barog.unlocked';       // 잠금 해제 여부 (3단계에서 토큰으로 교체)

// ─────────────────────────── 상태 ───────────────────────────

let config = null;

const state = {
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

/** 진행 중인 것처럼 보이게 잠깐 기다린다. 3단계에서 실제 서버 호출로 바뀐다. */
function pretendWork(text, ms = 700) {
  showLoading(text);
  return new Promise((resolve) => setTimeout(() => { hideLoading(); resolve(); }, ms));
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
 * 응답 모양(branches/procedures/personas/audiences/tones/platforms/lengths)은 서버와 동일하게 맞춰 두었다.
 */
async function loadConfig() {
  const names = ['branches', 'procedures', 'personas', 'audiences', 'tones'];
  const loaded = await Promise.all(
    names.map((name) => fetch(`config/${name}.json`).then((res) => {
      if (!res.ok) throw new Error(name);
      return res.json();
    }))
  );

  const result = {};
  names.forEach((name, i) => { result[name] = loaded[i]; });

  // 플랫폼·분량은 서버가 기준을 갖는 값이다. 2단계에서는 같은 모양으로 여기에 둔다.
  result.platforms = [
    { id: 'naver', name: '네이버 블로그', description: '스마트에디터 붙여넣기용', active: true },
    { id: 'wordpress', name: '워드프레스·자사 홈페이지', description: '마크다운 + HTML', active: true },
    { id: 'sns', name: '인스타·스레드', description: '캡션형으로 짧게', active: true },
    { id: 'blog-md', name: '티스토리·브런치', description: '마크다운', active: true },
  ];
  result.lengths = [
    { id: 'short', name: '짧게', description: '약 1,200자', target_chars: 1200, active: true },
    { id: 'medium', name: '보통', description: '약 2,000자', target_chars: 2000, active: true },
    { id: 'long', name: '길게', description: '약 3,000자', target_chars: 3000, active: true },
  ];

  // active: false 인 항목은 화면에 그리지 않는다 (지운 지점·시술도 과거 이력을 위해 JSON에는 남아 있다)
  const onlyActive = (list) => list.filter((item) => item.active !== false);
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
      state[stateKey] = (state[stateKey] === item.id) ? null : item.id;
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
    state.branch && state.procedure && state.persona &&
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

// ─────────────────────────── 예시 데이터 (3단계에서 교체) ───────────────────────────

const SAMPLE = {
  /** 키워드 후보 — 실제로는 POST /api/keywords 응답 */
  keywords(ctx) {
    const p = ctx.procedureName;
    const b = ctx.branchName.replace(/점$/, '');
    return [
      { text: `${p} 효과`, intent: '정보형' },
      { text: `${p} 가격`, intent: '비교형' },
      { text: `${b} ${p}`, intent: '예약형' },
      { text: `${p} 후기`, intent: '후기형' },
      { text: `${p} 주기`, intent: '정보형' },
      { text: `${p} 통증`, intent: '정보형' },
      { text: `${p} 회복기간`, intent: '정보형' },
      { text: `${p} 부작용`, intent: '정보형' },
      { text: `${p} 비교`, intent: '비교형' },
      { text: `${p} 추천`, intent: '비교형' },
      { text: `${p} 관리법`, intent: '정보형' },
      { text: `${b} 피부과`, intent: '예약형' },
    ];
  },

  /** 제목 후보 — 실제로는 POST /api/titles 응답 */
  titles(ctx) {
    const p = ctx.procedureName;
    const k = ctx.keywords[0] || p;
    return [
      { text: `${p}, 처음이라면 이것부터 확인하세요`, hook: '고민 짚어주기' },
      { text: `${p} 받기 전 꼭 알아야 할 5가지`, hook: '숫자 나열형' },
      { text: `${k} 궁금하셨죠? 상담실장이 정리했습니다`, hook: '질문 던지기' },
      { text: `${p} 주기와 관리법, 한 번에 정리`, hook: '정보 정리형' },
      { text: `${ctx.branchName}에서 ${p} 상담할 때 가장 많이 듣는 질문`, hook: '현장 경험형' },
    ];
  },

  /** 본문 — 실제로는 POST /api/draft 응답 (SSE 스트리밍) */
  draft(ctx) {
    const p = ctx.procedureName;
    return {
      sections: [
        {
          heading: '이런 고민으로 오십니다',
          body: `${ctx.audienceName} 분들이 ${p} 상담을 받으러 오실 때 가장 먼저 꺼내는 이야기가 있습니다.\n` +
                '거울을 볼 때마다 신경 쓰이는데, 막상 병원에 오려니 뭘 물어봐야 할지 모르겠다는 말씀이에요.\n' +
                '오늘은 그 첫 질문들을 순서대로 정리해 보겠습니다.',
        },
        {
          heading: `${p}는 어떤 시술인가요`,
          body: `${p}는 피부 상태와 목표에 따라 설정을 달리해 진행합니다.\n` +
                '같은 이름의 시술이라도 어떤 부위에, 어느 정도 강도로 하느냐에 따라 과정이 달라집니다.\n' +
                '그래서 상담에서 피부 상태를 먼저 확인하는 과정이 중요합니다.',
        },
        {
          heading: '상담에서 자주 듣는 질문',
          body: '“얼마나 아픈가요?” — 부위와 개인차가 있어 한마디로 답하기는 어렵습니다.\n' +
                '“며칠 쉬어야 하나요?” — 일정이 있으시면 미리 말씀해 주세요. 시기를 조절해 잡아드립니다.\n' +
                '“몇 번 받아야 하나요?” — 목표에 따라 다릅니다. 상담 때 함께 계획을 세웁니다.',
        },
        {
          heading: '시술 전후 이렇게 준비하세요',
          body: '시술 전날에는 자극이 강한 홈케어를 잠시 쉬어주세요.\n' +
                '시술 후에는 보습과 자외선 차단이 가장 중요합니다.\n' +
                '평소보다 순한 제품으로 바꾸고, 궁금한 점은 언제든 문의해 주세요.',
        },
        {
          heading: '상담 안내',
          body: ctx.cta
            ? ctx.cta
            : '피부 상태에 맞는 방향은 상담에서 확인하실 수 있습니다.\n예약은 전화나 온라인으로 편하게 남겨주세요.',
        },
      ],
      hashtags: ctx.keywords.slice(0, 5).map((k) => '#' + k.replace(/\s+/g, ''))
        .concat(['#' + ctx.branchName, '#피부과', '#피부관리', '#' + p.replace(/\s+/g, ''), '#바로그의원']),
      meta_description: `${p}가 처음이신 분들을 위해 상담에서 자주 나오는 질문과 준비 방법을 정리했습니다.`,
    };
  },

  /** 의료법 검사 결과 — 실제로는 POST /api/compliance 응답 */
  issues() {
    return [
      {
        level: 'danger',
        phrase: '부작용 없는',
        reason: '부작용이 없다고 단정하는 표현은 의료광고에서 쓸 수 없습니다.',
        suggestion: '개인차가 있을 수 있는',
      },
      {
        level: 'warn',
        phrase: '가장 인기 있는',
        reason: '객관적 근거 없이 최상급으로 읽힐 수 있습니다.',
        suggestion: '많이 문의 주시는',
      },
      {
        level: 'info',
        phrase: '지역명 반복',
        reason: '지역명과 시술명이 반복되면 검색 어뷰징으로 볼 수 있습니다.',
        suggestion: '문맥에 맞게 한두 번만 쓰기',
      },
    ];
  },
};

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
      `<span class="card-note">${t.text.length}자 · ${escapeHtml(t.hook)}</span>`;

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
      await pretendWork('이 부분을 다시 쓰고 있어요…', 900);
      // 3단계에서 POST /api/draft/section 응답으로 바꾼다
      section.body = section.body + '\n(다시 쓴 문단이 여기에 들어갑니다.)';
      renderResult();
      toast('문단을 다시 썼어요');
    });

    block.append(heading, body, redo);
    box.appendChild(block);
  });

  const tags = $('#result-hashtags');
  if (state.platform === 'naver' || state.platform === 'sns') {
    tags.textContent = state.draft.hashtags.join(' ');
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
    const safe = escapeHtml(issue.phrase);
    if (!html.includes(safe)) return;
    const cls = issue.level === 'warn' ? ' class="is-warn"' : '';
    html = html.split(safe).join(`<mark${cls}>${safe}</mark>`);
  });
  return html;
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

    if (issue.suggestion) {
      const fix = document.createElement('div');
      fix.className = 'issue-fix';
      fix.innerHTML = `<span class="issue-fix-text">→ ${escapeHtml(issue.suggestion)}</span>`;

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-secondary btn-sm';
      btn.textContent = '이 문구로 바꾸기';
      btn.addEventListener('click', () => {
        // 본문에서 표현을 바꾸고 다시 검사한다 (4단계에서 서버 재검사로 교체)
        state.draft.sections.forEach((s) => {
          s.body = s.body.split(issue.phrase).join(issue.suggestion);
        });
        issue.resolved = true;
        renderResult();
        toast('문구를 바꿨어요');
      });

      fix.appendChild(btn);
      el.appendChild(fix);
    }

    list.appendChild(el);
  });

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
    lines.push(state.draft.hashtags.join(' '));
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
  $('#lock-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const value = $('#lock-password').value.trim();
    const error = $('#lock-error');
    if (!value) {
      error.textContent = '비밀번호를 입력해 주세요.';
      error.hidden = false;
      return;
    }
    error.hidden = true;
    saveLocal(KEY_UNLOCKED, true);
    unlock();
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
    await pretendWork('검색 키워드를 찾고 있어요…');
    state.keywordPool = SAMPLE.keywords(currentContext());
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
    await pretendWork('제목을 뽑고 있어요…');
    state.titlePool = SAMPLE.titles(currentContext());
    state.title = '';
    renderTitleCards();
    $('#title-edit-wrap').hidden = true;
    $('#btn-to-result').disabled = true;
    saveDraftState();
    goTo('titles');
  });

  $('#btn-retry-titles').addEventListener('click', async () => {
    await pretendWork('제목을 다시 뽑고 있어요…');
    state.titlePool = SAMPLE.titles(currentContext());
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
    showLoading('글 구조를 잡고 있어요…');
    await new Promise((r) => setTimeout(r, 800));
    showLoading('본문을 쓰고 있어요…');
    await new Promise((r) => setTimeout(r, 1200));
    showLoading('의료법 표현을 살펴보고 있어요…');
    await new Promise((r) => setTimeout(r, 700));
    hideLoading();

    state.draft = SAMPLE.draft(currentContext());
    state.issues = SAMPLE.issues();
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

function renderInputScreen() {
  renderChipGroup('#group-branch', config.branches, 'branch', () => updateDuplicateBanner());
  renderProcedureCategories();
  renderProcedureItems();
  renderChipGroup('#group-persona', config.personas, 'persona', onPersonaPicked);
  renderChipGroup('#group-audience', config.audiences, 'audience');
  renderChipGroup('#group-tone', config.tones, 'tone');
  renderChipGroup('#group-platform', config.platforms, 'platform');
  renderChipGroup('#group-length', config.lengths, 'length');

  $('#persona-custom-text').value = state.personaCustom || '';
  $('#input-cta').value = state.cta || '';
  $('#input-reference').value = state.reference || '';
  $('#ref-count').textContent = String((state.reference || '').length);

  onPersonaPicked(state.persona);
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

async function boot() {
  try {
    config = await loadConfig();
  } catch (e) {
    $('#lock-error').textContent = '화면을 불러오지 못했어요. 새로고침해 주세요.';
    $('#lock-error').hidden = false;
    return;
  }

  duplicateNames = findDuplicateNames(config.procedures);

  // 새로고침·뒤로가기에도 입력이 날아가지 않게 복원한다
  const saved = readLocal(KEY_DRAFT_STATE, null);
  if (saved) Object.assign(state, saved);

  bindEvents();
  renderInputScreen();
  $('#btn-load-last').hidden = !readLocal(KEY_LAST_SETTING, null);

  if (readLocal(KEY_UNLOCKED, false)) {
    unlock();
  }
}

boot();
