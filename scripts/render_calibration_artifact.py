"""renders the labelling sheet as a page that can be
published as an Artifact, so the labels are stored server-side and can be
read back directly.

The first sheet was a local HTML file. Two things went wrong with it, both
worth keeping in mind rather than in prose: opened from disk, a page's
`localStorage` throws in several browser configurations and killed the
script on its second line -- silently, so the save button did nothing --
and even when it works, getting the answers out means copying JSON by
hand. Neither is the labeller's problem to solve.

The pairs come from `judge_calibration_pairs.json`, and the `expected`
field and both `origin` fields are DROPPED here: the sheet must not carry
which member was constructed or which model wrote which, or the labels
stop being an independent reference point.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from src.lantern.config import PROJECT_ROOT

EVIDENCE_DIR = PROJECT_ROOT / "datasets" / "evidence"
PAIRS_PATH = EVIDENCE_DIR / "judge_calibration_pairs.json"
OUT_PATH = EVIDENCE_DIR / "judge_calibration_artifact.html"

QUESTIONS = {
    "RecoveryExplanationQuality": (
        "Який текст краще пояснює ситуацію українською — точніше, "
        "природніше, без кальок і помилок у числах чи одиницях?"
    ),
    "UncertaintyAndRefusal": (
        "Який текст чесніше говорить про межі того, що система може "
        "зробити — не обіцяє зайвого і не приховує відмову?"
    ),
    "UserControlAndConsentClarity": (
        "З якого тексту гостю ясніше, на що саме він погоджується — "
        "що зміниться в кошику і на яку суму?"
    ),
}


def _blind_pairs() -> List[Dict[str, Any]]:
    document = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))
    blind = []
    for pair in document["pairs"]:
        blind.append(
            {
                "id": pair["pair_id"],
                "question": QUESTIONS[pair["dimension"]],
                "a": pair["a"]["text"],
                "b": pair["b"]["text"],
            }
        )
    return blind


HEAD = """<title>Розмітка пар для судді</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?\
family=IBM+Plex+Sans:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,400;\
8..60,600&display=swap">
<style>
:root {
  --paper: #FAF9F7;
  --card: #FFFFFF;
  --ink: #24242E;
  --muted: #6B7280;
  --hair: #DAD6E0;
  --accent: #6440C9;
  --accent-tint: #F0ECFB;
  --good: #2F7A55;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper: #17161C;
    --card: #201F28;
    --ink: #ECEAF2;
    --muted: #9C97AC;
    --hair: #35323F;
    --accent: #B3A0F0;
    --accent-tint: #272238;
    --good: #6FC79A;
  }
}
:root[data-theme="dark"] {
  --paper: #17161C;
  --card: #201F28;
  --ink: #ECEAF2;
  --muted: #9C97AC;
  --hair: #35323F;
  --accent: #B3A0F0;
  --accent-tint: #272238;
  --good: #6FC79A;
}
* { box-sizing: border-box; }
body {
  background: var(--paper);
  color: var(--ink);
  font-family: "IBM Plex Sans", system-ui, sans-serif;
  margin: 0;
  padding: 0 20px 140px;
  line-height: 1.55;
}
.wrap { max-width: 760px; margin: 0 auto; }
header { padding: 44px 0 20px; }
h1 {
  font-family: "Source Serif 4", Georgia, serif;
  font-weight: 600;
  font-size: 30px;
  margin: 0 0 6px;
  text-wrap: balance;
}
.sub { color: var(--muted); font-size: 15px; margin: 0; }
.brief {
  border-left: 3px solid var(--accent);
  padding: 2px 0 2px 16px;
  margin: 26px 0 8px;
  display: flex; flex-direction: column; gap: 10px;
  font-size: 14.5px;
}
.brief b { font-weight: 600; }
.pair { padding: 30px 0; border-top: 1px solid var(--hair); }
.eyebrow {
  font-size: 11.5px; letter-spacing: .1em; text-transform: uppercase;
  color: var(--muted); font-weight: 600; margin: 0 0 8px;
  font-variant-numeric: tabular-nums;
}
.q { font-size: 15px; font-weight: 500; margin: 0 0 16px; }
.opts { display: flex; flex-direction: column; gap: 10px; }
.opt {
  display: grid; grid-template-columns: 26px 1fr; gap: 14px;
  align-items: start;
  background: var(--card);
  border: 1px solid var(--hair);
  border-left: 3px solid transparent;
  border-radius: 4px;
  padding: 14px 16px;
  cursor: pointer;
}
.opt:hover { border-color: var(--accent); }
.opt:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
.opt.on { border-left-color: var(--accent); background: var(--accent-tint); }
.opt input { margin: 4px 0 0; accent-color: var(--accent); }
.opt .tag {
  font-weight: 600; font-size: 13px; color: var(--muted);
  grid-column: 1; text-align: center;
}
.opt.on .tag { color: var(--accent); }
.body {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 16px; white-space: pre-wrap;
}
.same .body { font-family: "IBM Plex Sans", system-ui, sans-serif;
  font-size: 14px; color: var(--muted); }
footer {
  position: fixed; left: 0; right: 0; bottom: 0;
  background: var(--card); border-top: 1px solid var(--hair);
  padding: 12px 20px;
}
.fwrap {
  max-width: 760px; margin: 0 auto;
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
}
.count { font-weight: 600; font-variant-numeric: tabular-nums; }
.track { flex: 1; min-width: 120px; height: 6px; background: var(--hair);
  border-radius: 3px; overflow: hidden; }
