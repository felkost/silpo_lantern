// G7 (D-G7-04): Ukrainian copy for the two vocabularies the guest would
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
  "order.payment_types.disabled": "Не всі способи оплати доступні для цього кошика.",
};

export function translateValidationCode(validation: DisclosedValidation): string {
  return (
    VALIDATION_CODE_UK[validation.code] ??
    `Цю позначку кошика ще не розпізнано (${validation.code}).`
  );
}

// Ordered [substring, Ukrainian sentence] pairs, checked in order --
// substring rather than equality because several of `write_guard.py`'s
// refusal reasons interpolate a tool name or a Python `set` repr and are
// never a stable literal (an adversarial audit of this stage's own plan
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
  ["read-back diff does not match the consented product", "Результат не збігається з тим, на що ви погодились -- перевірте кошик."],
  ["read-back quantity does not match", "Додана кількість не збігається з тим, на що ви погодились."],
  ["carries a new error-level validation", "Після зміни в кошику з'явилась нова позначка -- перевірте його."],
  ["cart applied a different price", "Кошик застосував іншу ціну, ніж очікувалось -- сума в чеку точна."],
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
