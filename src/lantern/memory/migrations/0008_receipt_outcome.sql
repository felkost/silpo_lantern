-- A verified write is not a recovered cart. Measured on a live run: the
-- write landed exactly as consented, `status` read `receipt`, and the
-- cart stayed blocked by 2.98 UAH -- the catalogue advertised 96.49 for a
-- product the cart then priced at 86.84, and no pre-write endpoint
-- exposes that discount (`find_products_batch` and
-- `silpo_get_product_details` both report the higher figure with
-- `oldPrice: null`).
--
-- Without these columns the receipt cannot answer the only question the
-- guest actually asked -- "can I check out now?" -- and the brief's
-- recovery metrics would have to re-derive it from the stored
-- `after_state` JSON on every read.
ALTER TABLE receipts ADD COLUMN blocker_cleared BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE receipts ADD COLUMN remaining_gap NUMERIC;
