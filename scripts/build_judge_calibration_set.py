"""G9 follow-up (T20): builds the human-labelling set for judge
calibration, and the sheet the author labels it on.

**Why the pairs are built rather than picked.** D-G9-09 refuses a judge
whose prompt and whose calibration set are authored by the same person:
that is a self-graded oracle, and it reports agreement with itself. So
nothing here is chosen for how it will score.

Three properties this script exists to guarantee:

* **The texts are real.** Every member of every pair is an output some
  model actually produced -- either a live `guest_text_uk` from a tracked
  replay bundle, or a UA-Eval generation from G4. Nothing is written by
  whoever prepares the set.
* **Most pairs are naturally uncertain.** Two thirds are two DIFFERENT
  models answering the SAME UA-Eval prompt, so neither member is
  constructed and the better one is a genuine judgement. Agreement on
  pairs whose answer is obvious measures very little; those exist to
  catch a broken judge, not to produce the headline number, and the
  report breaks the statistic down by kind for exactly that reason.
* **The constructed pairs are DELETIONS.** The one dimension with no
  natural pair source (consent clarity) is built by removing a clause
  from a real text, never by writing a worse one -- so even there, every
  word the author reads was produced by the system.

**The UA-Eval rows' own scores are deliberately unused.** They were
produced by an LLM judge (x-ai/grok-4.6, see `config/models.yaml`), and
calibrating one LLM judge against another's scores is the same
self-graded oracle one step removed. Only the generated TEXT is taken;
selection is seeded-random and never reads a score, so the set cannot be
skewed toward rows some earlier judge liked.

The sheet is blind: it shows a pair id, the question, and two texts in a
seeded-random A/B order. It carries no hint of which member was
constructed, which model wrote which, or what any judge would say.
"""

from __future__ import annotations

import json
import random
from typing import Any, Dict, List, Tuple

from src.lantern.config import PROJECT_ROOT

EVIDENCE_DIR = PROJECT_ROOT / "datasets" / "evidence"
BUNDLE_DIR = PROJECT_ROOT / "datasets" / "fixtures" / "replay"
UA_EVAL_PATH = EVIDENCE_DIR / "ua_eval_20260906T165532Z.json"
PAIRS_PATH = EVIDENCE_DIR / "judge_calibration_pairs.json"
SHEET_PATH = EVIDENCE_DIR / "judge_calibration_sheet.html"
LABELS_PATH = EVIDENCE_DIR / "judge_calibration_labels.json"

SEED = 20260909

# UA-Eval's own categories, mapped to the judge each one informs. The
# refusal category is what makes `UncertaintyAndRefusal` labelable from
# natural pairs instead of from text someone had to invent.
QUALITY_CATEGORIES = {
    "validation_code_explanation",
    "numerals_and_sums",
    "units_and_package_size",
    "product_name_declension",
}
REFUSAL_CATEGORY = "polite_refusal"

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


def _ua_eval_rows() -> List[Dict[str, Any]]:
    rows = json.loads(UA_EVAL_PATH.read_text(encoding="utf-8"))
    return [
        row
        for row in rows
        if (row.get("generation") or {}).get("text")
        and row.get("category")
        and row.get("model_id")
    ]


def _natural_pairs(
    rows: List[Dict[str, Any]],
    categories: set,
    dimension: str,
    count: int,
    rng: random.Random,
) -> List[Dict[str, Any]]:
    """Two different models on the same prompt. Selection never reads a
    score -- see the module docstring."""
    by_prompt: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        if row["category"] in categories:
            by_prompt.setdefault(row["prompt_id"], []).append(row)

    candidates: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []
    for prompt_id, group in sorted(by_prompt.items()):
        if len(group) < 2:
            continue
        first, second = rng.sample(group, 2)
        # Two models answering the same prompt sometimes write byte-identical
        # text, and such a pair discriminates nothing -- it can only add
        # noise to an agreement statistic, or a tie that has to be explained
        # away afterwards. Found the hard way: CAL-03 of the first set was
        # exactly this.
        if first["generation"]["text"] == second["generation"]["text"]:
            continue
        candidates.append((prompt_id, first, second))

    rng.shuffle(candidates)
    pairs = []
    for prompt_id, first, second in candidates[:count]:
        pairs.append(
            {
                "kind": "natural",
                "dimension": dimension,
                "source": f"ua-eval:{prompt_id}",
                "left": {
                    "text": first["generation"]["text"],
                    "origin": first["model_id"],
                },
                "right": {
                    "text": second["generation"]["text"],
                    "origin": second["model_id"],
                },
                # Nobody knows which is better -- that is the point.
                "constructed_worse": None,
            }
        )
    return pairs


def _explainer_texts() -> List[str]:
    seen: List[str] = []
    for path in sorted(BUNDLE_DIR.glob("*.json")):
        bundle = json.loads(path.read_text(encoding="utf-8"))
        for output in bundle["payload"]["llm"].get("explainer", []):
            text = output.get("guest_text_uk")
            if text and text not in seen:
                seen.append(text)
    return seen


