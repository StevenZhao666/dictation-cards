#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把 `17-默写卡-Ch1-4.md` 编译成一个可离线使用的单页自测器（默写卡自测/index.html）。

用法：  python "_build_默写卡自测.py" [卡片md] [输出目录] [--single]
默认：  卡片md = 本脚本同目录的 17-默写卡-Ch1-4.md
        输出目录 = 本脚本同目录/默写卡自测
        --single = 额外产出一个把 KaTeX 全内联的单文件版（手机用，微信发这一个文件就行）

依赖：  仅标准库。KaTeX 从 D:\\MarkdownViewer\\lib\\katex 复制到输出目录（首次），
        之后完全离线、相对路径引用，不依赖 CDN。

功能：  随机顺序 · 点开答案 · ✓/✗ 记录（localStorage）· "只抽没过的"模式 · 键盘 1/2/3/空格
  v2 新增（回应导师建议）：
    ① 默写输入框——自己先把答案写出来（LaTeX 或英文句子）
    ② AI 判定——把「题面 + 标准答案 + 你的默写」发给 DeepSeek 比对，回
       「结论 / 漏掉的要点 / 写错的地方 / 提醒」；判定按卡片存本机，复习时能看到
    ③ 手写拍照——拍下纸上写的，走 DeepSeek 视觉模型判定
    API key 存在本机浏览器 localStorage，**不写进 html 文件**，所以单文件版
    可以放心发给同学/老师；换设备要在那台设备上重填一次 key。
    不填 key 也能用「复制给 AI」：一键复制拼好的 prompt，贴给任何 LLM，再把答复贴回。
