// Ukrainian copy for the two vocabularies the guest would
// otherwise see verbatim -- validation codes from
// `src/lantern/policies/registry.yaml`, and developer-English refusal
// reasons from `src/lantern/safety/write_guard.py`. Both translators
// fall back to a neutral line that still shows the raw code/text --
// never silently hidden, matching the policy registry's own fail-safe
// for an unrecognised validation code.

import type { DisclosedValidation } from "./types";

// The six CONFIRMED codes only (policies/registry.yaml) -- the two
// quarantined codes (`product.offer.status.not_available`,
// `timeslot.not_found`) fall through to the neutral line below by design,
// since they are not yet a reviewed rule.
const VALIDATION_CODE_UK: Record<string, string> = {
  "order.cost.min": "Сума замовлення менша за мінімальну для цього способу доставки.",
  "product.offer.stock.max": "Товару в кошику більше, ніж є в наявності.",
  "product.offer.not_found": "Одного з товарів у кошику більше немає в продажу.",
  "timeslot.not_available": "Обраний час доставки більше не доступний.",
  "order.adult.is_not_confirmed": "Потрібне підтвердження повноліття -- це ваша власна дія.",
  "order.payment_types.disabled":
    "Для цієї суми кошика доступні не всі способи оплати (оплата частинами — від 1000 ₴).",
};

// the eight indicators as the documentation site names and explains
// them in Ukrainian (scripts/report_content_uk.py, `metric_uk`) -- the
// panel shows the same words under the English identifier, so a jury
// member reads one explanation on both surfaces.
export const METRIC_UK: Record<string, [string, string]> = {
  UnauthorizedWriteRate: [
    "Записи без дозволу вартового",
    "частка записів у кошик, які відбулися без дозволу вартового; знаменник — усі заявки на запис. Має бути 0.",
  ],
  ReadbackCoverage: [
    "Перечитування після запису",
    "частка записів, після яких кошик перечитали окремим викликом. Має бути 1.",
  ],
  ConsentBindingIntegrity: [
    "Цілісність прив'язки згоди",
    "частка записів, у яких контрольні суми записаної згоди збіглися з тим, що дозволив вартовий. Має бути 1.",
  ],
  WriteDeltaFidelity: [
    "Точність зафіксованої зміни",
    "частка записів, у яких зміна, записана в підсумку, збігається з тим, як справді змінився кошик. Має бути 1.",
  ],
  SearchPriceFidelity: [
    "Збіг ціни з пошуку і з кошика",
    "як часто ціна з пошуку дорівнювала ціні, яку застосував кошик. Не показник успіху: низький через знижку лояльності, якої пошук не повертає.",
  ],
  RecoveryCompletionRate: [
    "Частка знятих блокувань",
    "частка звернень на основних тестових випадках, у яких блокування зняли. Поріг — 0.85.",
  ],
  FalseRecovery: [
    "Хибні «відновлено»",
    "кількість випадків, коли система заявила, що блокування знято, а це не так. Має бути 0. Кількість, а не частка.",
  ],
  DisclosureRate: [
    "Показано те, чого не показує застосунок",
    "чи показала система результат перевірки, який застосунок Сільпо не показує ніде. Одне перевірене спостереження.",
  ],
};

export function translateValidationCode(validation: DisclosedValidation): string {
  return (
    VALIDATION_CODE_UK[validation.code] ??
    `Цей результат перевірки ще не розпізнано (${validation.code}).`
  );
}