def _strip_the_amount_clause(text: str) -> str:
    """Removes the clause that says what the change costs, leaving the
    rest of the real sentence untouched.

    The live explainer's output is one templated sentence -- "Додайте X —
    це додасть N ₴ до суми кошика." -- so deleting everything from the
    dash removes exactly the information the guest needs to know what
    they are approving, and adds nothing. A DELETION, never a rewrite:
    the point of the pair is that both members are text the system
    produced.
    """
    for dash in ("—", "–", " - "):
        if dash in text:
            head = text.split(dash)[0].rstrip().rstrip(",")
            return head + "."
    return text


def _constructed_pairs(
    texts: List[str], count: int, rng: random.Random
) -> List[Dict[str, Any]]:
    usable = [t for t in texts if _strip_the_amount_clause(t) != t]
    rng.shuffle(usable)
    pairs = []
    for text in usable[:count]:
        pairs.append(
            {
                "kind": "constructed",
                "dimension": "UserControlAndConsentClarity",
                "source": "explainer-bundle",
                "left": {"text": text, "origin": "live-explainer"},
                "right": {
                    "text": _strip_the_amount_clause(text),
                    "origin": "live-explainer-minus-amount",
                },
                # The full sentence is the better member by construction:
                # it says what the change costs and the other does not.
                "constructed_worse": "right",
            }
        )
    return pairs


def build_pairs() -> List[Dict[str, Any]]:
    rng = random.Random(SEED)
    rows = _ua_eval_rows()
    pairs = (
        _natural_pairs(rows, QUALITY_CATEGORIES, "RecoveryExplanationQuality", 12, rng)
        + _natural_pairs(rows, {REFUSAL_CATEGORY}, "UncertaintyAndRefusal", 6, rng)
        + _constructed_pairs(_explainer_texts(), 7, rng)
    )
    rng.shuffle(pairs)

    built = []
    for index, pair in enumerate(pairs, start=1):
        # A/B order is randomised per pair, so a labeller who notices that
        # (say) the longer text keeps winning cannot ride that pattern.
        flip = rng.random() < 0.5
        a, b = (pair["right"], pair["left"]) if flip else (pair["left"], pair["right"])
        worse = pair["constructed_worse"]
        if worse is not None:
            better_side = "left" if worse == "right" else "right"
            expected = "B" if (better_side == "left") == flip else "A"
        else:
            expected = None
        built.append(
            {
                "pair_id": f"CAL-{index:02d}",
                "dimension": pair["dimension"],
                "kind": pair["kind"],
                "source": pair["source"],
                "a": a,
                "b": b,
                # Present ONLY for constructed pairs, and never rendered
                # into the sheet.
                "expected": expected,
            }
        )
    return built