"""
import base64
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KATEX_SRC = r"D:\MarkdownViewer\lib\katex"

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
MD_PATH = ARGS[0] if len(ARGS) > 0 else os.path.join(HERE, "17-默写卡-Ch1-4.md")
OUT_DIR = ARGS[1] if len(ARGS) > 1 else os.path.join(HERE, "默写卡自测")
TITLE_DEFAULT = "默写卡自测"

DEFAULT_BASE = "https://api.deepseek.com"
# 2026-10-14 实测（GET /models）：这个 key 可用的模型只有 deepseek-flash 与 deepseek-v4-pro。
# deepseek-chat / deepseek-reasoner / deepseek-v4-flash-vision-exp / deepseek-v4-flash 这些名字会被
# 服务端静默当成 deepseek-flash（返回体的 model 字段一律是 deepseek-flash），
# 而 deepseek-v3 / deepseek-chat-latest 直接 400「The supported API model names are ...」。
# 图片也用同一个 deepseek-flash（实测识图正常），所以文字与手写只用一个模型名，不再分两个。
DEFAULT_MODEL = "deepseek-flash"


def md_title(text, fallback):
    """用 md 的第一个一级标题当页面标题（这样同一个脚本能给不同课程用）。"""
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else fallback


def parse_cards(text):
    """按 '## 卡 NN · 名称' 切块；<details> 前的正文=题面，标签内=答案。"""
    blocks = re.split(r"\n## 卡 ", text)[1:]
    cards = []
    for b in blocks:
        lines = b.split("\n", 1)
        title = lines[0].strip()
        rest = lines[1] if len(lines) > 1 else ""
        m = re.search(r"<details><summary>答案</summary>(.*?)</details>", rest, re.S)
        if m:
            q = rest[: m.start()].strip()
            ans = m.group(1).strip()
            if "卡" in rest[m.end():] or rest[m.end():].strip():
                trailing = rest[m.end():].strip()
                if trailing and not trailing.startswith("##"):
                    ans = ans + "\n\n" + trailing
        else:
            q, ans = rest.strip(), ""
        q = re.sub(r"^\*\*默写题[：:]\s*(.*?)\*\*$", r"\1", q, flags=re.M).strip()
        if not q:
            q = "说出条件与结论（英文原文）。"
        num = re.match(r"(\d+)", title)
        cards.append({"id": num.group(1) if num else title[:2], "t": title, "q": q, "a": ans})
    return cards


CSS = """
:root{--bg:#111418;--card:#1b2027;--fg:#e8edf3;--mut:#9aa7b4;--acc:#4c9be8;--ok:#3fbf7f;--no:#e2604a;--bd:#2b323b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.7 system-ui,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:18px 16px 60px}
h1{font-size:19px;margin:0 0 4px}
.bar{position:sticky;top:0;background:linear-gradient(#111418,#111418ee);padding:10px 0 12px;border-bottom:1px solid var(--bd);margin-bottom:18px;z-index:5}
.bar .row{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.stat{color:var(--mut);font-size:14px}
.stat b{color:var(--fg)}
button{background:#232a33;color:var(--fg);border:1px solid var(--bd);border-radius:10px;
  padding:10px 14px;font:inherit;font-size:15px;cursor:pointer}
button:hover{border-color:var(--acc)}
button[disabled]{opacity:.5;cursor:default}
button.primary{background:#1d3a55;border-color:#2c6ea8}
button.ok{background:#17362a;border-color:#2b6b4f}
button.no{background:#3a211c;border-color:#7d3a2c}
label.chk{color:var(--mut);font-size:14px;display:flex;gap:6px;align-items:center;cursor:pointer}
.card{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:20px 20px 16px}
.num{color:var(--acc);font-size:15px;letter-spacing:.02em;margin-bottom:10px}
.q{font-size:21px;font-weight:600;margin-bottom:18px}
.ans{border-top:1px dashed var(--bd);margin-top:6px;padding-top:16px}
.ans p{margin:.55em 0}
.ans strong{color:#fff}
.ans code{background:#0d1013;padding:1px 5px;border-radius:5px;font-size:.92em}
.btns{display:flex;flex-wrap:wrap;gap:10px;margin-top:20px}
.btns button{flex:1 1 auto;min-width:120px}
.done{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:24px;text-align:center}
.kbd{color:var(--mut);font-size:13px;margin-top:14px}
.foot{color:var(--mut);font-size:13px;margin-top:22px}
a{color:var(--acc)}
/* ---- v2：默写输入 + AI 判定 ---- */
.minebox{border-top:1px dashed var(--bd);margin-top:14px;padding-top:14px}
.minebox label{display:block;color:var(--mut);font-size:14px;margin-bottom:8px}
textarea{width:100%;background:#0d1013;color:var(--fg);border:1px solid var(--bd);border-radius:10px;
  padding:10px 12px;font:15px/1.6 ui-monospace,Consolas,"Cascadia Mono",monospace;resize:vertical;min-height:104px}
textarea:focus{outline:none;border-color:var(--acc)}
.ai{border-top:1px dashed var(--bd);margin-top:18px;padding-top:16px}
.aihead{display:flex;flex-wrap:wrap;gap:10px;align-items:baseline;margin-bottom:10px}
.aihead b{font-size:15px}
.aiout{background:#0d1013;border:1px solid var(--bd);border-left:3px solid var(--acc);border-radius:10px;
  padding:12px 14px;margin:12px 0;font-size:15.5px}
.aiout p{margin:.45em 0}
.warn{color:#e2b34a}
.oktxt{color:var(--ok)}
.notxt{color:var(--no)}
details.cfg{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:12px 16px;margin-top:18px}
details.cfg summary{cursor:pointer;color:var(--mut);font-size:15px}
details.cfg .grid{display:grid;gap:10px;margin-top:12px}
details.cfg label{font-size:14px}
details.cfg input[type=text],details.cfg input[type=password]{width:100%;background:#0d1013;color:var(--fg);
  border:1px solid var(--bd);border-radius:9px;padding:9px 11px;font:14px/1.5 ui-monospace,Consolas,monospace}
details.cfg small{color:var(--mut);font-size:13px;display:block;margin-top:4px}
.preview{margin-top:10px}
.preview img{max-width:100%;max-height:280px;border-radius:10px;border:1px solid var(--bd)}
/* ---- v3：LaTeX 编辑框 + 默写实时预览 ---- */
.texwrap{margin:6px 0 0}
.texwrap summary{cursor:pointer;color:var(--mut);font-size:14px}
.texwrap summary:hover{color:var(--acc)}
.texbox{background:#0d1013;border:1px solid var(--bd);border-radius:10px;padding:10px 12px;margin-top:8px}
.texbtns{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:9px}
.texbtns button{padding:4px 8px;font:13.5px/1.3 ui-monospace,Consolas,"Cascadia Mono",monospace;
  background:#12181d;border-radius:7px;min-width:0}
.texbtns button:hover{border-color:var(--acc);color:var(--acc)}
#texSrc{min-height:46px;font:15px/1.6 ui-monospace,Consolas,"Cascadia Mono",monospace}
.texpv{margin-top:8px;padding:8px 10px;background:#12181d;border:1px solid var(--bd);border-radius:8px;
  min-height:44px;display:flex;align-items:center;gap:8px;overflow-x:auto;flex-wrap:wrap}
.texpv .tag{color:var(--mut);font-size:12.5px;flex:0 0 auto}
.hint{color:var(--mut);font-size:13px}
.minepv{margin-top:8px;padding:10px 12px;background:#0d1013;border:1px dashed var(--bd);border-radius:10px;font-size:15.5px}
.minepv p{margin:.45em 0}
"""

JS = r"""
const CARDS = __CARDS__;
const KEY = '__STOREKEY__';
const CFG_KEY = KEY + ':cfg';
const DEF_CFG = { base: '__DEFAULT_BASE__', key: '', model: '__DEFAULT_MODEL__', think: false };
let state = {};
try { state = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { state = {}; }

const $ = (s) => document.querySelector(s);
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} };
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const nl2br = (s) => esc(s).replace(/\n/g, '<br>');

function cfgLoad() {
  let c = {};
  try { c = JSON.parse(localStorage.getItem(CFG_KEY) || '{}') || {}; } catch (e) { c = {}; }
  return Object.assign({}, DEF_CFG, c);
}
function cfgSave() { try { localStorage.setItem(CFG_KEY, JSON.stringify(CFG)); } catch (e) {} }
let CFG = cfgLoad();

let queue = [], pos = 0, cur = null, revealed = false, busy = false;
let imgData = null;   // 当前这张卡已选/已拍的手写图（data URL，不落存储）

function renderMD(md) {
  const parts = [];
  md = md.replace(/\\\[([\s\S]+?)\\\]/g, (m, t) => { parts.push({ tex: t.trim(), d: true }); return '@@M' + (parts.length - 1) + '@@'; });
  md = md.replace(/\\\(([\s\S]+?)\\\)/g, (m, t) => { parts.push({ tex: t.trim(), d: false }); return '@@M' + (parts.length - 1) + '@@'; });
  md = md.replace(/\$\$([\s\S]+?)\$\$/g, (m, t) => { parts.push({ tex: t.trim(), d: true }); return '@@M' + (parts.length - 1) + '@@'; });
  md = md.replace(/\$([^$\n]+?)\$/g, (m, t) => { parts.push({ tex: t.trim(), d: false }); return '@@M' + (parts.length - 1) + '@@'; });
  md = esc(md);
  md = md.replace(/`([^`]+)`/g, '<code>$1</code>');
  md = md.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  md = md.replace(/^- (.*)$/gm, '• $1');
  md = md.replace(/^\s*---+\s*$/gm, '');
  let html = md.split(/\n{2,}/).map((p) => '<p>' + p.replace(/\n/g, '<br>') + '</p>').join('');
  html = html.replace(/@@M(\d+)@@/g, (m, i) => {
    const p = parts[+i];
    try { return katex.renderToString(p.tex, { displayMode: p.d, throwOnError: false }); }
    catch (e) { return '<code>' + esc(p.tex) + '</code>'; }
  });
  return html;
}

/* ---------- v3：LaTeX 编辑框（按钮拼公式 + 实时预览 + 插入默写框） ---------- */
function texMathDepth(ta) {   // 光标处是否已经在 $...$ 里（数 $ 的奇偶）
  const before = ta.value.slice(0, ta.selectionStart);
  return ((before.match(/(^|[^$])\$(?!\$)/g) || []).length) % 2 === 1;
}
function texIns(tex) {
  const ta = $('#texSrc');
  const s = ta.selectionStart, e = ta.selectionEnd, v = ta.value, sel = v.slice(s, e);
  let ins = tex, caret;
  if (sel && ins.indexOf('{}') >= 0) { ins = ins.replace('{}', '{' + sel + '}'); caret = s + ins.length; }  // 有选中 → 包进去
  else if (ins.indexOf('{}') >= 0) { caret = s + ins.indexOf('{}') + 1; }                                    // 光标进花括号
  else { caret = s + ins.length; }
  ta.value = v.slice(0, s) + ins + v.slice(e);
  ta.selectionStart = ta.selectionEnd = caret;
  ta.focus();
  texPvUpd();
}
function texPvUpd() {
  const raw = $('#texSrc').value.trim();
  const body = $('#texPvBody');
  if (!raw) { body.innerHTML = '<span class="hint">拼好的公式会显示在这里</span>'; return; }
  const t = raw.replace(/^\$\$?/, '').replace(/\$\$?$/, '').trim();
  try { body.innerHTML = katex.renderToString(t, { displayMode: false, throwOnError: false }); }
  catch (e) { body.textContent = raw; }
}
function minePvUpd() {   // 默写框内容实时渲染（$...$ 变公式），空了就收起
  const pv = $('#minePv'), v = $('#mine').value;
  if (!v.trim()) { pv.hidden = true; pv.innerHTML = ''; return; }
  pv.innerHTML = renderMD(v);
  // 有 LaTeX 命令没被 $（或 \(..\)）包起来 → 提醒（否则用户会奇怪为什么没渲染成公式）
  const outside = v.replace(/\$\$[\s\S]*?\$\$/g, '').replace(/\$[^$\n]*?\$/g, '').replace(/\\\([\s\S]*?\\\)/g, '');
  if (/\\[a-zA-Z]+/.test(outside)) {
    pv.innerHTML += '<div class="hint">↑ 有一段 LaTeX 还没用 $ 括起来，所以现在只是文本。写成 $…$ 就会渲染成公式（也可以点上面的「LaTeX 编辑框」拼好再插入）</div>';
  }
  pv.hidden = false;
}
function texToMine() {
  const tex = $('#texSrc').value.trim();
  if (!tex) return;
  const ta = $('#mine');
  const s = ta.selectionStart, e = ta.selectionEnd;
  let ins = tex.replace(/^\$\$?/, '').replace(/\$\$?$/, '').trim();
  if (!texMathDepth(ta)) ins = '$' + ins + '$';    // 不在 $...$ 里就自动包一层
  // 防止与相邻的 $ 粘成 $$（$$ 会被当成 display 公式）
  let padL = '', padR = '';
  if (s > 0 && ta.value[s - 1] === '$') padL = ' ';
  if (e < ta.value.length && ta.value[e] === '$') padR = ' ';
  ta.value = ta.value.slice(0, s) + padL + ins + padR + ta.value.slice(e);
  ta.selectionStart = ta.selectionEnd = s + padL.length + ins.length;
  ta.focus();
  minePvUpd();
  $('#texSrc').value = ''; texPvUpd();             // 搬走了就清空编辑框
}

function shuffle(a) { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); const t = a[i]; a[i] = a[j]; a[j] = t; } return a; }

function startQueue() {
  const onlyFailed = $('#onlyFailed').checked;
  const list = CARDS.filter((c) => (onlyFailed ? state[c.id] === 'no' : true));
  if (!list.length) { queue = []; pos = 0; showDone(true); return; }   // 空候选：给出口，别卡住
  queue = shuffle(list.map((c) => c.id));
  pos = 0; revealed = false;
  $('#card').hidden = false;
  $('#done').hidden = true;
  next();
}

function counts() {
  let ok = 0, no = 0;
  CARDS.forEach((c) => { if (state[c.id] === 'ok') ok++; else if (state[c.id] === 'no') no++; });
  return { ok: ok, no: no, todo: CARDS.length - ok - no };
}

function paintStat() {
  const c = counts();
  const mode = $('#onlyFailed').checked ? '只抽 ✗（' + queue.length + ' 张）' : '全部';
  $('#stat').innerHTML = '已通过 <b>' + c.ok + '/' + CARDS.length + '</b>　✗ 未过 <b>' + c.no + '</b>　未测 <b>' + c.todo +
    '</b>　·　模式：' + mode + '　·　本轮 ' + (queue.length ? (pos + 1) + '/' + queue.length : 0);
}

function next() {
  if (pos >= queue.length) { showDone(); return; }
  cur = CARDS.find((c) => c.id === queue[pos]);
  revealed = false;
  imgData = null;
  $('#done').hidden = true;
  $('#card').hidden = false;
  $('#num').textContent = '卡 ' + cur.t;
  $('#q').textContent = cur.q;
  $('#ans').innerHTML = '';
  $('#ans').hidden = true;
  $('#show').hidden = false;
  $('#acts').hidden = true;
  $('#mine').value = state['mine:' + cur.id] || '';
  minePvUpd();
  $('#fileImg').value = '';
  $('#thumb').hidden = true;
  $('#thumb').removeAttribute('src');
  $('#ai').hidden = true;
  $('#aiOut').hidden = true;
  $('#aiOut').innerHTML = '';
  $('#aiPaste').value = state['ai:' + cur.id] || '';
  $('#aiMsg').textContent = '';
  $('#aiMsg').className = 'stat';
  paintStat();
}

function reveal() {
  if (!cur || revealed) return;
  revealed = true;
  const mine = $('#mine').value.trim();
  if (mine) { state['mine:' + cur.id] = mine; save(); }
  $('#ans').innerHTML = renderMD(cur.a);
  $('#ans').hidden = false;
  $('#show').hidden = true;
  $('#acts').hidden = false;
  $('#ai').hidden = false;
  const prev = state['ai:' + cur.id];
  if (prev) { $('#aiOut').innerHTML = renderMD(prev); $('#aiOut').hidden = false; }
}

function mark(r) {
  if (!cur) return;
  if (r !== 'skip') { state[cur.id] = r; save(); }
  pos++;
  if (pos >= queue.length) { showDone(); paintStat(); return; }
  next();
}

function showDone(empty) {
  $('#card').hidden = true;
  $('#done').hidden = false;
  const c = counts();
  const onlyFailed = $('#onlyFailed').checked;
  let msg;
  if (empty && onlyFailed) {
    msg = '现在<b>没有「✗ 没过」的卡片</b>（✗ ' + c.no + ' 张 · 未测 ' + c.todo + ' 张），所以「只抽 ✗ 的」抽不出东西。' +
      '<br>→ 点下面那个按钮取消它，就能从全部 ' + CARDS.length + ' 张里继续。';
  } else if (empty) {
    msg = '没有卡片可抽。';
  } else {
    msg = '本轮结束。' + (onlyFailed ? '' : '已通过 <b>' + c.ok + '/' + CARDS.length + '</b>。') +
      (c.no ? ' 还有 <b>' + c.no + '</b> 张没过——把「只抽 ✗ 的」勾上再来一轮。'
            : (c.todo ? ' 还有 ' + c.todo + ' 张没测。' : ' 全部通过 🎉'));
  }
  $('#doneMsg').innerHTML = msg;
  $('#fallback').hidden = !(empty && onlyFailed);
  $('#again2').hidden = !!(empty && onlyFailed);
  paintStat();
}

/* ---------- v2：AI 判定 ---------- */

function buildPrompt(c, mine) {
  return [
    '你是数学分析课程的助教，正在批改学生的「定理默写」。教材：Bartle & Sherbert, Introduction to Real Analysis (4th ed.)。',
    '评分只依内容（条件、结论、量词、符号位置是否齐全），不因措辞不同或等价的符号写法扣分。',
    '本课程期中是英文卷：学生答案若用中文写、或没能给出可直接抄上考卷的英文表述，请明确指出。',
    '',
    '请严格按下面四行格式作答，不要输出其它内容：',
    '结论：正确 / 部分正确 / 不正确',
    '漏掉的要点：（没有就写"无"）',
    '写错的地方：（没有就写"无"）',
    '提醒：（一句话）',
    '',
    '—— 题目 ——', c.q,
    '—— 标准答案（教材口径）——', c.a,
    '—— 学生的默写 ——', (mine && mine.trim()) ? mine : '（见附图：手写默写）'
  ].join('\n');
}

async function callAI(prompt, img) {
  const url = CFG.base.replace(/\/+$/, '') + '/chat/completions';
  const content = img ? [{ type: 'text', text: prompt }, { type: 'image_url', image_url: { url: img } }] : prompt;
  const body = {
    model: CFG.model,
    max_tokens: CFG.think ? 4000 : (img ? 2500 : 1500),
    messages: [{ role: 'user', content: content }]
  };
  // 默认关掉思考链：更快更省，而且不会出现「思考把 token 预算吃光、正文空掉」的情况
  if (!CFG.think) body.thinking = { type: 'disabled' };
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + CFG.key },
    body: JSON.stringify(body)
  });
  const txt = await r.text();
  if (!r.ok) throw new Error('HTTP ' + r.status + '：' + txt.slice(0, 300));
  let d;
  try { d = JSON.parse(txt); } catch (e) { throw new Error('返回不是 JSON：' + txt.slice(0, 200)); }
  const ch = (d.choices && d.choices[0]) || {};
  const m = ch.message || {};
  const body0 = ((m.content || '') + '').trim();
  const reason = ((m.reasoning_content || '') + '').trim();
  if (body0) {
    if (ch.finish_reason === 'length') return body0 + '\n\n（⚠ 输出被 max_tokens 截断，可能没说完整——可在设置里把「深度思考」打开再试）';
    return body0;
  }
  if (ch.finish_reason === 'length' && reason) {
    throw new Error('模型把 token 预算全花在思考上了，被截断、没给出结论。把「深度思考」关掉再试（默认就是关的），或换模型。');
  }
  if (reason) return '⚠ 下面这段是模型的思考过程，不是判定结果（它没给出正式答复）：\n\n' + reason;
  throw new Error('模型返回空内容（finish_reason=' + (ch.finish_reason || '?') + '）');
}

function shrinkImage(file, maxSide, cb) {
  const fr = new FileReader();
  fr.onerror = () => cb(null, '读取图片失败');
  fr.onload = () => {
    const im = new Image();
    im.onerror = () => cb(null, '这张图浏览器打不开');
    im.onload = () => {
      const s = Math.min(1, maxSide / Math.max(im.width, im.height));
      const cv = document.createElement('canvas');
      cv.width = Math.max(1, Math.round(im.width * s));
      cv.height = Math.max(1, Math.round(im.height * s));
      cv.getContext('2d').drawImage(im, 0, 0, cv.width, cv.height);
      cb(cv.toDataURL('image/jpeg', 0.85), null);
    };
    im.src = fr.result;
  };
  fr.readAsDataURL(file);
}

function aiOut(html) { $('#aiOut').innerHTML = html; $('#aiOut').hidden = false; }
function aiMsg(t, cls) { $('#aiMsg').textContent = t; $('#aiMsg').className = 'stat ' + (cls || ''); }

async function aiGrade(useImage) {
  if (!cur || busy) return;
  const prompt = buildPrompt(cur, $('#mine').value);
  if (!CFG.key) {
    aiOut('<span class="warn">还没有填 API key。</span>先展开下面的「AI 设置」填一次（只存在本机浏览器），' +
      '或者点「复制给 AI」，把复制到的内容贴给任意 AI，再把它的答复贴回来。');
    return;
  }
  if (useImage && !imgData) { aiMsg('先选一张手写照片', 'warn'); return; }
  const mineTxt = $('#mine').value.trim();
  if (!mineTxt && !imgData) { aiMsg('上面还没写东西——先默写点内容，或点「手写拍照 / 选图判定」选张照片', 'warn'); return; }
  if (!mineTxt && imgData && !useImage) { aiMsg('默写框是空的；要按你拍的照片判定，请点「手写拍照 / 选图判定」', 'warn'); return; }
  busy = true;
  const btn = useImage ? $('#aiImg') : $('#aiGo');
  const old = btn.textContent;
  btn.textContent = '判定中…'; $('#aiGo').disabled = true; $('#aiImg').disabled = true;
  aiMsg('正在请求 ' + CFG.model + ' …');
  try {
    const out = await callAI(prompt, useImage ? imgData : null);
    state['ai:' + cur.id] = (useImage ? '[手写照片判定]\n' : '') + out;
    save();
    aiOut(renderMD(out));
    aiMsg('✓ 已判定并存下（下次抽到这张卡会自动显示）', 'oktxt');
  } catch (e) {
    aiOut('<span class="notxt">判定失败：' + esc(e.message || String(e)) + '</span><br><br>' +
      '常见原因：key 不对 / 没余额 / 没网 / 浏览器拦了跨域。<br>' +
      '可以先点「复制给 AI」走手动路径。');
    aiMsg('');
  } finally {
    busy = false;
    btn.textContent = old; $('#aiGo').disabled = false; $('#aiImg').disabled = false;
  }
}

function fallbackCopy(t, done) {
  const ta = document.createElement('textarea');
  ta.value = t; ta.style.position = 'fixed'; ta.style.top = '-9999px';
  document.body.appendChild(ta); ta.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch (e) {}
  document.body.removeChild(ta);
  if (ok) { done(); return; }
  $('#aiPaste').value = t;
  aiMsg('浏览器不让自动复制，内容已放进下面的框里，长按全选手动复制', 'warn');
}

function copyPrompt() {
  if (!cur) return;
  if (!$('#mine').value.trim() && !imgData) { aiMsg('上面还没写东西——先默写点内容，或选一张手写照片', 'warn'); return; }
  const t = buildPrompt(cur, $('#mine').value);
  const done = () => aiMsg('✓ 已复制，粘给 AI（微信里的 Hermes / DeepSeek / 豆包都行），再把答复贴到下面', 'oktxt');
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(t).then(done, () => fallbackCopy(t, done));
  } else { fallbackCopy(t, done); }
}

document.addEventListener('DOMContentLoaded', () => {
  try {
    localStorage.setItem(KEY + '_ping', '1');
    localStorage.removeItem(KEY + '_ping');
  } catch (e) { $('#storageWarn').hidden = false; }

  $('#cfgBase').value = CFG.base;
  $('#cfgKey').value = CFG.key;
  $('#cfgModel').value = CFG.model;
  $('#cfgThink').checked = !!CFG.think;

  $('#onlyFailed').addEventListener('change', startQueue);
  $('#show').addEventListener('click', reveal);
  $('#again').addEventListener('click', startQueue);
  $('#again2').addEventListener('click', startQueue);
  $('#fallback').addEventListener('click', () => { $('#onlyFailed').checked = false; startQueue(); });
  $('#reset').addEventListener('click', () => {
    if (confirm('清空全部 ✓/✗ 记录？（默写内容和 AI 判定也会一起清掉）')) { state = {}; save(); startQueue(); }
  });
  document.querySelectorAll('#acts button').forEach((b) => b.addEventListener('click', () => mark(b.dataset.r)));

  $('#mine').addEventListener('blur', () => {
    if (!cur) return;
    const v = $('#mine').value.trim();
    if (v) { state['mine:' + cur.id] = v; save(); }
  });

  $('#aiGo').addEventListener('click', () => aiGrade(false));
  $('#aiImg').addEventListener('click', () => $('#fileImg').click());
  $('#fileImg').addEventListener('change', (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    aiMsg('正在压缩图片…');
    shrinkImage(f, 1400, (data, err) => {
      if (!data) { aiMsg(err || '图片处理失败', 'warn'); return; }
      imgData = data;
      $('#thumb').src = data; $('#thumb').hidden = false;
      aiMsg('图片就绪，点「手写拍照 / 选图判定」开始', 'oktxt');
    });
  });
  $('#copyP').addEventListener('click', copyPrompt);
  $('#aiSave').addEventListener('click', () => {
    if (!cur) return;
    const v = $('#aiPaste').value.trim();
    state['ai:' + cur.id] = v;
    save();
    aiOut(v ? renderMD(v) : '<span class="warn">（已清空这张卡的判定）</span>');
    aiMsg('✓ 已存到这张卡', 'oktxt');
  });

  $('#saveCfg').addEventListener('click', () => {
    CFG.base = $('#cfgBase').value.trim() || DEF_CFG.base;
    CFG.key = $('#cfgKey').value.trim();
    CFG.model = $('#cfgModel').value.trim() || DEF_CFG.model;
    CFG.think = $('#cfgThink').checked;
    cfgSave();
    aiMsg(CFG.key ? '✓ 设置已保存到本机浏览器' : '已保存（没填 key，只能用「复制给 AI」）', 'oktxt');
  });

  $('#testCfg').addEventListener('click', async () => {
    const b = $('#testCfg');
    CFG.base = $('#cfgBase').value.trim() || DEF_CFG.base;
    CFG.key = $('#cfgKey').value.trim();
    CFG.model = $('#cfgModel').value.trim() || DEF_CFG.model;
    CFG.think = $('#cfgThink').checked;
    cfgSave();
    if (!CFG.key) { aiMsg('先填 key 再测', 'warn'); return; }
    b.disabled = true; aiMsg('测试中…');
    try {
      const out = await callAI('只回两个字：可以', null);
      aiMsg('✓ 连接正常，模型回了：' + out.slice(0, 40), 'oktxt');
    } catch (e) {
      aiMsg('✗ ' + (e.message || String(e)).slice(0, 200), 'notxt');
    } finally { b.disabled = false; }
  });

  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.code === 'Space' || e.code === 'Enter') { e.preventDefault(); reveal(); }
    else if (e.key === '1') mark('ok');
    else if (e.key === '2') mark('no');
    else if (e.key === '3') mark('skip');
  });
  // v3：LaTeX 编辑框 + 默写实时预览
  document.querySelectorAll('#texWrap button[data-tex]').forEach((b) => b.addEventListener('click', () => texIns(b.dataset.tex)));
  $('#texSrc').addEventListener('input', texPvUpd);
  $('#texSrc').addEventListener('keydown', (e) => { if (e.key === 'Tab') { e.preventDefault(); texIns('  '); } });
  $('#texToMine').addEventListener('click', texToMine);
  $('#texClear').addEventListener('click', () => { $('#texSrc').value = ''; texPvUpd(); $('#texSrc').focus(); });
  $('#mine').addEventListener('input', minePvUpd);
  $('#texWrap').addEventListener('toggle', () => { try { localStorage.setItem(KEY + ':texopen', $('#texWrap').open ? '1' : '0'); } catch (e) {} });
  try { const _tv = localStorage.getItem(KEY + ':texopen'); if (_tv === '1') $('#texWrap').open = true; else if (_tv === '0') $('#texWrap').open = false; } catch (e) {}
  startQueue();
});
"""

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="katex/katex.min.css">
<script src="katex/katex.min.js"></script>
<style>__CSS__</style>
</head>
<body>
<div class="wrap">
  <div class="bar">
    <h1>__TITLE__</h1>
    <div class="row" style="margin-top:8px">
      <span class="stat" id="stat"></span>
    </div>
    <div class="row" style="margin-top:8px">
      <label class="chk"><input type="checkbox" id="onlyFailed"> 只抽 ✗ 的</label>
      <span class="stat" id="storageWarn" hidden style="color:#e2b34a">⚠ 此浏览器禁止本地存储，进度只在本次打开期间有效</span>
      <button id="again">重新打乱 / 再来一轮</button>
      <button id="reset">清空记录</button>
    </div>
  </div>
  <div class="card" id="card">
    <div class="num" id="num"></div>
    <div class="q" id="q"></div>

    <div class="minebox">
      <label for="mine">① 我的默写（写 LaTeX 也行、写英文句子也行；先写完再看答案）</label>
      <details class="texwrap" id="texWrap">
        <summary>∑ LaTeX 编辑框（点开：手打 LaTeX，下面实时预览，拼好插入默写框）</summary>
        <div class="texbox">
          <div class="texbtns">
            <button data-tex="\frac{}{}">分式</button>
            <button data-tex="\sqrt{}">根号</button>
            <button data-tex="^{}">上标</button>
            <button data-tex="_{}">下标</button>
            <button data-tex="\lim_{n \to \infty}">lim</button>
            <button data-tex="\sum_{n=1}^{\infty}">∑</button>
            <button data-tex="\forall">∀</button>
            <button data-tex="\exists">∃</button>
            <button data-tex="\in">∈</button>
            <button data-tex="\le">≤</button>
            <button data-tex="\ge">≥</button>
            <button data-tex="\ne">≠</button>
            <button data-tex="\to">→</button>
            <button data-tex="\Rightarrow">⇒</button>
            <button data-tex="\varepsilon">ε</button>
            <button data-tex="\delta">δ</button>
            <button data-tex="\infty">∞</button>
            <button data-tex="\mid">|</button>
          </div>
          <textarea id="texSrc" rows="2" placeholder="直接打 LaTeX，如 \frac{a_n}{b_n} \to 0（不用写 $；其余符号手打即可）"></textarea>
          <div class="texpv" id="texPv"><span class="tag">预览</span><span id="texPvBody"><span class="hint">拼好的公式会显示在这里</span></span></div>
          <div class="btns">
            <button class="primary" id="texToMine">插入到默写框</button>
            <button id="texClear">清空</button>
          </div>
        </div>
      </details>
      <textarea id="mine" rows="4" placeholder="例：$S$ is finite if ...（想手写的话跳过这里，直接拍下面那张图）"></textarea>
      <div class="minepv" id="minePv" hidden></div>
      <div class="btns"><button class="primary" id="show">② 显示答案并对照（空格）</button></div>
    </div>

    <div class="ans" id="ans" hidden></div>

    <div class="ai" id="ai" hidden>
      <div class="aihead">
        <b>③ AI 判定</b>
        <span class="stat" id="aiMsg"></span>
      </div>
      <div class="aiout" id="aiOut" hidden></div>
      <div class="btns">
        <button class="primary" id="aiGo">让 AI 判一下</button>
        <button id="aiImg">手写拍照 / 选图判定</button>
        <button id="copyP">复制给 AI（手动）</button>
      </div>
      <input type="file" id="fileImg" accept="image/*" capture="environment" hidden>
      <div class="preview"><img id="thumb" hidden alt="手写默写"></div>
      <div style="margin-top:14px">
        <label for="aiPaste" class="stat">把 AI 的答复贴到这里 → 保存（以后抽到这张卡会自动显示）</label>
        <textarea id="aiPaste" rows="3" style="margin-top:8px" placeholder="结论：…&#10;漏掉的要点：…&#10;写错的地方：…&#10;提醒：…"></textarea>
        <div class="btns"><button id="aiSave">保存判定</button></div>
      </div>

      <details class="cfg">
        <summary>⚙ AI 设置（选填）—— key 只存在这台设备的浏览器里，不会写进这个 html 文件</summary>
        <div class="grid">
          <div>
            <label for="cfgKey">API key（DeepSeek）</label>
            <input type="password" id="cfgKey" placeholder="sk-...">
            <small>不填也能用「复制给 AI」那条路。发给同学/老师的文件里不含 key；换设备要重填一次。</small>
          </div>
          <div>
            <label for="cfgBase">API 地址</label>
            <input type="text" id="cfgBase">
          </div>
          <div>
            <label for="cfgModel">模型</label>
            <input type="text" id="cfgModel">
            <small>文字判定和手写照片都用它。2026-10-14 实测这个 key 可用的只有 deepseek-flash 与 deepseek-v4-pro。</small>
          </div>
          <div>
            <label class="chk"><input type="checkbox" id="cfgThink"> 深度思考（默认关：快、省、够用；判不准或手写照片潦草时再打开）</label>
          </div>
          <div class="btns">
            <button id="saveCfg">保存设置</button>
            <button id="testCfg">测试连接</button>
          </div>
        </div>
      </details>
    </div>

    <div class="btns" id="acts" hidden>
      <button class="ok" data-r="ok">✓ 过了（1）</button>
      <button class="no" data-r="no">✗ 没过（2）</button>
      <button data-r="skip">跳过（3）</button>
    </div>
  </div>
  <div class="done" id="done" hidden>
    <div id="doneMsg" style="font-size:18px"></div>
    <div class="btns" style="justify-content:center;margin-top:18px">
      <button class="primary" id="again2">再来一轮</button>
      <button id="fallback" hidden>取消「只抽 ✗ 的」，抽全部</button>
    </div>
  </div>
  <div class="kbd">键盘：空格/回车 = 显示答案　1 = 过了　2 = 没过　3 = 跳过（手机直接点按钮）<br>
  默写内容和 AI 判定都存在本机浏览器，换设备不同步。</div>
  <div class="foot">来源：__SRC__　·　改了卡片 md 后重跑 <code>_build_默写卡自测.py</code> 即更新</div>
</div>
<script>__JS__</script>
</body>
</html>
"""


MIME = {".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf"}


def build_single_file(html):
    """把 KaTeX 的 css / js / 字体全部内联，产出单个 .html（手机用，发微信一个文件就够）。"""
    css = open(os.path.join(KATEX_SRC, "katex.min.css"), encoding="utf-8").read()
    js = open(os.path.join(KATEX_SRC, "katex.min.js"), encoding="utf-8").read()
    if "</script" in js.lower():
        raise SystemExit("katex.min.js 里含 </script，不能直接内联")
    fonts_dir = os.path.join(KATEX_SRC, "fonts")
    cache = {}

    def repl(m):
        ref = m.group(1).strip("\"'")
        name = os.path.basename(ref)
        if name not in cache:
            ext = os.path.splitext(name)[1].lower()
            fp = os.path.join(fonts_dir, name)
            if not os.path.isfile(fp):
                cache[name] = None          # 该字体本地不存在（如 .woff 回退版）→ 保留原引用，浏览器会静默跳过
                return "url(%s)" % ref
            with open(fp, "rb") as f:
                cache[name] = "data:%s;base64,%s" % (MIME.get(ext, "application/octet-stream"),
                                                     base64.b64encode(f.read()).decode())
        return "url(%s)" % cache[name]

    css = re.sub(r"url\(([^)]+)\)", repl, css)
    external = [k for k, v in cache.items() if v is None]
    html = html.replace('<link rel="stylesheet" href="katex/katex.min.css">', "<style>" + css + "</style>")
    html = html.replace('<script src="katex/katex.min.js"></script>', "<script>" + js + "</script>")
    inlined = sum(1 for v in cache.values() if v)      # 真正内联进去的字体文件数
    return html, inlined, external


def main():
    with open(MD_PATH, encoding="utf-8") as f:
        raw_md = f.read()
    cards = parse_cards(raw_md)
    if not cards:
        raise SystemExit("没解析到卡片，检查 md 的 '## 卡 ' 格式")
    os.makedirs(OUT_DIR, exist_ok=True)

    dst_katex = os.path.join(OUT_DIR, "katex")
    if not os.path.isdir(dst_katex):
        if not os.path.isdir(KATEX_SRC):
            raise SystemExit("找不到本地 KaTeX：%s" % KATEX_SRC)
        shutil.copytree(KATEX_SRC, dst_katex)

    title = md_title(raw_md, TITLE_DEFAULT)
    src_name = os.path.basename(MD_PATH)
    store_key = "cards:" + src_name           # 每个题库一个独立进度（file:// 下所有页面共用一个 localStorage）
    js = (JS.replace("__CARDS__", json.dumps(cards, ensure_ascii=False))
            .replace("__STOREKEY__", store_key)
            .replace("__DEFAULT_BASE__", DEFAULT_BASE)
            .replace("__DEFAULT_MODEL__", DEFAULT_MODEL))
    html = (HTML
            .replace("__TITLE__", title)
            .replace("__CSS__", CSS)
            .replace("__JS__", js)
            .replace("__SRC__", src_name))
    out = os.path.join(OUT_DIR, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    if "--single" in sys.argv:
        single, nfonts, external = build_single_file(html)
        out2 = os.path.join(OUT_DIR, os.path.splitext(os.path.basename(MD_PATH))[0] + "-单文件.html")
        with open(out2, "w", encoding="utf-8") as f:
            f.write(single)
        print("单文件版:", out2)
        print("内联字体:", nfonts, "个；无本地文件的回退格式引用:", len(external), "条（无害，浏览器静默跳过）")
        print("单文件大小: %.1f KB" % (os.path.getsize(out2) / 1024))

    print("卡片数:", len(cards))
    print("输出:", out)
    print("大小: %.1f KB" % (os.path.getsize(out) / 1024))
    print("KaTeX:", dst_katex)


if __name__ == "__main__":
    main()
