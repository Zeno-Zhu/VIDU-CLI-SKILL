#!/usr/bin/env node
/**
 * selftest.mjs —— 不调模型、不花额度的确定性自测
 *
 * 每一道质量门都必须有一个「故意写违规 → 确认被拦」的用例。
 * 改完脚本先跑这个：node scripts/selftest.mjs
 */
import { readFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { gateReport as scriptGates, validateScript, lineChars, computeStats, renderMarkdown, renderShots } from './ir-script.mjs';
import { gateReport as outlineGates, validateOutline, paramsOf, dynamicSceneCap, renderMarkdown as outlineMd } from './ir-outline.mjs';
import { buildDocx, writeDocx, P } from './docx.mjs';

let pass = 0;
const fails = [];

function ok(cond, name) {
  if (cond) pass += 1;
  else fails.push(name);
}
function eq(actual, expected, name) {
  ok(actual === expected, `${name}（期望 ${expected}，实际 ${actual}）`);
}

const clone = (o) => JSON.parse(JSON.stringify(o));

/* ------------------------------------------------------------------ */
/* 剧本夹具                                                            */
/* ------------------------------------------------------------------ */

function flowOK() {
  const f = [{ action: '他推门进来，把包放在桌上。' }];
  for (let i = 0; i < 12; i += 1) {
    f.push({ speaker: 'C01', line: '这是一句十八个字左右的测试台词内容。' });
    f.push({ action: '他把东西挪了一下位置。' });
  }
  return f;
}

function scriptBase() {
  return {
    title: '测试剧',
    source: '测试剧',
    params: {},
    episodes: [
      {
        ep: 1,
        title: '测试集',
        targetSeconds: 75,
        hook: '开场钩子',
        cliff: '结尾悬念',
        hookBeat: [1, 1],
        beatsClaimed: ['打脸'],
        scenes: [
          {
            sceneId: 'S01',
            title: '办公室',
            time: '日',
            inOut: '内',
            characters: ['C01'],
            props: [],
            flow: flowOK(),
          },
        ],
      },
    ],
  };
}

function scriptOutline() {
  return {
    characters: [{ id: 'C01', name: '万集' }],
    scenes: [{ id: 'S01', name: '办公室' }],
    props: [],
    beats: [{ id: 'B01', type: '打脸', weight: 'major', episode: 1, value: '爽' }],
  };
}

const sGate = (doc, id, ctx = { outline: scriptOutline() }) => scriptGates(doc, ctx).find((g) => g.id === id);

/* ------------------------------------------------------------------ */
/* 剧本 12 门                                                           */
/* ------------------------------------------------------------------ */

// 基线必须全过
eq(validateScript(scriptBase(), { outline: scriptOutline() }).length, 0, '剧本基线应全部通过');

// 1 duration
{
  const d = clone(scriptBase());
  d.episodes[0].scenes[0].flow = d.episodes[0].scenes[0].flow.slice(0, 8);
  ok(!sGate(d, 'duration').ok, 'duration 应拦住过短的一集');
}
{
  const d = clone(scriptBase());
  for (let i = 0; i < 30; i += 1) d.episodes[0].scenes[0].flow.push({ action: '他又走了一步。' });
  ok(!sGate(d, 'duration').ok, 'duration 应拦住过长的一集');
}

// 2 line-length
{
  const d = clone(scriptBase());
  d.episodes[0].scenes[0].flow[1].line = '这一句台词特别特别长'.repeat(4);
  ok(lineChars(d.episodes[0].scenes[0].flow[1].line) > 35, '夹具长度应超过 35 字');
  ok(!sGate(d, 'line-length').ok, 'line-length 应拦住超长单句');
}

// 3 speaker
{
  const d = clone(scriptBase());
  d.episodes[0].scenes[0].flow[1].speaker = 'C99';
  ok(!sGate(d, 'speaker').ok, 'speaker 应拦住不在本场的说话人');
}
{
  const d = clone(scriptBase());
  d.episodes[0].scenes[0].flow[1].speaker = 'VO';
  ok(!sGate(d, 'speaker').ok, 'speaker 应拦住老式 speaker:"VO" 写法');
}

// 4 hook-cliff
{
  const d = clone(scriptBase());
  d.episodes[0].hook = '';
  ok(!sGate(d, 'hook-cliff').ok, 'hook-cliff 应拦住空钩子');
}

// 5 hook-open
{
  const d = clone(scriptBase());
  d.episodes[0].hookBeat = [1, 6];
  ok(!sGate(d, 'hook-open').ok, 'hook-open 应拦住超出前 4 拍的钩子');
}
{
  const d = clone(scriptBase());
  d.episodes[0].hookBeat = [1, 99];
  ok(!sGate(d, 'hook-open').ok, 'hook-open 应拦住指向不存在节拍');
}

// 6 has-action
{
  const d = clone(scriptBase());
  d.episodes[0].scenes[0].flow = d.episodes[0].scenes[0].flow.filter((b) => b.line);
  ok(!sGate(d, 'has-action').ok, 'has-action 应拦住纯对白的场');
}

// 7 action-prose
{
  const d = clone(scriptBase());
  d.episodes[0].scenes[0].flow.push({ action: '他说「我不干」。' });
  ok(!sGate(d, 'action-prose').ok, 'action-prose 应拦住动作里的引号台词');
}

// 8 beats-claimed
{
  const d = clone(scriptBase());
  d.episodes[0].beatsClaimed = [];
  ok(!sGate(d, 'beats-claimed').ok, 'beats-claimed 应拦住没认领的爽点');
  d.episodes[0].beatsClaimed = ['打脸'];
  ok(sGate(d, 'beats-claimed').ok, 'beats-claimed 认领后应通过');
}

// 9 refs-characters
{
  const d = clone(scriptBase());
  d.episodes[0].scenes[0].characters = ['C01', 'C77'];
  d.episodes[0].scenes[0].flow[1].speaker = 'C77';
  ok(!sGate(d, 'refs-characters').ok, 'refs-characters 应拦住大纲里没有的角色');
}

// 10 refs-scenes
{
  const d = clone(scriptBase());
  d.episodes[0].scenes[0].sceneId = 'S99';
  ok(!sGate(d, 'refs-scenes').ok, 'refs-scenes 应拦住大纲里没有的场景');
}

// 11 format-ready
{
  const d = clone(scriptBase());
  delete d.episodes[0].scenes[0].time;
  ok(!sGate(d, 'format-ready').ok, 'format-ready 应拦住缺时间的场景头');
}
{
  const d = clone(scriptBase());
  d.episodes[0].title = '';
  ok(!sGate(d, 'format-ready').ok, 'format-ready 应拦住缺集名');
}

// 12 delivery-psych 是软门：报警但不拦
{
  const d = clone(scriptBase());
  d.episodes[0].scenes[0].flow[1].delivery = '心里明白了一切';
  const g = sGate(d, 'delivery-psych');
  ok(!g.ok && g.soft, 'delivery-psych 应报警且标记为软门');
  eq(validateScript(d, { outline: scriptOutline() }).length, 0, '软门不应拦下 validate');
}

// 统计与渲染
{
  const st = computeStats(scriptBase());
  eq(st.totals.episodes, 1, 'computeStats 集数');
  eq(st.totals.scenes, 1, 'computeStats 场数');
  ok(st.episodes[0].est > 63 && st.episodes[0].est < 87, `computeStats 预估时长应在容差内（${st.episodes[0].est}）`);
}
{
  const md = renderMarkdown(scriptBase(), { outline: scriptOutline() });
  ok(md.includes('第1集·测试集'), 'render md 应输出集标题');
  ok(md.includes('1-1：[日] 办公室 内'), 'render md 应输出标准场景头');
  ok(md.includes('人物：万集'), 'render md 应把 C01 显示成万集');
  ok(md.includes('△'), 'render md 应输出 △ 动作');
  ok(!md.includes('\n\n\n'), 'render md 不应出现连续空行');
}
{
  // 连续动作合并成一条 △
  const d = clone(scriptBase());
  d.episodes[0].scenes[0].flow = [
    { action: '他推门进来。' },
    { action: '他把包放在桌上。' },
    { speaker: 'C01', line: '我来了。' },
  ];
  const md = renderMarkdown(d, { outline: scriptOutline() });
  ok(md.includes('△他推门进来。他把包放在桌上。'), 'render md 应把连续动作合并成一条 △');
}
{
  const d = clone(scriptBase());
  d.episodes[0].scenes[0].flow[3] = { speaker: 'C01', mode: 'vo', line: '心声。' };
  const md = renderMarkdown(d, { outline: scriptOutline() });
  ok(md.includes('万集（VO）：心声。'), 'render md 应输出 VO 格式');
  d.episodes[0].scenes[0].flow[3] = { speaker: 'C01', mode: 'off', line: '门外有人。' };
  const md2 = renderMarkdown(d, { outline: scriptOutline() });
  ok(md2.includes('万集（画外）：门外有人。'), 'render md 应输出画外格式');
}
{
  const shots = renderShots(scriptBase(), { outline: scriptOutline() });
  eq(shots.episodes.length, 1, 'shots 集数');
  ok(!JSON.stringify(shots).includes('镜头'), 'shots 里不应出现镜号相关字段');
}

/* ------------------------------------------------------------------ */
/* 大纲 17 门                                                           */
/* ------------------------------------------------------------------ */

function outlineBase() {
  const eps = [1, 2, 3, 4, 5, 6].map((i) => ({
    ep: i,
    synopsis: '这一集发生了某件事。',
    hook: '钩子',
    suspense: '悬念',
    sceneIds: ['S01'],
    characterIds: i === 1 ? ['C01', 'C02'] : ['C01'],
    propIds: [],
    crowdPlan: '',
    warnings: [],
  }));
  return {
    source: '测试剧',
    origin: 'original',
    params: { episodes: 6, targetSeconds: 75, genre: '喜剧', adaptMode: '抽核', coreValue: ['笑'], mainline: false, thresholds: {} },
    adaptation: { core: '核心', keep: [{ what: 'a', why: 'b' }], cut: [], merge: [], risks: [] },
    characters: [
      { id: 'C01', name: '万集', role: '男主', tier: 'lead', anchor: 'base:wanji', arc: 'x', from: ['原创'] },
      { id: 'C02', name: '苏薇', role: '女主', tier: 'lead', anchor: 'base:suwei', arc: 'y', from: ['原创'] },
    ],
    scenes: [{ id: 'S01', name: '办公室', primary: true }],
    props: [],
    beats: [1, 2, 3, 4, 5, 6].map((i) => ({
      id: `B0${i}`, type: '爽', weight: i === 3 ? 'major' : 'minor', episode: i, value: '笑', setup: 's', payoff: 'p',
    })),
    episodes: eps,
  };
}

const oGate = (doc, id) => outlineGates(doc, 'full').find((g) => g.id === id);

eq(validateOutline(outlineBase(), 'full').length, 0, '大纲基线应全部通过');

// 1 characters-lead
{
  const d = clone(outlineBase());
  d.characters.forEach((c) => { c.tier = 'support'; });
  ok(!oGate(d, 'characters-lead').ok, 'characters-lead 应拦住没有主角组');
}
{
  const d = clone(outlineBase());
  for (let i = 0; i < 5; i += 1) d.characters.push({ id: `C1${i}`, name: `配角${i}`, role: 'x', tier: 'lead', anchor: 'local', arc: 'x', from: ['原创'] });
  ok(!oGate(d, 'characters-lead').ok, 'characters-lead 应拦住主角组超过 5 人');
}

// 2 characters-support
{
  const d = clone(outlineBase());
  for (let i = 0; i < 11; i += 1) d.characters.push({ id: `C2${i}`, name: `配${i}`, role: '', tier: 'support', anchor: 'local', arc: 'x', from: ['原创'] });
  ok(!oGate(d, 'characters-support').ok, 'characters-support 应拦住超过 10 人');
}

// 3 characters-functional
{
  const d = clone(outlineBase());
  for (let i = 0; i < 11; i += 1) d.characters.push({ id: `C3${i}`, name: `功能${i}`, role: '', tier: 'functional', anchor: 'local', from: ['原创'] });
  ok(!oGate(d, 'characters-functional').ok, 'characters-functional 应拦住超过 10 人');
}

// 4 scenes-cap
{
  eq(dynamicSceneCap(6), 5, 'dynamicSceneCap(6) 应为 5');
  eq(dynamicSceneCap(60), 10, 'dynamicSceneCap(60) 应为 10');
  eq(dynamicSceneCap(200), 15, 'dynamicSceneCap(200) 应封顶 15');
  const d = clone(outlineBase());
  for (let i = 0; i < 6; i += 1) d.scenes.push({ id: `S1${i}`, name: `景${i}`, primary: true });
  ok(!oGate(d, 'scenes-cap').ok, 'scenes-cap 应拦住主场景超上限');
}

// 5 scene-reuse
{
  const d = clone(outlineBase());
  d.scenes.push({ id: 'S02', name: '车库', primary: false });
  d.episodes[2].sceneIds = ['S02'];
  ok(!oGate(d, 'scene-reuse').ok, 'scene-reuse 应拦住一次性场景缺 reusePlan');
  d.scenes[1].reusePlan = '复用 S01';
  ok(oGate(d, 'scene-reuse').ok, 'scene-reuse 补了 reusePlan 应通过');
}

// 6 props-cap
{
  const d = clone(outlineBase());
  for (let i = 0; i < 9; i += 1) d.props.push({ id: `P0${i}`, name: `道具${i}`, function: 'f', beatIds: [] });
  ok(!oGate(d, 'props-cap').ok, 'props-cap 应拦住超过 8 件道具');
}

// 7 beat-gap
{
  const d = clone(outlineBase());
  d.beats = [
    { id: 'B01', type: 'a', weight: 'minor', episode: 1, value: '笑', setup: 's', payoff: 'p' },
    { id: 'B02', type: 'b', weight: 'major', episode: 6, value: '笑', setup: 's', payoff: 'p' },
  ];
  ok(!oGate(d, 'beat-gap').ok, 'beat-gap 应拦住中间空 5 集');
}
{
  const d = clone(outlineBase());
  d.beats.forEach((b) => { b.episode = 1; });
  ok(!oGate(d, 'beat-gap').ok, 'beat-gap 应拦住结尾真空');
}

// 8 beat-major
{
  const d = clone(outlineBase());
  d.beats.forEach((b) => { b.weight = 'minor'; });
  ok(!oGate(d, 'beat-major').ok, 'beat-major 应拦住没有大爆点');
}
{
  const d = clone(outlineBase());
  d.beats.forEach((b) => { b.weight = b.episode === 6 ? 'major' : 'minor'; });
  ok(!oGate(d, 'beat-major').ok, 'beat-major 应拦住大爆点只落在最后一集');
}

// 9 hook-ep1
{
  const d = clone(outlineBase());
  d.episodes[0].hook = '';
  ok(!oGate(d, 'hook-ep1').ok, 'hook-ep1 应拦住第 1 集没钩子');
}

// 10 episode-three
{
  const d = clone(outlineBase());
  d.episodes[1].synopsis = '';
  ok(!oGate(d, 'episode-three').ok, 'episode-three 应拦住缺梗概');
}

// 11 crowd-plan
{
  const d = clone(outlineBase());
  d.episodes[2].characterIds = ['C01', 'C02', 'C03'];
  d.characters.push({ id: 'C03', name: '反派', role: '', tier: 'support', anchor: 'local', arc: 'x', from: ['原创'] });
  ok(!oGate(d, 'crowd-plan').ok, 'crowd-plan 应拦住三人同框没方案');
  d.episodes[2].crowdPlan = '三人分处两场，无同框，分场拍';
  ok(oGate(d, 'crowd-plan').ok, 'crowd-plan 写了方案应通过');
}

// 12 warnings
{
  const d = clone(outlineBase());
  d.episodes[3].synopsis = '外面下着雨，两人在楼下站着。';
  ok(!oGate(d, 'warnings').ok, 'warnings 应拦住提到雨戏却没预警');
  d.episodes[3].warnings = ['雨戏'];
  ok(oGate(d, 'warnings').ok, 'warnings 补了预警应通过');
}

// 13 refs
{
  const d = clone(outlineBase());
  d.episodes[0].characterIds = ['C99'];
  ok(!oGate(d, 'refs').ok, 'refs 应拦住不存在的角色引用');
}
{
  const d = clone(outlineBase());
  d.characters.push({ id: 'C05', name: '闲人', role: '', tier: 'support', anchor: 'local', arc: 'x', from: ['原创'] });
  ok(!oGate(d, 'refs').ok, 'refs 应拦住全剧没出场的角色');
}
{
  const d = clone(outlineBase());
  d.params.episodes = 7;
  ok(!oGate(d, 'refs').ok, 'refs 应拦住分集数量与 params 不符');
}

// 14 prose
{
  const d = clone(outlineBase());
  d.episodes[0].synopsis = '他说「我不干了」，然后走了。';
  ok(!oGate(d, 'prose').ok, 'prose 应拦住梗概里的引号对白');
}

// 15 anchor-unique
{
  const d = clone(outlineBase());
  d.characters.push({ id: 'C06', name: '万集2', role: '', tier: 'lead', anchor: 'base:wanji', arc: 'x', from: ['原创'] });
  ok(!oGate(d, 'anchor-unique').ok, 'anchor-unique 应拦住第二个万集');
}
{
  const d = clone(outlineBase());
  d.characters = d.characters.filter((c) => c.anchor !== 'base:wanji');
  ok(!oGate(d, 'anchor-unique').ok, 'anchor-unique 应拦住没有万集');
}
{
  const d = clone(outlineBase());
  d.characters.push({ id: 'C07', name: '苏薇2', role: '', tier: 'lead', anchor: 'base:suwei', arc: 'x', from: ['原创'] });
  ok(!oGate(d, 'anchor-unique').ok, 'anchor-unique 应拦住第二个苏薇');
}
{
  const d = clone(outlineBase());
  d.params.coreValue = ['甜'];
  d.characters = d.characters.filter((c) => c.anchor !== 'base:suwei');
  ok(!oGate(d, 'anchor-unique').ok, 'anchor-unique 应在卖甜时要求苏薇在场');
}

// 16 core-value
{
  const d = clone(outlineBase());
  d.params.coreValue = ['爽'];
  ok(!oGate(d, 'core-value').ok, 'core-value 应拦住没被认领的核心商品');
}
{
  const d = clone(outlineBase());
  d.params.coreValue = [];
  ok(!oGate(d, 'core-value').ok, 'core-value 应拦住空的核心商品');
}

// 17 mainline-bound
{
  const d = clone(outlineBase());
  d.params.mainline = false;
  d.beats[2].reveal = '世界意志';
  ok(!oGate(d, 'mainline-bound').ok, 'mainline-bound 应拦住主线外泄');
  d.params.mainline = true;
  ok(oGate(d, 'mainline-bound').ok, 'mainline=true 时允许 reveal');
}

// stage 过滤
{
  const d = clone(outlineBase());
  d.episodes = [];
  const sk = outlineGates(d, 'skeleton').map((g) => g.id);
  ok(!sk.includes('episode-three'), 'skeleton 阶段不应查分集门');
  const full = outlineGates(d, 'full').map((g) => g.id);
  ok(full.includes('episode-three'), 'full 阶段应查分集门');
  eq(sk.length, 7, 'skeleton 应为 7 门');
  eq(full.length, 17, 'full 应为 17 门');
}

// 渲染
{
  const md = outlineMd(outlineBase());
  ok(md.includes('《测试剧》｜短剧大纲'), '大纲 md 应有标题');
  ok(md.includes('## 三、人物'), '大纲 md 应有人物表');
  ok(md.includes('第 1 集'), '大纲 md 应有分集');
}
{
  eq(paramsOf(outlineBase()).maxPrimaryScenes, 5, 'params 应算出 6 集的主场景上限 5');
}

/* ------------------------------------------------------------------ */
/* DOCX                                                                */
/* ------------------------------------------------------------------ */

{
  const buf = buildDocx([P.title('《测试》'), P.ep('第1集·测试'), P.scene('1-1：[日] 办公室 内'), P.action('他推门进来。'), P.line('万集', '声音很平', '我来了。')]);
  ok(buf.length > 800, 'docx 体积应大于 800 字节');
  eq(buf.slice(0, 2).toString('latin1'), 'PK', 'docx 应是 ZIP 容器');
  ok(buf.includes(Buffer.from('word/document.xml')), 'docx 应包含 document.xml');
  ok(buf.includes(Buffer.from('word/styles.xml')), 'docx 应包含 styles.xml');
}
{
  const dir = mkdtempSync(join(tmpdir(), 'ir-docx-'));
  const p = join(dir, 't.docx');
  writeDocx(p, [P.p('hello')]);
  const b = readFileSync(p);
  ok(b.length > 0 && b.slice(0, 2).toString('latin1') === 'PK', 'writeDocx 应写出可用的文件');
  rmSync(dir, { recursive: true, force: true });
}

/* ------------------------------------------------------------------ */
/* 结果                                                                */
/* ------------------------------------------------------------------ */

const scriptGateIds = scriptGates(scriptBase(), {}).map((g) => g.id);
const outlineGateIds = outlineGates(outlineBase(), 'full').map((g) => g.id);

console.log(`剧本质量门 ${scriptGateIds.length} 道：${scriptGateIds.join(' / ')}`);
console.log(`大纲质量门 ${outlineGateIds.length} 道：${outlineGateIds.join(' / ')}`);
console.log('');

if (fails.length) {
  console.error(`✗ ${fails.length} 项未过：`);
  for (const f of fails) console.error(`  · ${f}`);
  console.error(`\n通过 ${pass} 项`);
  process.exit(1);
}

console.log(`✓ 全部 ${pass} 项断言通过（不调模型、不花额度）`);