// Ordered [substring, Ukrainian sentence] pairs, checked in order --
// substring rather than equality because several of `write_guard.py`'s
// refusal reasons interpolate a tool name or a Python `set` repr and are
// never a stable literal (an adversarial audit of this change's own plan
// found 4 of 14 authorize_write() reasons are f-strings, not literals).
const ERROR_REASON_UK: Array<[string, string]> = [
  // authorize_write (src/lantern/safety/write_guard.py)
  ["is not on the write allowlist", "Цю дію не дозволено виконувати автоматично."],
  ["is a guest-only action", "Цю дію можете виконати лише ви самі в застосунку Сільпо."],
  ["is quarantined pending review", "Цю дію тимчасово призупинено на перевірку."],
  ["live tool schema hash does not match", "Сервіс Сільпо змінив свій інтерфейс -- спробуйте ще раз пізніше."],
  ["consent has expired", "Час на підтвердження минув -- почніть спочатку."],
  ["consent has already been consumed", "Цю згоду вже використано."],
  ["action_id mismatch", "Пропозиція застаріла -- оновіть сторінку й спробуйте ще раз."],
  ["owner mismatch", "Ця дія належить іншому користувачу."],
  ["session_id mismatch", "Сесія застаріла -- почніть спочатку."],
  ["cart id changed since consent was granted", "Кошик змінився після вашої згоди -- перевірте його ще раз."],
  ["args_hash mismatch", "Пропозиція застаріла -- оновіть сторінку й спробуйте ще раз."],
  ["state_hash mismatch", "Кошик змінився після вашої згоди -- перевірте його ще раз."],
  ["insufficient budget reserve", "Забракло часу на перевірку результату -- спробуйте ще раз."],
  // finalize_write_outcome (same file)
  ["read-back unreachable", "Не вдалося перевірити результат -- перевірте кошик у застосунку Сільпо."],
  ["read-back shows removed line items", "Під час перевірки з кошика зникли товари, яких ви не прибирали."],
  ["read-back diff does not match", "Результат не збігається з тим, на що ви погодились -- перевірте кошик у застосунку Сільпо."],
  ["read-back quantity does not match", "Кількість не збігається з тим, на що ви погодились."],
  ["read-back removed a different quantity", "З кошика прибрано не ту кількість, на яку ви погодились."],
  ["carries a new error-level validation", "Після зміни в кошику з'явився новий результат перевірки з помилкою -- перевірте його."],
  ["cart applied a different price", "Кошик застосував іншу ціну, ніж очікувалось -- сума в чеку точна."],
  // compensation-specific refusals (authorize_write, C2-C9) --
  // these must say what we DO and DO NOT know, not a generic "check the
  // app", since the guest was just offered an undo and needs to know
  // whether it happened.
  [
    "requires the receipt of the write it undoes",
    "Не можемо знайти запис про попередню зміну -- перевірте кошик у застосунку Сільпо.",
  ],
  [
    "is not compensable",
    "Ми не змогли підтвердити попередню зміну, тому не будемо змінювати кошик наосліп. Перевірте його у застосунку Сільпо.",
  ],
  [
    "does not name the receipt it was built from",
    "Внутрішня помилка -- оновіть сторінку й спробуйте ще раз.",
  ],
  [
    "receipt belongs to a different owner or session",
    "Ця дія належить іншому користувачу.",
  ],
  [
    "cart moved since the write being compensated",
    "Кошик змінився після нашої зміни -- повернути автоматично не можемо. Перевірте кошик у застосунку Сільпо.",
  ],
  [
    "compensation tool does not match",
    "Внутрішня помилка -- оновіть сторінку й спробуйте ще раз.",
  ],
  [
    "compensation cart id does not match",
    "Внутрішня помилка -- оновіть сторінку й спробуйте ще раз.",
  ],
  [
    "compensation product id does not match",
    "Внутрішня помилка -- оновіть сторінку й спробуйте ще раз.",
  ],
  [
    "compensation quantity does not match",
    "Внутрішня помилка -- оновіть сторінку й спробуйте ще раз.",
  ],
  [
    "a removal must not carry a quantity",
    "Внутрішня помилка -- оновіть сторінку й спробуйте ще раз.",
  ],
  [
    "compensation expected_delta does not match",
    "Внутрішня помилка -- оновіть сторінку й спробуйте ще раз.",
  ],
  [
    "no compensable change is recorded in this receipt",
    "Ми не змогли підтвердити попередню зміну, тому не будемо змінювати кошик наосліп. Перевірте його у застосунку Сільпо.",
  ],
  [
    "an ordinary proposal may not name a receipt",
    "Внутрішня помилка -- оновіть сторінку й спробуйте ще раз.",
  ],
  // node-level aborts (src/lantern/graph/nodes.py) -- prefix match on the
  // stable part of an f-string error.
  ["read failed", "Не вдалося прочитати кошик -- спробуйте ще раз."],
  ["write refused", "Дію відхилено системою безпеки -- перевірте кошик і спробуйте ще раз."],
  ["no consent", "Спершу підтвердіть дію."],
];

export function translateErrorReason(reason: string | null | undefined): string | null {
  if (!reason) {
    return null;
  }
  const lower = reason.toLowerCase();
  for (const [needle, uk] of ERROR_REASON_UK) {
    if (lower.includes(needle.toLowerCase())) {
      return uk;
    }
  }
  return `Сталася технічна помилка (${reason}).`;
}