.fill { height: 100%; width: 0; background: var(--accent);
  transition: width .2s ease; }
.state { font-size: 13px; color: var(--muted); }
.state.ok { color: var(--good); }
@media (prefers-reduced-motion: reduce) { .fill { transition: none; } }
</style>"""


def build_page(pairs: List[Dict[str, Any]]) -> str:
    data = json.dumps(pairs, ensure_ascii=False)
    return f"""{HEAD}
<div class="wrap">
<header>
  <h1>Розмітка пар для калібрування судді</h1>
  <p class="sub">{len(pairs)} пар · Lantern</p>
</header>
<div class="brief">
  <span><b>Оберіть текст, який краще відповідає питанню над парою.</b>
  Якщо різниці справді не бачите — оберіть «Однаково». Це повноцінна
  відповідь: вимушений вибір там, де різниці немає, створює фальшиву
  незгоду й занижує цифру.</span>
  <span><b>Чого тут навмисно немає.</b> Ви не бачите, яка модель що
  написала і який текст «правильний». Порядок перемішано. Ваша розмітка
  має бути незалежною точкою відліку, а не підтвердженням чужої.</span>
  <span><b>Відповіді зберігаються самі</b> — сторінку можна закрити й
  повернутись.</span>
</div>
<main id="pairs"></main>
</div>
<footer><div class="fwrap">
  <span class="count"><span id="done">0</span> / {len(pairs)}</span>
  <span class="track"><span class="fill" id="fill"></span></span>
  <span class="state" id="state">Готово до розмітки</span>
</div></footer>
<script>
const PAIRS = {data};
const answers = {{}};
let db = null;

const main = document.getElementById('pairs');
const stateEl = document.getElementById('state');

function option(pair, value, text, isSame) {{
  const label = document.createElement('label');
  label.className = 'opt' + (isSame ? ' same' : '');
  label.dataset.pair = pair.id;
  label.dataset.value = value;
  const input = document.createElement('input');
  input.type = 'radio';
  input.name = pair.id;
  input.value = value;
  const tag = document.createElement('span');
  tag.className = 'tag';
  tag.textContent = value === 'tie' ? '=' : value;
  const body = document.createElement('span');
  body.className = 'body';
  body.textContent = text;
  label.append(input, tag, body);
  input.addEventListener('change', () => choose(pair.id, value));
  return label;
}}

PAIRS.forEach((pair, index) => {{
  const section = document.createElement('section');
  section.className = 'pair';
  const eyebrow = document.createElement('p');
  eyebrow.className = 'eyebrow';
  eyebrow.textContent = 'Пара ' + (index + 1) + ' з ' + PAIRS.length;
  const question = document.createElement('p');
  question.className = 'q';
  question.textContent = pair.question;
  const opts = document.createElement('div');
  opts.className = 'opts';
  opts.append(
    option(pair, 'A', pair.a, false),
    option(pair, 'B', pair.b, false),
    option(pair, 'tie', 'Однаково — різниці не бачу', true)
  );
  section.append(eyebrow, question, opts);
  main.append(section);
}});

function paint() {{
  document.querySelectorAll('.opt').forEach(el => {{
    const on = answers[el.dataset.pair] === el.dataset.value;
    el.classList.toggle('on', on);
    const input = el.querySelector('input');
    if (on && !input.checked) input.checked = true;
  }});
  const done = Object.keys(answers).length;
  document.getElementById('done').textContent = done;
  document.getElementById('fill').style.width =
    (100 * done / PAIRS.length) + '%';
}}

function choose(pairId, value) {{
  answers[pairId] = value;
  paint();
  save();
}}

let pending = null;
function save() {{
  if (!db) {{
    stateEl.textContent = 'Збереження недоступне — не закривайте вкладку';
    return;
  }}
  clearTimeout(pending);
  pending = setTimeout(async () => {{
    try {{
      await db.doc('calibration/labels').set({{
        labeller: 'author',
        labels: answers,
        updatedAt: new Date().toISOString()
      }});
      stateEl.textContent = 'Збережено';
      stateEl.className = 'state ok';
    }} catch (e) {{
      stateEl.textContent = 'Не збереглося: ' + (e && e.code ? e.code : 'помилка');
      stateEl.className = 'state';
    }}
  }}, 400);
}}

paint();

claude.use('db').then(async (namespace) => {{
  db = namespace;
  if (!db) {{
    stateEl.textContent = 'Збереження недоступне — не закривайте вкладку';
    return;
  }}
  try {{
    const snap = await db.doc('calibration/labels').get();
    if (snap.exists) {{
      const stored = snap.data().labels || {{}};
      Object.keys(stored).forEach(k => {{ answers[k] = stored[k]; }});
      paint();
      stateEl.textContent = 'Відновлено попередні відповіді';
      stateEl.className = 'state ok';
    }}
  }} catch (e) {{
    stateEl.textContent = 'Не вдалося прочитати збережене';
  }}
}});
</script>"""


def main() -> int:
    pairs = _blind_pairs()
    OUT_PATH.write_text(build_page(pairs), encoding="utf-8")
    print(f"wrote {OUT_PATH.relative_to(PROJECT_ROOT)} ({len(pairs)} pairs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
