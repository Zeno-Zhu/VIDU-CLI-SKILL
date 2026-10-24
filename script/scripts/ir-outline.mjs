#!/usr/bin/env node
/**
 * ir-outline.mjs —— 无限轮回剧本 · 大纲校验与渲染
 *
 * 数据契约与确定性质量门设计改造自 eternityspring/shuohao-skills 的 novel-outline（Apache-2.0）。
 * 工艺与设定来自《无限轮回宇宙·短剧共创 设定》阶段零、第七章。
 *
 * 零依赖，Node >= 18。
 *   node ir-outline.mjs seed     world.json          > outline.json
 *   node ir-outline.mjs validate outline.json --stage skeleton|beats|full
 *   node ir-outline.mjs checkup  outline.json
 *   node ir-outline.mjs render   outline.json --md
 *   node ir-outline.mjs assets   outline.json
 *   node ir-outline.mjs stats    outline.json
 */
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { writeDocx, P } from './docx.mjs';

/* ------------------------------------------------------------------ */
/* 常量                                                                */
/* ------------------------------------------------------------------ */

const QUOTE_RE = /[「」『』“”"]/;
const ANCHORS = ['base:wanji', 'base:suwei', 'system', 'local'];
const TIERS = ['lead', 'support', 'functional'];

const WARN_RULES = [
  { tag: '雨戏', re: /雨|暴雨|下雨/ },
  { tag: '肢体接触', re: /拥抱|抱住|牵手|亲吻|接吻|背起|扛起/ },
  { tag: '人群', re: /人群|围观|众目睽睽|满场人|一片人/ },
  { tag: '手部特写', re: /手部特写|指尖|手指/ },
];

const ALL_GATES = [
  'characters-lead', 'characters-support', 'characters-functional',
  'scenes-cap', 'scene-reuse', 'props-cap',
  'beat-gap', 'beat-major', 'hook-ep1',
  'episode-three', 'crowd-plan', 'warnings', 'refs', 'prose',
  'anchor-unique', 'core-value', 'mainline-bound',
];

const STAGES = {
  skeleton: ['characters-lead', 'characters-support', 'characters-functional', 'scenes-cap', 'scene-reuse', 'props-cap', 'anchor-unique'],
  beats: ['characters-lead', 'characters-support', 'characters-functional', 'scenes-cap', 'scene-reuse', 'props-cap',
    'beat-gap', 'beat-major', 'anchor-unique', 'core-value', 'mainline-bound'],
  full: ALL_GATES,
};

const GATE_LABELS = {
  'characters-lead': '主角组人数在 1–5 之间',
  'characters-support': '重要配角 ≤ 上限',
  'characters-functional': '功能性角色 ≤ 上限',
  'scenes-cap': '主场景不超过上限（随集数动态）',
  'scene-reuse': '全剧只出现一次的场景有 reusePlan',
  'props-cap': '叙事道具 ≤ 上限',
  'beat-gap': '爽点无真空，相邻间隔在限内',
  'beat-major': '至少一个 major，且最早的 major 不在最后一集',
  'hook-ep1': '第 1 集有钩子',
  'episode-three': '每集三栏齐全（梗概/钩子/悬念）',
  'crowd-plan': '三人以上同框有拆解方案',
  'warnings': '生成难点已进预警',
  'refs': '引用完整：无失业角色、空转场景、零集道具',
  'prose': '梗概是叙述体，没有对白',
  'anchor-unique': '锚点唯一（万集 1 个、苏薇 ≤1、系统 ≤1）',
  'core-value': '核心观看商品都有戏认领',
  'mainline-bound': '主线边界守住（mainline=false 时不揭终极秘密）',
};

/* ------------------------------------------------------------------ */
/* 工具                                                                */
/* ------------------------------------------------------------------ */

const th = (s) => typeof s === 'string' && s.trim().length > 0;
const num = (v, d) => (Number.isFinite(Number(v)) ? Number(v) : d);

export function paramsOf(doc) {
  const p = doc?.params ?? {};
  const episodes = num(p.episodes, 0);
  const thres = p.thresholds ?? {};
  return {
    episodes,
    targetSeconds: num(p.targetSeconds, 75),
    genre: p.genre ?? '',
    origin: doc?.origin ?? 'original',
    adaptMode: p.adaptMode ?? '抽核',
    coreValue: Array.isArray(p.coreValue) ? p.coreValue : [],
    mainline: p.mainline === true,
    preferences: p.preferences ?? [],
    maxLeads: num(thres.maxLeads, 5),
    maxSupport: num(thres.maxSupport, 10),
    maxFunctional: num(thres.maxFunctional, 10),
    maxBeatGap: num(thres.maxBeatGap, 3),
    maxProps: num(thres.maxProps, 8),
    maxPrimaryScenes: num(thres.maxPrimaryScenes, dynamicSceneCap(episodes)),
  };
}

/** 主场景上限随集数动态：4 + ⌈集数/10⌉，夹在 5–15 */
export function dynamicSceneCap(episodes) {
  if (!episodes) return 15;
  return Math.min(15, Math.max(5, 4 + Math.ceil(episodes / 10)));
}

/* ------------------------------------------------------------------ */
/* 各门判定                                                            */
/* ------------------------------------------------------------------ */

function checkCharacters(chars, p) {
  const out = { lead: [], support: [], functional: [], anchor: [] };
  const byTier = (t) => chars.filter((c) => c.tier === t);

  const lead = byTier('lead');
  const support = byTier('support');
  const func = byTier('functional');

  if (lead.length < 1) out.lead.push('主角组为空——至少 1 个 lead');
  if (lead.length > p.maxLeads) out.lead.push(`主角组 ${lead.length} 人，超过上限 ${p.maxLeads}`);
  if (support.length > p.maxSupport) out.support.push(`重要配角 ${support.length} 人，超过上限 ${p.maxSupport}`);
  if (func.length > p.maxFunctional) out.functional.push(`功能性角色 ${func.length} 人，超过上限 ${p.maxFunctional}`);

  for (const c of chars) {
    if (!th(c?.id)) out.anchor.push('有角色缺 id');
    if (!th(c?.name)) out.anchor.push(`${c?.id ?? '?'} 缺 name`);
    if (!TIERS.includes(c?.tier)) out.anchor.push(`${c?.id ?? '?'} 的 tier「${c?.tier}」不合法`);
    if (!ANCHORS.includes(c?.anchor)) out.anchor.push(`${c?.id ?? '?'} 的 anchor「${c?.anchor}」不合法`);
    if ((c?.tier === 'lead' || c?.tier === 'support') && !th(c?.arc)) out.anchor.push(`${c?.id ?? '?'} 是 ${c?.tier}，arc 必填`);
    if (!Array.isArray(c?.from) || c.from.length === 0) out.anchor.push(`${c?.id ?? '?'} 的 from 必须是非空数组`);
  }

  const w = chars.filter((c) => c.anchor === 'base:wanji');
  const s = chars.filter((c) => c.anchor === 'base:suwei');
  const sys = chars.filter((c) => c.anchor === 'system');

  if (w.length === 0) out.anchor.push('没有 base:wanji——本篇男主必须是万集');
  if (w.length > 1) out.anchor.push(`base:wanji 有 ${w.length} 个，只能 1 个`);
  if (s.length > 1) out.anchor.push(`base:suwei 有 ${s.length} 个，最多 1 个（不许造第二个锚点）`);
  if (sys.length > 1) out.anchor.push(`system 有 ${sys.length} 个，最多 1 个`);

  const cv = p.coreValue.join(' ');
  if (/爱情|甜|情感|恋/.test(cv) && s.length === 0) {
    out.anchor.push('coreValue 含爱情/甜，但人物表里没有 base:suwei');
  }

  return out;
}

function checkBeats(beats, p) {
  const out = { gap: [], major: [], value: [], mainline: [] };

  const at = [...new Set(beats.map((b) => b.episode).filter(Number.isInteger))].sort((a, b) => a - b);
  if (!at.length) {
    out.gap.push('一条爽点都没有');
  } else {
    if (at[0] > p.maxBeatGap) out.gap.push(`开头真空：第 1–${at[0] - 1} 集无爽点（上限 ${p.maxBeatGap}）`);
    for (let i = 1; i < at.length; i += 1) {
      const d = at[i] - at[i - 1];
      if (d > p.maxBeatGap) out.gap.push(`第 ${at[i - 1]} 集到第 ${at[i]} 集之间空 ${d} 集（上限 ${p.maxBeatGap}）`);
    }
    if (p.episodes && p.episodes - at[at.length - 1] > p.maxBeatGap) {
      out.gap.push(`结尾真空：第 ${at[at.length - 1]} 集之后还有 ${p.episodes - at[at.length - 1]} 集无爽点`);
    }
  }

  const majors = beats.filter((b) => b.weight === 'major');
  if (!majors.length) {
    out.major.push('一个 major 都没有');
  } else {
    const eps = majors.map((b) => b.episode).filter(Number.isInteger);
    if (eps.length && Math.min(...eps) === p.episodes) out.major.push('最早的 major 落在最后一集——大爆点不能压到结尾');
  }

  const need = Math.max(1, Math.ceil((p.episodes || 1) / 10));
  for (const v of p.coreValue) {
    const n = beats.filter((b) => th(b.value) && (b.value.includes(v) || v.includes(b.value))).length;
    if (n < need) out.value.push(`「${v}」只被认领 ${n} 次（每 10 集至少 1 次，本篇需 ≥${need}）`);
  }
  if (!p.coreValue.length) out.value.push('params.coreValue 为空——本篇卖什么都没写');

  if (!p.mainline) {
    for (const b of beats) {
      if (th(b.reveal)) out.mainline.push(`${b.id ?? '?'} 标了 reveal「${b.reveal}」，但 mainline=false`);
    }
  }

  return out;
}

/* ------------------------------------------------------------------ */
/* 质量门                                                              */
/* ------------------------------------------------------------------ */

export function gateReport(doc, stage = 'full') {
  const p = paramsOf(doc);
  const chars = Array.isArray(doc?.characters) ? doc.characters : [];
  const scenes = Array.isArray(doc?.scenes) ? doc.scenes : [];
  const props = Array.isArray(doc?.props) ? doc.props : [];
  const beats = Array.isArray(doc?.beats) ? doc.beats : [];
  const eps = Array.isArray(doc?.episodes) ? doc.episodes : [];

  const c = checkCharacters(chars, p);
  const b = checkBeats(beats, p);

  const detail = {};
  const ok = {};

  ok['characters-lead'] = c.lead.length === 0;
  detail['characters-lead'] = c.lead.join('；');
  ok['characters-support'] = c.support.length === 0;
  detail['characters-support'] = c.support.join('；');
  ok['characters-functional'] = c.functional.length === 0;
  detail['characters-functional'] = c.functional.join('；');
  ok['anchor-unique'] = c.anchor.length === 0;
  detail['anchor-unique'] = c.anchor.join('；');

  // 主场景
  const primaries = scenes.filter((s) => s.primary === true);
  ok['scenes-cap'] = primaries.length <= p.maxPrimaryScenes;
  detail['scenes-cap'] = `主场景 ${primaries.length} 个，上限 ${p.maxPrimaryScenes}（${p.episodes} 集）`;

  // 一次性场景
  const usedIn = new Map();
  for (const ep of eps) for (const id of ep?.sceneIds ?? []) usedIn.set(id, (usedIn.get(id) ?? 0) + 1);
  const oneOff = scenes.filter((s) => (usedIn.get(s.id) ?? 0) === 1 && !th(s.reusePlan));
  if (!eps.length) {
    ok['scene-reuse'] = true;
    detail['scene-reuse'] = '尚无分集，本门跳过（视为通过）';
  } else {
    ok['scene-reuse'] = oneOff.length === 0;
    detail['scene-reuse'] = oneOff.map((s) => `${s.id}「${s.name ?? ''}」只出现一次，缺 reusePlan`).join('；');
  }

  ok['props-cap'] = props.length <= p.maxProps;
  detail['props-cap'] = `道具 ${props.length} 件，上限 ${p.maxProps}`;

  ok['beat-gap'] = b.gap.length === 0;
  detail['beat-gap'] = b.gap.join('；');
  ok['beat-major'] = b.major.length === 0;
  detail['beat-major'] = b.major.join('；');
  ok['core-value'] = b.value.length === 0;
  detail['core-value'] = b.value.join('；');
  ok['mainline-bound'] = b.mainline.length === 0;
  detail['mainline-bound'] = b.mainline.join('；');

  // 第 1 集钩子
  const ep1 = eps.find((e) => e?.ep === 1);
  ok['hook-ep1'] = th(ep1?.hook);
  detail['hook-ep1'] = ok['hook-ep1'] ? '' : '第 1 集没有钩子';

  // 三栏
  const miss3 = eps.filter((e) => !th(e?.synopsis) || !th(e?.hook) || !th(e?.suspense));
  ok['episode-three'] = eps.length > 0 && miss3.length === 0;
  detail['episode-three'] = miss3.length
    ? miss3.map((e) => `第 ${e.ep} 集缺${[!th(e?.synopsis) && '梗概', !th(e?.hook) && '钩子', !th(e?.suspense) && '悬念'].filter(Boolean).join('/')}`).join('；')
    : (eps.length ? '' : '还没有分集');

  // 三人同框
  const crowd = eps.filter((e) => (e?.characterIds ?? []).length >= 3 && !th(e?.crowdPlan));
  ok['crowd-plan'] = crowd.length === 0;
  detail['crowd-plan'] = crowd.map((e) => `第 ${e.ep} 集 ${e.characterIds.length} 人同框，缺 crowdPlan`).join('；');

  // 生成难点预警
  const warnBad = [];
  for (const e of eps) {
    const text = `${e?.synopsis ?? ''}${e?.hook ?? ''}${e?.suspense ?? ''}`;
    const need = WARN_RULES.filter((r) => r.re.test(text)).map((r) => r.tag);
    const has = new Set(Array.isArray(e?.warnings) ? e.warnings : []);
    for (const t of need) if (!has.has(t)) warnBad.push(`第 ${e.ep} 集提到「${t}」但没进 warnings`);
  }
  ok['warnings'] = warnBad.length === 0;
  detail['warnings'] = warnBad.join('；');

  // 引用完整
  const refsBad = [];
  if (p.episodes && eps.length !== p.episodes) {
    refsBad.push(`分集 ${eps.length} 条，params.episodes 是 ${p.episodes}`);
  }
  const charIds = new Set(chars.map((x) => x.id));
  const sceneIds = new Set(scenes.map((x) => x.id));
  const propIds = new Set(props.map((x) => x.id));
  const charUsed = new Set();
  const sceneUsed = new Set();
  const propUsed = new Set();

  for (const e of eps) {
    for (const id of e?.sceneIds ?? []) {
      if (!sceneIds.has(id)) refsBad.push(`第 ${e.ep} 集引用了不存在的场景 ${id}`);
      else sceneUsed.add(id);
    }
    for (const id of e?.characterIds ?? []) {
      if (!charIds.has(id)) refsBad.push(`第 ${e.ep} 集引用了不存在的角色 ${id}`);
      else charUsed.add(id);
    }
    for (const id of e?.propIds ?? []) {
      if (!propIds.has(id)) refsBad.push(`第 ${e.ep} 集引用了不存在的道具 ${id}`);
      else propUsed.add(id);
    }
  }
  if (eps.length) {
    for (const x of chars) if (!charUsed.has(x.id)) refsBad.push(`${x.id}「${x.name ?? ''}」全剧没出场`);
    for (const x of scenes) if (!sceneUsed.has(x.id)) refsBad.push(`${x.id}「${x.name ?? ''}」全剧没用过`);
    for (const x of props) if (!propUsed.has(x.id)) refsBad.push(`${x.id}「${x.name ?? ''}」没有任何一集引用`);
  }
  ok['refs'] = refsBad.length === 0;
  detail['refs'] = refsBad.join('；');

  // 叙述体
  const proseBad = [];
  for (const e of eps) {
    for (const [k, label] of [['synopsis', '梗概'], ['hook', '钩子'], ['suspense', '悬念']]) {
      if (QUOTE_RE.test(String(e?.[k] ?? ''))) proseBad.push(`第 ${e.ep} 集${label}`);
    }
  }
  ok['prose'] = proseBad.length === 0;
  detail['prose'] = proseBad.join('；');

  const wanted = STAGES[stage] ?? ALL_GATES;
  return ALL_GATES.filter((id) => wanted.includes(id)).map((id) => ({
    id,
    label: GATE_LABELS[id],
    ok: ok[id] !== false,
    detail: ok[id] === false ? (detail[id] || '') : (id === 'scenes-cap' || id === 'props-cap') ? (detail[id] || '') : '',
    skipped: id === 'scene-reuse' && !eps.length,
  }));
}

export function validateOutline(doc, stage = 'full') {
  return gateReport(doc, stage)
    .filter((g) => !g.ok)
    .map((g) => `${g.label}${g.detail ? ` — ${g.detail}` : ''}`);
}

/* ------------------------------------------------------------------ */
/* seed —— 从 world.json 建骨架                                         */
/* ------------------------------------------------------------------ */

export function seedFromWorld(world) {
  const p = world?.params ?? {};
  const episodes = num(p.episodes, 10);
  const target = num(p.targetSeconds, 75);
  const cast = Array.isArray(world?.cast) ? world.cast : [];

  const characters = [];
  let n = 0;
  const push = (c) => {
    n += 1;
    characters.push({ id: `C${String(n).padStart(2, '0')}`, arc: '', from: ['原创'], ...c });
  };

  // 万集恒为 C01
  push({ name: '万集', role: '男主', tier: 'lead', anchor: 'base:wanji' });

  for (const c of cast) {
    const anchor = ANCHORS.includes(c?.anchor) ? c.anchor : 'local';
    if (anchor === 'base:wanji') continue;
    push({
      name: c?.name ?? '',
      role: c?.want ?? '',
      tier: anchor === 'base:suwei' ? 'lead' : 'support',
      anchor,
      arc: '',
    });
  }

  return {
    source: world?.title ?? '',
    origin: world?.origin ?? 'original',
    params: {
      episodes,
      targetSeconds: target,
      genre: p.genre ?? '',
      adaptMode: '抽核',
      coreValue: Array.isArray(p.coreValue) ? p.coreValue : [],
      mainline: p.mainline === true,
      preferences: [],
      thresholds: {},
    },
    adaptation: {
      core: world?.coreIdea?.whyFun ?? '',
      keep: [{ what: '创作者原始脑洞', why: world?.coreIdea?.consume ?? '' }],
      cut: [],
      merge: [],
      risks: [],
      cutNote: '',
      mergeNote: '',
    },
    characters,
    scenes: [],
    props: [],
    beats: [],
    episodes: Array.from({ length: episodes }, (_, i) => ({
      ep: i + 1,
      synopsis: '',
      hook: '',
      suspense: '',
      sceneIds: [],
      characterIds: [],
      propIds: [],
      crowdPlan: '',
      warnings: [],
    })),
  };
}

/* ------------------------------------------------------------------ */
/* render —— Markdown                                                   */
/* ------------------------------------------------------------------ */

const ANCHOR_TAG = { 'base:wanji': '万集', 'base:suwei': '苏薇', system: '系统', local: '原创' };
const TIER_TAG = { lead: '主角组', support: '重要配角', functional: '功能性' };

export function renderMarkdown(doc) {
  const p = paramsOf(doc);
  const chars = doc?.characters ?? [];
  const scenes = doc?.scenes ?? [];
  const props = doc?.props ?? [];
  const beats = doc?.beats ?? [];
  const eps = doc?.episodes ?? [];
  const ad = doc?.adaptation ?? {};

  const nameOfChar = (id) => chars.find((c) => c.id === id)?.name ?? id;
  const nameOfScene = (id) => scenes.find((s) => s.id === id)?.name ?? id;

  const L = [];
  L.push(`# 《${doc?.source ?? '未命名'}》｜短剧大纲`, '');
  L.push(`- 题材：${p.genre || '—'}`);
  L.push(`- 规模：${p.episodes} 集 × ${p.targetSeconds} 秒`);
  L.push(`- 核心观看商品：${p.coreValue.join(' / ') || '—'}`);
  L.push(`- 来源模式：${p.origin === 'novel' ? '小说改编' : '脑洞原创'}（${p.adaptMode}）`);
  L.push(`- 主线：${p.mainline ? '本篇推进轮回主线' : '本篇以独立剧情为主'}`);
  L.push('');

  if (th(ad.core)) {
    L.push('## 一、核心', '', ad.core, '');
  }

  // 关键决策
  const majors = beats.filter((b) => b.weight === 'major');
  const leadN = chars.filter((c) => c.tier === 'lead').length;
  const supN = chars.filter((c) => c.tier === 'support').length;
  const funN = chars.filter((c) => c.tier === 'functional').length;
  L.push('## 二、关键决策', '');
  if (th(ad.cutNote)) L.push(`- 砍线结论：${ad.cutNote}`);
  if (th(ad.mergeNote)) L.push(`- 合人补注：${ad.mergeNote}`);
  L.push(`- 大爆点落在：${majors.length ? majors.map((b) => `第 ${b.episode} 集`).join('、') : '—'}`);
  L.push(`- 角色位：主角组 ${leadN} / 重要配角 ${supN} / 功能性 ${funN}`);
  L.push(`- 规模核算：${scenes.filter((s) => s.primary).length} 个主场景，${props.length} 件叙事道具`);
  L.push('');

  // 人物
  L.push('## 三、人物', '');
  L.push('| 编号 | 姓名 | 定位 | 档位 | 锚点 | 人物弧 |');
  L.push('| --- | --- | --- | --- | --- | --- |');
  for (const c of chars) {
    L.push(`| ${c.id} | ${c.name ?? ''} | ${c.role ?? ''} | ${TIER_TAG[c.tier] ?? c.tier ?? ''} | ${ANCHOR_TAG[c.anchor] ?? c.anchor ?? ''} | ${c.arc ?? '—'} |`);
  }
  L.push('');

  // 场景
  L.push('## 四、场景', '');
  L.push('| 编号 | 名称 | 主场景 | 复用方案 |');
  L.push('| --- | --- | --- | --- |');
  for (const s of scenes) {
    L.push(`| ${s.id} | ${s.name ?? ''} | ${s.primary ? '是' : ''} | ${s.reusePlan ?? ''} |`);
  }
  L.push('');

  // 道具
  if (props.length) {
    L.push('## 五、叙事道具', '');
    L.push('| 编号 | 名称 | 承载什么 | 托起爽点 |');
    L.push('| --- | --- | --- | --- |');
    for (const x of props) {
      L.push(`| ${x.id} | ${x.name ?? ''} | ${x.function ?? ''} | ${(x.beatIds ?? []).join('、')} |`);
    }
    L.push('');
  }

  // 观看价值曲线
  L.push(`## ${props.length ? '六' : '五'}、观看价值曲线`, '');
  L.push('| 编号 | 类型 | 观看价值 | 权重 | 集 | 铺垫 | 兑现 |');
  L.push('| --- | --- | --- | --- | --- | --- | --- |');
  for (const x of beats) {
    L.push(`| ${x.id} | ${x.type ?? ''} | ${x.value ?? ''} | ${x.weight === 'major' ? '大' : '小'} | ${x.episode} | ${x.setup ?? ''} | ${x.payoff ?? ''} |`);
  }
  L.push('');

  // 时间轴
  if (p.episodes) {
    const marks = new Map();
    for (const x of beats) {
      const cur = marks.get(x.episode) ?? [];
      cur.push(x.weight === 'major' ? '●' : '·');
      marks.set(x.episode, cur);
    }
    let axis = '';
    for (let i = 1; i <= p.episodes; i += 1) axis += marks.has(i) ? (marks.get(i).includes('●') ? '●' : '·') : '○';
    L.push(`时间轴（● 大爆点 · 小爆点 ○ 空档）：`, '', '```', axis, '```', '');
  }

  // 分集
  L.push(`## ${props.length ? '七' : '六'}、分集梗概`, '');
  for (const e of eps) {
    L.push(`### 第 ${e.ep} 集`, '');
    L.push(`**梗概**　${e.synopsis || '—'}`, '');
    L.push(`**钩子**　${e.hook || '—'}`, '');
    L.push(`**悬念**　${e.suspense || '—'}`, '');
    if ((e.sceneIds ?? []).length) L.push(`**场景**　${e.sceneIds.map(nameOfScene).join('、')}`, '');
    if ((e.characterIds ?? []).length) L.push(`**人物**　${e.characterIds.map(nameOfChar).join('、')}`, '');
    if (th(e.crowdPlan)) L.push(`**同框方案**　${e.crowdPlan}`, '');
    if (th(e.powerNote)) L.push(`**能力说明**　${e.powerNote}`, '');
    if ((e.warnings ?? []).length) L.push(`**生成预警**　${e.warnings.join('、')}`, '');
  }

  // 质量门
  L.push('## 质量门', '');
  for (const g of gateReport(doc, 'full')) {
    L.push(`- ${g.ok ? '✓' : g.skipped ? '·' : '✗'} ${g.label}${g.detail ? ` — ${g.detail}` : ''}`);
  }
  L.push('');

  return L.join('\n').replace(/\n{3,}/g, '\n\n').trimEnd() + '\n';
}

/* ------------------------------------------------------------------ */
/* render —— DOCX                                                       */
/* ------------------------------------------------------------------ */

export function renderDocx(doc, outPath = null) {
  const p = paramsOf(doc);
  const chars = doc?.characters ?? [];
  const scenes = doc?.scenes ?? [];
  const props = doc?.props ?? [];
  const beats = doc?.beats ?? [];
  const eps = doc?.episodes ?? [];
  const ad = doc?.adaptation ?? {};

  const nameOfChar = (id) => chars.find((c) => c.id === id)?.name ?? id;
  const nameOfScene = (id) => scenes.find((s) => s.id === id)?.name ?? id;

  const B = [];
  B.push(P.title(`《${doc?.source ?? '未命名'}》｜短剧大纲`));
  B.push(P.p(`题材：${p.genre || '—'}　规模：${p.episodes} 集 × ${p.targetSeconds} 秒`));
  B.push(P.p(`核心观看商品：${p.coreValue.join(' / ') || '—'}　主线：${p.mainline ? '推进' : '不推进'}`));
  B.push(P.p(`来源模式：${p.origin === 'novel' ? '小说改编' : '脑洞原创'}（${p.adaptMode}）`));

  if (th(ad.core)) {
    B.push(P.h2('一、核心'));
    B.push(P.p(ad.core));
  }

  const majors = beats.filter((b) => b.weight === 'major');
  B.push(P.h2('二、关键决策'));
  if (th(ad.cutNote)) B.push(P.p(`砍线结论：${ad.cutNote}`));
  if (th(ad.mergeNote)) B.push(P.p(`合人补注：${ad.mergeNote}`));
  B.push(P.p(`大爆点落在：${majors.length ? majors.map((b) => `第 ${b.episode} 集`).join('、') : '—'}`));
  B.push(P.p(`角色位：主角组 ${chars.filter((c) => c.tier === 'lead').length} / 重要配角 ${chars.filter((c) => c.tier === 'support').length} / 功能性 ${chars.filter((c) => c.tier === 'functional').length}`));

  B.push(P.h2('三、人物'));
  for (const c of chars) {
    B.push(P.p(`${c.id}　${c.name ?? ''}　【${TIER_TAG[c.tier] ?? c.tier}｜${ANCHOR_TAG[c.anchor] ?? c.anchor}】`));
    B.push(P.note(`${c.role ?? ''}${th(c.arc) ? `　弧：${c.arc}` : ''}`));
  }

  B.push(P.h2('四、场景'));
  for (const s of scenes) {
    B.push(P.p(`${s.id}　${s.name ?? ''}${s.primary ? '　（主场景）' : ''}`));
    if (th(s.reusePlan)) B.push(P.note(`复用方案：${s.reusePlan}`));
  }

  if (props.length) {
    B.push(P.h2('五、叙事道具'));
    for (const x of props) {
      B.push(P.p(`${x.id}　${x.name ?? ''}`));
      B.push(P.note(`承载：${x.function ?? ''}${(x.beatIds ?? []).length ? `　托起：${x.beatIds.join('、')}` : ''}`));
    }
  }

  B.push(P.h2(`${props.length ? '六' : '五'}、观看价值曲线`));
  for (const x of beats) {
    B.push(P.p(`${x.id}　第 ${x.episode} 集　【${x.weight === 'major' ? '大爆点' : '小爆点'}｜${x.value ?? ''}】${x.type ?? ''}`));
    B.push(P.note(`铺垫：${x.setup ?? ''}　兑现：${x.payoff ?? ''}`));
  }

  B.push(P.h2(`${props.length ? '七' : '六'}、分集梗概`));
  for (const e of eps) {
    B.push(P.h3(`第 ${e.ep} 集`));
    B.push(P.p(`梗概：${e.synopsis || '—'}`));
    B.push(P.p(`钩子：${e.hook || '—'}`));
    B.push(P.p(`悬念：${e.suspense || '—'}`));
    if ((e.sceneIds ?? []).length) B.push(P.note(`场景：${e.sceneIds.map(nameOfScene).join('、')}`));
    if ((e.characterIds ?? []).length) B.push(P.note(`人物：${e.characterIds.map(nameOfChar).join('、')}`));
    if (th(e.crowdPlan)) B.push(P.note(`同框方案：${e.crowdPlan}`));
    if (th(e.powerNote)) B.push(P.note(`能力说明：${e.powerNote}`));
    if ((e.warnings ?? []).length) B.push(P.note(`生成预警：${e.warnings.join('、')}`));
  }

  if (outPath) writeDocx(outPath, B);
  return B;
}

/* ------------------------------------------------------------------ */
/* assets —— 资产清单                                                   */
/* ------------------------------------------------------------------ */

export function renderAssets(doc) {
  const p = paramsOf(doc);
  const chars = doc?.characters ?? [];
  const scenes = doc?.scenes ?? [];
  const props = doc?.props ?? [];
  const eps = doc?.episodes ?? [];

  const epOf = (key, id) => eps.filter((e) => (e?.[key] ?? []).includes(id)).map((e) => e.ep);

  const L = [];
  L.push(`# 《${doc?.source ?? '未命名'}》｜资产清单`, '');
  L.push(`> 由脚本从大纲汇总，**不要手改**。规模：${p.episodes} 集 × ${p.targetSeconds} 秒。`, '');

  L.push('## 人物（C）', '');
  L.push('| 编号 | 姓名 | 档位 | 锚点 | 出现集数 | 备注 |');
  L.push('| --- | --- | --- | --- | --- | --- |');
  for (const c of chars) {
    const list = epOf('characterIds', c.id);
    L.push(`| ${c.id} | ${c.name ?? ''} | ${TIER_TAG[c.tier] ?? c.tier ?? ''} | ${ANCHOR_TAG[c.anchor] ?? c.anchor ?? ''} | ${list.length}（${list.slice(0, 6).join(',')}${list.length > 6 ? '…' : ''}） | ${c.role ?? ''} |`);
  }
  L.push('');

  L.push('## 场景（S）', '');
  L.push('| 编号 | 名称 | 主场景 | 出现集数 | 复用方案 |');
  L.push('| --- | --- | --- | --- | --- |');
  for (const s of scenes) {
    const list = epOf('sceneIds', s.id);
    L.push(`| ${s.id} | ${s.name ?? ''} | ${s.primary ? '✓' : ''} | ${list.length} | ${s.reusePlan ?? ''} |`);
  }
  L.push('');

  if (props.length) {
    L.push('## 道具（P）', '');
    L.push('| 编号 | 名称 | 承载什么 | 出现集数 |');
    L.push('| --- | --- | --- | --- |');
    for (const x of props) {
      L.push(`| ${x.id} | ${x.name ?? ''} | ${x.function ?? ''} | ${epOf('propIds', x.id).length} |`);
    }
    L.push('');
  }

  L.push('## 统计', '');
  L.push(`- 人物 ${chars.length}（主角组 ${chars.filter((c) => c.tier === 'lead').length} / 重要配角 ${chars.filter((c) => c.tier === 'support').length} / 功能性 ${chars.filter((c) => c.tier === 'functional').length}）`);
  L.push(`- 场景 ${scenes.length}（主场景 ${scenes.filter((s) => s.primary).length}，上限 ${p.maxPrimaryScenes}）`);
  L.push(`- 道具 ${props.length}（上限 ${p.maxProps}）`);
  L.push(`- 爽点 ${(doc?.beats ?? []).length}（大 ${(doc?.beats ?? []).filter((b) => b.weight === 'major').length}）`);
  L.push('');

  return L.join('\n').trimEnd() + '\n';
}

/* ------------------------------------------------------------------ */
/* CLI                                                                 */
/* ------------------------------------------------------------------ */

const USAGE = `无限轮回剧本 · 大纲工具（ir-outline）

用法：
  node ir-outline.mjs seed     <world.json>                      > outline.json
  node ir-outline.mjs validate <outline.json> [--stage skeleton|beats|full]
  node ir-outline.mjs checkup  <outline.json>
  node ir-outline.mjs render   <outline.json> --docx <输出.docx>
  node ir-outline.mjs render   <outline.json> --md
  node ir-outline.mjs assets   <outline.json>
  node ir-outline.mjs stats    <outline.json>

17 道质量门全部确定性检查，不调模型、不花额度。
--stage beats 是硬门：写分集之前必须过。
`;

function readJson(path) {
  let raw;
  try {
    raw = readFileSync(path, 'utf8');
  } catch {
    throw new Error(`读不到文件：${path}`);
  }
  try {
    return JSON.parse(raw);
  } catch (e) {
    throw new Error(`${path} 不是合法 JSON：${e.message}`);
  }
}

function flag(rest, name, fallback = null) {
  const i = rest.indexOf(name);
  return i >= 0 && rest[i + 1] && !rest[i + 1].startsWith('--') ? rest[i + 1] : fallback;
}

function main(argv) {
  const [cmd, ...rest] = argv;

  if (!cmd || cmd === '-h' || cmd === '--help') {
    console.log(USAGE);
    process.exit(cmd ? 0 : 1);
  }

  if (cmd === 'seed') {
    const [path] = rest;
    if (!path) throw new Error('用法：seed <world.json>');
    console.log(JSON.stringify(seedFromWorld(readJson(path)), null, 2));
    return;
  }

  if (cmd === 'validate' || cmd === 'checkup') {
    const [path] = rest;
    if (!path) throw new Error(`用法：${cmd} <outline.json> [--stage skeleton|beats|full]`);
    const doc = readJson(path);
    const stage = flag(rest, '--stage', 'full');
    const gates = gateReport(doc, stage);

    if (cmd === 'checkup') {
      for (const g of gates) {
        console.log(`${g.ok ? (g.skipped ? '·' : '✓') : '✗'} ${g.label}${!g.ok && g.detail ? ` — ${g.detail}` : ''}`);
      }
      const failed = gates.filter((g) => !g.ok).length;
      console.log(failed ? `\n✗ ${failed} 项未过` : '\n✓ 全部通过');
      if (failed) process.exit(1);
      return;
    }

    const problems = validateOutline(doc, stage);
    if (problems.length) {
      console.error(`✗ ${problems.length} 处违规（stage=${stage}）：\n`);
      for (const x of problems) console.error(`  ${x}`);
      process.exit(1);
    }
    const p = paramsOf(doc);
    console.log(`✓ ${p.episodes} 集 / ${(doc.characters ?? []).length} 人 / ${(doc.scenes ?? []).length} 景 / ${(doc.beats ?? []).length} 个爽点全部通过（stage=${stage}）`);
    return;
  }

  if (cmd === 'render') {
    const [path] = rest;
    if (!path) throw new Error('用法：render <outline.json> [--docx 输出.docx | --md]');
    const doc = readJson(path);

    if (rest.includes('--docx')) {
      const out = flag(rest, '--docx', null) ?? `${doc?.source || 'outline'}-大纲.docx`;
      const blocks = renderDocx(doc, out);
      console.log(`✓ 已生成 ${out}（${blocks.length} 段）`);
      return;
    }

    process.stdout.write(renderMarkdown(doc));
    return;
  }

  if (cmd === 'assets') {
    const [path] = rest;
    if (!path) throw new Error('用法：assets <outline.json>');
    process.stdout.write(renderAssets(readJson(path)));
    return;
  }

  if (cmd === 'stats') {
    const [path] = rest;
    if (!path) throw new Error('用法：stats <outline.json>');
    const doc = readJson(path);
    const p = paramsOf(doc);
    console.log(`集数 ${p.episodes}　时长 ${p.targetSeconds}s　题材 ${p.genre || '—'}`);
    console.log(`人物 ${(doc.characters ?? []).length}　场景 ${(doc.scenes ?? []).length}　道具 ${(doc.props ?? []).length}　爽点 ${(doc.beats ?? []).length}`);
    console.log(`核心商品 ${p.coreValue.join(' / ') || '—'}　主线 ${p.mainline ? '推进' : '不推进'}`);
    return;
  }

  throw new Error(`未知命令 ${cmd}\n\n${USAGE}`);
}

function isMainModule() {
  try {
    return import.meta.url === pathToFileURL(process.argv[1]).href;
  } catch {
    return false;
  }
}

if (isMainModule()) {
  try {
    main(process.argv.slice(2));
  } catch (e) {
    console.error(`✗ ${e.message}`);
    process.exit(1);
  }
}
