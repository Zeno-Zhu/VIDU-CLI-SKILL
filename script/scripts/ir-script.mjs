#!/usr/bin/env node
/**
 * ir-script.mjs —— 无限轮回剧本 · 逐集剧本校验与渲染
 *
 * 数据契约与确定性质量门设计改造自 eternityspring/shuohao-skills 的 novel-script（Apache-2.0）。
 * 格式规范来自《无限轮回宇宙·短剧共创 设定》第六章、第八章。
 *
 * 零依赖，Node >= 18。
 *   node ir-script.mjs seed     outline.json --eps 1-3 > script.json
 *   node ir-script.mjs validate script.json --outline outline.json
 *   node ir-script.mjs checkup  script.json [--outline outline.json]
 *   node ir-script.mjs render   script.json --md    --outline outline.json
 *   node ir-script.mjs render   script.json --shots --outline outline.json
 *   node ir-script.mjs stats    script.json
 */
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { writeDocx, P } from './docx.mjs';

/* ------------------------------------------------------------------ */
/* 常量                                                                */
/* ------------------------------------------------------------------ */

export const DEFAULTS = {
  charsPerSecond: 4.5,
  actionSeconds: 2.5,
  tolerance: 0.15,
  maxLineChars: 35,
  targetSeconds: 75,
  hookWindow: 4,
};

