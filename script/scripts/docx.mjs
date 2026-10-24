/**
 * docx.mjs —— 零依赖 DOCX 生成器
 *
 * 只做一件事：把「段落 + 文字片段」写成合法的 .docx。
 * 用 Node 内置 zlib 做 DEFLATE，自己拼 ZIP 容器，不需要 npm 包。
 *
 * 用法：
 *   import { writeDocx, P } from './docx.mjs';
 *   writeDocx('剧本.docx', [ P.h1('标题'), P.p('正文') ]);
 */
import { writeFileSync } from 'node:fs';
import { deflateRawSync } from 'node:zlib';

/* ------------------------------------------------------------------ */
/* ZIP                                                                 */
/* ------------------------------------------------------------------ */

const CRC_TABLE = (() => {
  const t = new Int32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c;
  }
  return t;
})();

function crc32(buf) {
  let c = 0 ^ -1;
  for (let i = 0; i < buf.length; i += 1) c = (c >>> 8) ^ CRC_TABLE[(c ^ buf[i]) & 0xff];
  return (c ^ -1) >>> 0;
}

function dosTime(d = new Date()) {
  const time = ((d.getHours() & 0x1f) << 11) | ((d.getMinutes() & 0x3f) << 5) | ((d.getSeconds() / 2) & 0x1f);
  const date = (((d.getFullYear() - 1980) & 0x7f) << 9) | (((d.getMonth() + 1) & 0x0f) << 5) | (d.getDate() & 0x1f);
  return { time, date };
}

/** entries: [{ name, data: Buffer }] -> Buffer */
function zip(entries) {
  const { time, date } = dosTime();
  const locals = [];
  const centrals = [];
  let offset = 0;

  for (const e of entries) {
    const nameBuf = Buffer.from(e.name, 'utf8');
    const raw = Buffer.isBuffer(e.data) ? e.data : Buffer.from(e.data, 'utf8');
    const comp = deflateRawSync(raw, { level: 9 });
    const crc = crc32(raw);

    const lh = Buffer.alloc(30);
    lh.writeUInt32LE(0x04034b50, 0);
    lh.writeUInt16LE(20, 4);
    lh.writeUInt16LE(0x0800, 6); // UTF-8 文件名
    lh.writeUInt16LE(8, 8); // deflate
    lh.writeUInt16LE(time, 10);
    lh.writeUInt16LE(date, 12);
    lh.writeUInt32LE(crc, 14);
    lh.writeUInt32LE(comp.length, 18);
    lh.writeUInt32LE(raw.length, 22);
    lh.writeUInt16LE(nameBuf.length, 26);
    lh.writeUInt16LE(0, 28);
    locals.push(lh, nameBuf, comp);

    const ch = Buffer.alloc(46);
    ch.writeUInt32LE(0x02014b50, 0);
    ch.writeUInt16LE(20, 4);
    ch.writeUInt16LE(20, 6);
    ch.writeUInt16LE(0x0800, 8);
    ch.writeUInt16LE(8, 10);
    ch.writeUInt16LE(time, 12);
    ch.writeUInt16LE(date, 14);
    ch.writeUInt32LE(crc, 16);
    ch.writeUInt32LE(comp.length, 20);
    ch.writeUInt32LE(raw.length, 24);
    ch.writeUInt16LE(nameBuf.length, 28);
    ch.writeUInt16LE(0, 30); // extra
    ch.writeUInt16LE(0, 32); // comment
    ch.writeUInt16LE(0, 34); // disk
    ch.writeUInt16LE(0, 36); // internal attrs
    ch.writeUInt32LE(0, 38); // external attrs
    ch.writeUInt32LE(offset, 42);
    centrals.push(ch, nameBuf);

    offset += lh.length + nameBuf.length + comp.length;
  }

  const cd = Buffer.concat(centrals);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0);
  eocd.writeUInt16LE(0, 4);
  eocd.writeUInt16LE(0, 6);
  eocd.writeUInt16LE(entries.length, 8);
  eocd.writeUInt16LE(entries.length, 10);
  eocd.writeUInt32LE(cd.length, 12);
  eocd.writeUInt32LE(offset, 16);
  eocd.writeUInt16LE(0, 20);

  return Buffer.concat([...locals, cd, eocd]);
}

/* ------------------------------------------------------------------ */
/* XML 片段                                                            */
/* ------------------------------------------------------------------ */

const esc = (s) =>
  String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');

const FONT_LATIN = 'Times New Roman';
const FONT_EA = '宋体';
const FONT_HEI = '黑体';