def build_sheet(pairs: List[Dict[str, Any]]) -> str:
    def esc(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    blocks = []
    for pair in pairs:
        question = QUESTIONS[pair["dimension"]]
        blocks.append(f"""
<section class="pair" data-pair="{pair['pair_id']}">
  <h2>{pair['pair_id']}</h2>
  <p class="q">{esc(question)}</p>
  <div class="texts">
    <label class="opt">
      <input type="radio" name="{pair['pair_id']}" value="A">
      <span class="tag">A</span>
      <span class="txt">{esc(pair['a']['text'])}</span></label>
    <label class="opt">
      <input type="radio" name="{pair['pair_id']}" value="B">
      <span class="tag">B</span>
      <span class="txt">{esc(pair['b']['text'])}</span></label>
    <label class="opt tie">
      <input type="radio" name="{pair['pair_id']}" value="tie">
      <span class="tag">=</span>
      <span class="txt">Не бачу різниці / обидва однакові</span></label>
  </div>
</section>""")

    return f"""<!doctype html>
<html lang="uk"><head><meta charset="utf-8">
<title>Калібрування судді — розмітка</title>
<style>
 body {{ font-family: Arial, Helvetica, sans-serif; max-width: 900px;
        margin: 0 auto; padding: 24px; color: #24242E; }}
 h1 {{ font-size: 20px; }}
 .intro {{ background: #F7F7FA; border: 1px solid #D1D5DB; padding: 16px;
           border-radius: 6px; font-size: 14px; line-height: 1.5; }}
 .pair {{ border-top: 1px solid #D1D5DB; padding: 18px 0; }}
 .pair h2 {{ font-size: 13px; color: #6B7280; margin: 0 0 6px; }}
 .q {{ font-size: 14px; font-weight: 700; margin: 0 0 12px; }}
 .opt {{ display: flex; gap: 10px; align-items: flex-start; padding: 10px;
         border: 1px solid #D1D5DB; border-radius: 6px; margin-bottom: 8px;
         cursor: pointer; }}
 .opt:hover {{ background: #F7F7FA; }}
 .tag {{ font-weight: 700; min-width: 18px; }}
 .txt {{ font-size: 14px; line-height: 1.5; }}
 .tie .txt {{ color: #6B7280; }}
 #out {{ width: 100%; height: 160px; font-family: monospace; font-size: 12px; }}
 #bar {{ position: sticky; bottom: 0; background: #fff; border-top: 2px solid #24242E;
         padding: 12px 0; }}
 button {{ font-size: 14px; padding: 8px 14px; cursor: pointer; }}
 #count {{ font-weight: 700; }}
 .warn {{ color: #6440C9; font-size: 13px; }}
</style></head><body>
<h1>Калібрування судді — розмітка {len(pairs)} пар</h1>
<div class="intro">
<p><b>Що робити.</b> У кожній парі оберіть текст, який краще відповідає
питанню над нею. Якщо різниці справді не бачите — оберіть «=». Це не
помилка і не ухиляння: вимушений вибір там, де різниці немає, створює
фальшиву незгоду й псує цифру.</p>
<p><b>Чого тут навмисно немає.</b> Ви не бачите, яка модель що написала,
який текст «правильний» і що про них скаже суддя. Порядок A/B перемішано.
Це щоб ваша розмітка була незалежною точкою відліку, а не підтвердженням
чужої.</p>
<p><b>Коли закінчите</b> — натисніть кнопку внизу, скопіюйте JSON і
збережіть його у файл <code>datasets/evidence/judge_calibration_labels.json</code>.
Відповіді зберігаються у браузері, тож сторінку можна закрити й повернутись.</p>
</div>
{''.join(blocks)}
<div id="bar">
  <p>Розмічено: <span id="count">0</span> з {len(pairs)}
     <span id="persist" class="warn"></span></p>
  <p id="copied" class="warn"></p>
  <button id="save">Показати JSON для збереження</button>
  <textarea id="out" placeholder="JSON з'явиться тут"></textarea>
</div>
<script>
 // The sheet is opened from disk, and a file:// page's localStorage
 // throws SecurityError in several browser configurations. Unguarded,
 // that killed the whole script on its second line -- so no listeners
 // were ever attached and the button did nothing at all, silently.
 // Persistence is a convenience; labelling must work without it.
 const KEY = "lantern-judge-calibration";
 let store = null;
 try {{ window.localStorage.setItem(KEY + "-probe", "1");
        window.localStorage.removeItem(KEY + "-probe");
        store = window.localStorage; }} catch (e) {{ store = null; }}
 let saved = {{}};
 try {{ if (store) saved = JSON.parse(store.getItem(KEY) || "{{}}"); }}
 catch (e) {{ saved = {{}}; }}
 if (!store) {{
   document.getElementById('persist').textContent =
     "Цей браузер не дозволяє збереження для локального файлу — "
     + "не закривайте вкладку до кінця розмітки.";
 }}
 const radios = document.querySelectorAll('input[type=radio]');
 function refresh() {{
   const names = new Set();
   document.querySelectorAll('input[type=radio]:checked')
           .forEach(r => names.add(r.name));
   document.getElementById('count').textContent = names.size;
 }}
 radios.forEach(r => {{
   if (saved[r.name] === r.value) r.checked = true;
   r.addEventListener('change', () => {{
     saved[r.name] = r.value;
     try {{ if (store) store.setItem(KEY, JSON.stringify(saved)); }}
     catch (e) {{ /* labelling continues without persistence */ }}
     refresh();
   }});
 }});
 refresh();
 document.getElementById('save').addEventListener('click', () => {{
   const labels = {{}};
   document.querySelectorAll('input[type=radio]:checked')
           .forEach(r => labels[r.name] = r.value);
   const out = document.getElementById('out');
   out.value = JSON.stringify(
     {{labeller: "author", labels: labels}}, null, 2);
   out.focus();
   out.select();
   try {{ navigator.clipboard.writeText(out.value);
          document.getElementById('copied').textContent =
            "Скопійовано до буфера (" + Object.keys(labels).length + " відповідей)."; }}
   catch (e) {{ document.getElementById('copied').textContent =
            "Скопіюйте текст із поля нижче вручну."; }}
 }});
</script>
</body></html>"""


def main() -> int:
    pairs = build_pairs()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    PAIRS_PATH.write_text(
        json.dumps({"seed": SEED, "pairs": pairs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    SHEET_PATH.write_text(build_sheet(pairs), encoding="utf-8")

    kinds: Dict[str, int] = {}
    dimensions: Dict[str, int] = {}
    for pair in pairs:
        kinds[pair["kind"]] = kinds.get(pair["kind"], 0) + 1
        dimensions[pair["dimension"]] = dimensions.get(pair["dimension"], 0) + 1
    print(f"wrote {PAIRS_PATH.relative_to(PROJECT_ROOT)} ({len(pairs)} pairs)")
    print(f"  by kind: {kinds}")
    print(f"  by dimension: {dimensions}")
    print(f"wrote {SHEET_PATH.relative_to(PROJECT_ROOT)}")
    print(f"  label file to save: {LABELS_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