/** 动作描述必须是叙述体——台词只能进 line，混进 action 就没法计秒。 */
const QUOTE_RE = /[「」『』“”"]/;

/** 括号里的心理描写（软门，只提示不改判） */
const PSYCH_WORDS = ['心里', '内心', '心中', '想着', '心想', '暗想', '才明白', '终于知道', '意识到'];

const SENT_END = /[。！？…」』”"]$/;

const SKIP_OUTLINE = '未提供 outline.json，本门跳过（视为通过）';

/* ------------------------------------------------------------------ */
/* 工具                                                                */
/* ------------------------------------------------------------------ */

const r1 = (n) => Math.round(n * 10) / 10;
const th = (s) => typeof s === 'string' && s.trim().length > 0;

/** 台词字数：非空白字符（标点算时间——停顿也是时间） */
export const lineChars = (s) => String(s ?? '').replace(/\s/g, '').length;

export function paramsOf(doc) {
  return { ...DEFAULTS, ...(doc?.params ?? {}) };
}

export function slug(name) {
  const cleaned = String(name ?? '')
    .trim()
    .replace(/[\s/\\:*?"<>|·]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return cleaned || 'script';
}

/* ------------------------------------------------------------------ */
/* 统计                                                                */
/* ------------------------------------------------------------------ */

export function computeStats(doc) {
  const p = paramsOf(doc);
  const eps = Array.isArray(doc?.episodes) ? doc.episodes : [];

  const per = eps.map((ep) => {
    let scenes = 0;
    let lines = 0;
    let chars = 0;
    let actions = 0;
    for (const sc of ep?.scenes ?? []) {
      scenes += 1;
      for (const b of sc?.flow ?? []) {
        if (typeof b?.action === 'string' && b.action.trim()) actions += 1;
        else if (typeof b?.line === 'string') {
          lines += 1;
          chars += lineChars(b.line);
        }
      }
    }
    const lineSec = chars / p.charsPerSecond;
    const actSec = actions * p.actionSeconds;
    return {
      ep: ep?.ep,
      target: ep?.targetSeconds > 0 ? ep.targetSeconds : p.targetSeconds,
      scenes,
      lines,
      chars,
      actions,
      lineSec: r1(lineSec),
      actSec: r1(actSec),
      est: r1(lineSec + actSec),
    };
  });

  const totals = per.reduce(
    (a, x) => ({
      episodes: a.episodes + 1,
      scenes: a.scenes + x.scenes,
      lines: a.lines + x.lines,
      chars: a.chars + x.chars,
      actions: a.actions + x.actions,
      estSeconds: a.estSeconds + x.est,
      targetSeconds: a.targetSeconds + x.target,
    }),
    { episodes: 0, scenes: 0, lines: 0, chars: 0, actions: 0, estSeconds: 0, targetSeconds: 0 },
  );

  totals.estSeconds = r1(totals.estSeconds);
  totals.targetSeconds = r1(totals.targetSeconds);

  return { params: p, episodes: per, totals };
}

/* ------------------------------------------------------------------ */
/* 质量门（12 道）                                                      */
/* ------------------------------------------------------------------ */

export function gateReport(doc, ctx = {}) {
  const gates = [];
  const add = (id, label, ok, detail = '', soft = false) =>
    gates.push({ id, label, ok, detail, soft });

  const eps = Array.isArray(doc?.episodes) ? doc.episodes : [];
  const p = paramsOf(doc);
  const stats = computeStats(doc);

  const bad = {
    duration: [], lineLen: [], speaker: [], hook: [], hookOpen: [],
    noAction: [], prose: [], beats: [], chars: [], scenes: [], format: [], psych: [],
  };

  for (const [i, ep] of eps.entries()) {
    const st = stats.episodes[i];
    const label = `第 ${ep?.ep} 集`;
    const target = st.target;

    // ---- 1 时长预算：写超写欠都在这层拦 ----
    const lo = target * (1 - p.tolerance);
    const hi = target * (1 + p.tolerance);
    if (st.est < lo) bad.duration.push(`${label}欠 ${r1(lo - st.est)} 秒（估 ${st.est}s / 目标 ${target}s）`);
    if (st.est > hi) bad.duration.push(`${label}超 ${r1(st.est - hi)} 秒（估 ${st.est}s / 目标 ${target}s）`);

    // ---- 4 钩子与悬念落纸 ----
    if (!th(ep?.hook) || !th(ep?.cliff)) bad.hook.push(label);

    // ---- 11 场景头四要素（集名） ----
    if (!th(ep?.title)) bad.format.push(`${label}缺 title（集名）`);

    // ---- 5 钩子不是标签是第一拍 ----
    const hb = ep?.hookBeat;
    if (!Array.isArray(hb) || hb.length !== 2 || !Number.isInteger(hb[0]) || !Number.isInteger(hb[1])) {
      bad.hookOpen.push(`${label}缺 hookBeat（[场, 拍]，认领钩子具象的位置）`);
    } else {
      const scene = ep?.scenes?.[hb[0] - 1];
      if (!scene || hb[1] < 1 || hb[1] > (scene.flow ?? []).length) {
        bad.hookOpen.push(`${label}的 hookBeat [${hb[0]}, ${hb[1]}] 指向不存在的节拍`);
      } else {
        let pos = hb[1];
        for (let k = 0; k < hb[0] - 1; k += 1) pos += (ep.scenes[k]?.flow ?? []).length;
        if (pos > p.hookWindow) {
          bad.hookOpen.push(`${label}的钩子落在全集第 ${pos} 拍，超出前 ${p.hookWindow} 拍——冷开场先给钩子具象`);
        }
      }
    }

    for (const sc of ep?.scenes ?? []) {
      const cast = new Set(sc?.characters ?? []);
      let hasAction = false;

      // ---- 11 场景头四要素（地点/时间/内外） ----
      const miss = [];
      if (!th(sc?.title)) miss.push('title');
      if (!th(sc?.time)) miss.push('time');
      if (!th(sc?.inOut)) miss.push('inOut');
      if (!th(sc?.sceneId)) miss.push('sceneId');
      if (miss.length) bad.format.push(`${label} ${sc?.sceneId ?? '?'} 缺 ${miss.join('/')}`);

      for (const b of sc?.flow ?? []) {
        if (typeof b?.action === 'string' && b.action.trim()) {
          hasAction = true;
          // ---- 7 动作叙述体 ----
          if (QUOTE_RE.test(b.action)) bad.prose.push(`${label} ${sc?.sceneId ?? '?'}`);
        }

        if (typeof b?.line === 'string') {
          // ---- 2 单句字数 ----
          if (lineChars(b.line) > p.maxLineChars) {
            bad.lineLen.push(`${label}「${String(b.line).slice(0, 12)}…」${lineChars(b.line)} 字`);
          }
          // ---- 3 说话人合法 ----
          if (b.speaker === 'VO' || b.speaker === '画外') {
            bad.speaker.push(`${label} ${sc?.sceneId ?? '?'} 用了 speaker:"${b.speaker}"——请改写角色 id + mode:"vo"/"off"`);
          } else if (!cast.has(b.speaker)) {
            bad.speaker.push(`${label} ${sc?.sceneId ?? '?'} 的「${b.speaker}」不在本场人物里`);
          }
          // ---- 12 括号心理描写（软） ----
          if (th(b.delivery)) {
            const hit = PSYCH_WORDS.find((w) => b.delivery.includes(w));
            if (hit) bad.psych.push(`${label} ${sc?.sceneId ?? '?'}「${b.delivery.slice(0, 14)}」含「${hit}」`);
          }
        }
      }

      // ---- 6 每场至少一个动作节拍 ----
      if ((sc?.flow ?? []).length > 0 && !hasAction) bad.noAction.push(`${label} ${sc?.sceneId ?? '?'}`);
    }
  }

  // ---- 需要上游对账的门 ----
  const outline = ctx.outline ?? null;

  if (outline) {
    const charIds = new Set((outline.characters ?? []).map((c) => c.id));
    const sceneIds = new Set((outline.scenes ?? []).map((s) => s.id));
    const propIds = new Set((outline.props ?? []).map((x) => x.id));

    for (const ep of eps) {
      for (const sc of ep?.scenes ?? []) {
        if (!sceneIds.has(sc?.sceneId)) {
          bad.scenes.push(`第 ${ep.ep} 集引用了不存在的场景 ${sc?.sceneId}`);
        }
        for (const id of sc?.characters ?? []) {
          if (!charIds.has(id)) bad.chars.push(`第 ${ep.ep} 集 ${sc?.sceneId ?? '?'} 的 ${id}`);
        }
        for (const pid of sc?.props ?? []) {
          if (!propIds.has(pid)) bad.scenes.push(`第 ${ep.ep} 集引用了不存在的道具 ${pid}`);
        }
      }
      // ---- 8 爽点认领 ----
      const due = [...new Set((outline.beats ?? []).filter((b) => b.episode === ep.ep).map((b) => b.type))];
      const claimed = new Set(ep?.beatsClaimed ?? []);
      for (const t of due) if (!claimed.has(t)) bad.beats.push(`第 ${ep.ep} 集缺「${t}」`);
    }
  }

  add('duration', `每集时长在目标 ±${Math.round(p.tolerance * 100)}% 内`, eps.length > 0 && bad.duration.length === 0, bad.duration.join('；'));
  add('line-length', `单句台词 ≤ ${p.maxLineChars} 字`, bad.lineLen.length === 0, bad.lineLen.join('；'));
  add('speaker', '说话人在本场人物里（voice-over 用 mode 标注）', bad.speaker.length === 0, bad.speaker.join('；'));
  add('hook-cliff', '每集开场钩子与结尾悬念都落在纸面', eps.length > 0 && bad.hook.length === 0, bad.hook.join('；'));
  add('hook-open', `钩子的具象在全集前 ${p.hookWindow} 拍内兑现（hookBeat 认领）`, eps.length > 0 && bad.hookOpen.length === 0, bad.hookOpen.join('；'));
  add('has-action', '每场至少一个动作节拍——纯对白的场是广播剧', eps.length > 0 && bad.noAction.length === 0, bad.noAction.join('；'));
  add('action-prose', '动作描述叙述体，台词只进 line 字段', bad.prose.length === 0, bad.prose.join('；'));
  add('beats-claimed', '大纲爽点逐集认领', bad.beats.length === 0, outline ? bad.beats.join('；') : SKIP_OUTLINE);
  add('refs-characters', '角色引用对账大纲', bad.chars.length === 0, outline ? bad.chars.join('；') : SKIP_OUTLINE);
  add('refs-scenes', '场景／道具引用对账大纲', bad.scenes.length === 0, outline ? bad.scenes.join('；') : SKIP_OUTLINE);
  add('format-ready', '场景头四要素齐全（集名 + 地点/时间/内外）', eps.length > 0 && bad.format.length === 0, bad.format.join('；'));
  add('delivery-psych', '括号里没有心理描写（软门，只提示不拦）', bad.psych.length === 0, bad.psych.join('；'), true);

  return gates;
}

/* ------------------------------------------------------------------ */
/* validate                                                            */
/* ------------------------------------------------------------------ */

export function validateScript(doc, ctx = {}) {
  return gateReport(doc, ctx)
    .filter((g) => !g.ok && !g.soft)
    .map((g) => `${g.label}${g.detail ? ` — ${g.detail}` : ''}`);
}

/* ------------------------------------------------------------------ */
/* seed                                                                */
/* ------------------------------------------------------------------ */

export function seedFromOutline(outline, epRange = null) {
  const p = paramsOf(outline?.params ?? {});
  const per = outline?.params?.targetSeconds > 0 ? outline.params.targetSeconds : p.targetSeconds;
  const inRange = (n) => !epRange || (n >= epRange[0] && n <= epRange[1]);

  const episodes = (outline?.episodes ?? [])
    .filter((e) => inRange(e.ep))
    .map((e) => ({
      ep: e.ep,
      title: '',
      targetSeconds: per,
      hook: e.hook ?? '',
      cliff: e.suspense ?? '',
      hookBeat: null,
      beatsClaimed: [...new Set((outline.beats ?? []).filter((b) => b.episode === e.ep).map((b) => b.type))],
      scenes: [],
      seedNote: `大纲梗概：${e.synopsis ?? ''}　候选场景：${(e.sceneIds ?? []).join('、')}　人物：${(e.characterIds ?? []).join('、')}`,
    }));

  return { title: outline?.source ?? '', source: outline?.source ?? '', episodes };
}

/* ------------------------------------------------------------------ */
/* render —— Markdown（中国短剧 △ 格式）                                 */
/* ------------------------------------------------------------------ */

function joinActions(list) {
  return list.reduce((acc, t) => {
    if (!acc) return t;
    return SENT_END.test(acc) ? acc + t : `${acc}，${t}`;
  }, '');
}

function lineText(b, nameOf) {
  const name = nameOf(b.speaker);
  const parts = [];
  if (b.mode === 'vo') parts.push('VO');
  else if (b.mode === 'off') parts.push('画外');
  if (th(b.delivery)) parts.push(String(b.delivery).trim());
  const paren = parts.length ? `（${parts.join('，')}）` : '';
  return `${name}${paren}：${String(b.line ?? '').trim()}`;
}

export function renderMarkdown(doc, ctx = {}) {
  const charMap = new Map((ctx.outline?.characters ?? []).map((c) => [c.id, c.name]));
  const nameOf = (id) => charMap.get(id) ?? id ?? '?';

  const out = [];
  if (th(doc?.title)) {
    out.push(`# 《${doc.title}》`);
    out.push('');
  }

  for (const ep of doc?.episodes ?? []) {
    out.push(`第${ep.ep}集·${th(ep.title) ? ep.title : '未命名'}`);
    out.push('');

    (ep.scenes ?? []).forEach((sc, j) => {
      out.push(`${ep.ep}-${j + 1}：[${th(sc.time) ? sc.time : '日'}] ${th(sc.title) ? sc.title : '未命名场景'} ${th(sc.inOut) ? sc.inOut : '内'}`);
      out.push(`人物：${(sc.characters ?? []).map(nameOf).join('、') || '（空镜）'}`);
      out.push('');

      let buf = [];
      const flush = () => {
        if (!buf.length) return;
        out.push(`△${joinActions(buf)}`);
        buf = [];
      };

      for (const b of sc.flow ?? []) {
        if (typeof b?.action === 'string' && b.action.trim()) {
          buf.push(b.action.trim());
          continue;
        }
        if (typeof b?.line === 'string') {
          flush();
          out.push(lineText(b, nameOf));
        }
      }
      flush();
      out.push('');
    });
  }

  return out.join('\n').replace(/\n{3,}/g, '\n\n').trimEnd() + '\n';
}

/* ------------------------------------------------------------------ */
/* render —— DOCX（交付件）                                              */
/* ------------------------------------------------------------------ */

export function renderDocx(doc, ctx = {}, outPath = null) {
  const charMap = new Map((ctx.outline?.characters ?? []).map((c) => [c.id, c.name]));
  const nameOf = (id) => charMap.get(id) ?? id ?? '?';
  const blocks = [];

  if (th(doc?.title)) blocks.push(P.title(`《${doc.title}》`));

  for (const ep of doc?.episodes ?? []) {
    blocks.push(P.ep(`第${ep.ep}集·${th(ep.title) ? ep.title : '未命名'}`));

    (ep.scenes ?? []).forEach((sc, j) => {
      blocks.push(P.scene(`${ep.ep}-${j + 1}：[${th(sc.time) ? sc.time : '日'}] ${th(sc.title) ? sc.title : '未命名场景'} ${th(sc.inOut) ? sc.inOut : '内'}`));
      blocks.push(P.cast(`人物：${(sc.characters ?? []).map(nameOf).join('、') || '（空镜）'}`));

      let buf = [];
      const flush = () => {
        if (!buf.length) return;
        blocks.push(P.action(joinActions(buf)));
        buf = [];
      };

      for (const b of sc.flow ?? []) {
        if (typeof b?.action === 'string' && b.action.trim()) {
          buf.push(b.action.trim());
          continue;
        }
        if (typeof b?.line === 'string') {
          flush();
          const parts = [];
          if (b.mode === 'vo') parts.push('VO');
          else if (b.mode === 'off') parts.push('画外');
          if (th(b.delivery)) parts.push(String(b.delivery).trim());
          blocks.push(P.line(nameOf(b.speaker), parts.join('，'), String(b.line).trim()));
        }
      }
      flush();
    });
  }

  if (outPath) writeDocx(outPath, blocks);
  return blocks;
}

/* ------------------------------------------------------------------ */
/* render —— shots.json（下游交接件）                                    */
/* ------------------------------------------------------------------ */

export function renderShots(doc, ctx = {}) {
  const charMap = new Map((ctx.outline?.characters ?? []).map((c) => [c.id, c.name]));
  const p = paramsOf(doc);
  const stats = computeStats(doc);

  return {
    title: doc?.title ?? '',
    params: { charsPerSecond: p.charsPerSecond, actionSeconds: p.actionSeconds, tolerance: p.tolerance },
    episodes: (doc?.episodes ?? []).map((ep, i) => {
      const st = stats.episodes[i];
      return {
        ep: ep.ep,
        title: ep.title ?? '',
        targetSeconds: st.target,
        estSeconds: st.est,
        scenes: (ep.scenes ?? []).map((sc) => {
          let chars = 0;
          let lines = 0;
          let actions = 0;
          for (const b of sc.flow ?? []) {
            if (typeof b?.action === 'string' && b.action.trim()) actions += 1;
            else if (typeof b?.line === 'string') { lines += 1; chars += lineChars(b.line); }
          }
          return {
            sceneId: sc.sceneId,
            title: sc.title ?? '',
            time: sc.time ?? '',
            inOut: sc.inOut ?? '',
            characters: (sc.characters ?? []).map((id) => charMap.get(id) ?? id),
            props: sc.props ?? [],
            lines,
            actions,
            beats: lines + actions,
            estSeconds: r1(chars / p.charsPerSecond + actions * p.actionSeconds),
          };
        }),
      };
    }),
  };
}

/* ------------------------------------------------------------------ */
/* CLI                                                                 */
/* ------------------------------------------------------------------ */

const USAGE = `无限轮回剧本 · 逐集剧本工具（ir-script）

用法：
  node ir-script.mjs seed     <outline.json> [--eps 1-3]           > script.json
  node ir-script.mjs validate <script.json> [--outline outline.json]
  node ir-script.mjs checkup  <script.json> [--outline outline.json]
  node ir-script.mjs render   <script.json> --docx <输出.docx> [--outline outline.json]
  node ir-script.mjs render   <script.json> --md    [--outline outline.json]
  node ir-script.mjs render   <script.json> --shots [--outline outline.json]
  node ir-script.mjs stats    <script.json>

12 道质量门全部确定性检查，不调模型、不花额度。
默认口径：单集 75 秒 ±15%，4.5 字/秒，2.5 秒/拍，单句 ≤35 字，钩子前 4 拍。
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

function loadCtx(rest) {
  const o = flag(rest, '--outline');
  return { outline: o ? readJson(o) : null };
}

function main(argv) {
  const [cmd, ...rest] = argv;

  if (!cmd || cmd === '-h' || cmd === '--help') {
    console.log(USAGE);
    process.exit(cmd ? 0 : 1);
  }

  if (cmd === 'seed') {
    const [path] = rest;
    if (!path) throw new Error('用法：seed <outline.json> [--eps 1-6]');
    const range = flag(rest, '--eps');
    let epRange = null;
    if (range) {
      const m = String(range).match(/^(\d+)-(\d+)$/) ?? String(range).match(/^(\d+)$/);
      if (!m) throw new Error('--eps 形如 3 或 1-6');
      epRange = m[2] ? [Number(m[1]), Number(m[2])] : [Number(m[1]), Number(m[1])];
    }
    console.log(JSON.stringify(seedFromOutline(readJson(path), epRange), null, 2));
    return;
  }

  if (cmd === 'validate' || cmd === 'checkup') {
    const [path] = rest;
    if (!path) throw new Error(`用法：${cmd} <script.json> [--outline o.json]`);
    const doc = readJson(path);
    const ctx = loadCtx(rest);
    if (!ctx.outline) {
      console.error('⚠️ 没给 --outline，跳过爽点认领与引用对账两道门');
    }

    if (cmd === 'checkup') {
      const gates = gateReport(doc, ctx);
      for (const g of gates) {
        const mark = g.ok ? '✓' : g.soft ? '!' : '✗';
        console.log(`${mark} ${g.label}${!g.ok && g.detail ? ` — ${g.detail}` : ''}`);
      }
      const failed = gates.filter((g) => !g.ok && !g.soft).length;
      const warned = gates.filter((g) => !g.ok && g.soft).length;
      console.log(failed ? `\n✗ ${failed} 项未过${warned ? `（另有 ${warned} 项提示）` : ''}` : `\n✓ 全部通过${warned ? `（${warned} 项提示）` : ''}`);
      if (failed) process.exit(1);
      return;
    }

    const problems = validateScript(doc, ctx);
    if (problems.length) {
      console.error(`✗ ${problems.length} 处违规：\n`);
      for (const x of problems) console.error(`  ${x}`);
      process.exit(1);
    }
    const st = computeStats(doc);
    console.log(`✓ ${st.totals.episodes} 集 / ${st.totals.scenes} 场 / ${st.totals.lines} 句台词全部通过校验（预估 ${st.totals.estSeconds}s / 目标 ${st.totals.targetSeconds}s）`);
    return;
  }

  if (cmd === 'render') {
    const [path] = rest;
    if (!path) throw new Error('用法：render <script.json> [--docx 输出.docx | --md | --shots] [--outline o.json]');
    const doc = readJson(path);
    const ctx = loadCtx(rest);

    if (rest.includes('--docx')) {
      const out = flag(rest, '--docx', null) ?? `${slug(doc?.title || 'script')}-剧本.docx`;
      const blocks = renderDocx(doc, ctx, out);
      console.log(`✓ 已生成 ${out}（${blocks.length} 段）`);
      return;
    }

    if (rest.includes('--shots')) {
      console.log(JSON.stringify(renderShots(doc, ctx), null, 2));
    } else {
      process.stdout.write(renderMarkdown(doc, ctx));
    }
    return;
  }

  if (cmd === 'stats') {
    const [path] = rest;
    if (!path) throw new Error('用法：stats <script.json>');
    const st = computeStats(readJson(path));
    console.log(`集数 ${st.totals.episodes}　场次 ${st.totals.scenes}　台词 ${st.totals.lines} 句　动作 ${st.totals.actions} 拍`);
    console.log(`预估 ${st.totals.estSeconds}s / 目标 ${st.totals.targetSeconds}s`);
    for (const e of st.episodes) {
      console.log(`  第 ${e.ep} 集：${e.est}s / ${e.target}s（台词 ${e.lineSec}s + 动作 ${e.actSec}s，${e.scenes} 场 ${e.lines} 句 ${e.actions} 拍）`);
    }
    return;
  }

  if (cmd === 'slug') {
    console.log(slug(rest[0]));
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