function run(text, { bold = false, size = 24, font = FONT_EA, italic = false } = {}) {
  const rpr = [
    '<w:rPr>',
    `<w:rFonts w:ascii="${FONT_LATIN}" w:hAnsi="${FONT_LATIN}" w:eastAsia="${font}" w:cs="${FONT_LATIN}"/>`,
    bold ? '<w:b/><w:bCs/>' : '',
    italic ? '<w:i/>' : '',
    `<w:sz w:val="${size}"/><w:szCs w:val="${size}"/>`,
    '</w:rPr>',
  ].join('');
  return `<w:r>${rpr}<w:t xml:space="preserve">${esc(text)}</w:t></w:r>`;
}

function para(runs, { align = 'left', indentChars = 0, before = 0, after = 120, line = 360, keepNext = false } = {}) {
  // OOXML 的 pPr 子元素有固定顺序：keepNext → spacing → ind → jc，顺序错了严格校验器会拒
  const ppr = [
    '<w:pPr>',
    keepNext ? '<w:keepNext/>' : '',
    `<w:spacing w:before="${before}" w:after="${after}" w:line="${line}" w:lineRule="auto"/>`,
    indentChars ? `<w:ind w:firstLineChars="${indentChars * 100}" w:firstLine="${indentChars * 240}"/>` : '',
    align !== 'left' ? `<w:jc w:val="${align}"/>` : '',
    '</w:pPr>',
  ].join('');
  return `<w:p>${ppr}${runs.join('')}</w:p>`;
}

/* ------------------------------------------------------------------ */
/* 段落构造器（给上层用的语法糖）                                        */
/* ------------------------------------------------------------------ */

export const P = {
  /** 文档标题：《剧名》 */
  title: (t) => para([run(t, { bold: true, size: 40, font: FONT_HEI })], { align: 'center', before: 240, after: 360, keepNext: true }),

  /** 集标题：第1集·集名 */
  ep: (t) => para([run(t, { bold: true, size: 32, font: FONT_HEI })], { align: 'center', before: 360, after: 240, keepNext: true }),

  /** 场景头：1-1：[日] 地点 内 */
  scene: (t) => para([run(t, { bold: true, size: 24 })], { before: 240, after: 80, keepNext: true }),

  /** 人物：A、B */
  cast: (t) => para([run(t, { size: 21 })], { after: 160, keepNext: true }),

  /** △ 动作 */
  action: (t) => para([run(`△${t}`, { size: 24 })], { indentChars: 2, after: 80 }),

  /** 角色（提示）：台词 */
  line: (name, delivery, text, mode) => {
    const parts = [];
    if (mode) parts.push(mode);
    if (delivery) parts.push(delivery);
    const paren = parts.length ? `（${parts.join('，')}）` : '';
    return para([run(`${name}${paren}：`, { bold: true, size: 24 }), run(text, { size: 24 })], { indentChars: 2, after: 80 });
  },

  /** 普通正文 */
  p: (t, opts = {}) => para([run(t, { size: 24, ...opts })], { after: 120 }),

  /** 二级标题 */
  h2: (t) => para([run(t, { bold: true, size: 28, font: FONT_HEI })], { before: 320, after: 160, keepNext: true }),

  /** 小标题 */
  h3: (t) => para([run(t, { bold: true, size: 24, font: FONT_HEI })], { before: 240, after: 100, keepNext: true }),

  /** 引用/说明 */
  note: (t) => para([run(t, { size: 21, italic: true })], { indentChars: 2, after: 100 }),

  /** 空行 */
  blank: () => para([], { after: 0, line: 360 }),
};

/* ------------------------------------------------------------------ */
/* 打包                                                                */
/* ------------------------------------------------------------------ */

export function buildDocx(paragraphs) {
  const documentXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>${paragraphs.join('')}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="851" w:footer="992" w:gutter="0"/><w:docGrid w:linePitch="312"/></w:sectPr></w:body></w:document>`;

  const stylesXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="${FONT_LATIN}" w:hAnsi="${FONT_LATIN}" w:eastAsia="${FONT_EA}" w:cs="${FONT_LATIN}"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:line="360" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style></w:styles>`;

  const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>`;

  const rels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>`;

  const docRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`;

  return zip([
    { name: '[Content_Types].xml', data: contentTypes },
    { name: '_rels/.rels', data: rels },
    { name: 'word/document.xml', data: documentXml },
    { name: 'word/styles.xml', data: stylesXml },
    { name: 'word/_rels/document.xml.rels', data: docRels },
  ]);
}

export function writeDocx(path, paragraphs) {
  const buf = buildDocx(paragraphs);
  writeFileSync(path, buf);
  return buf.length;
}
