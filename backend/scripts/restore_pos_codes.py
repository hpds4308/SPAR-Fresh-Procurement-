"""
Restores every product's pos_code (and pos_code_flag) from the original
uploaded source file (database/seed/products.csv), overwriting whatever
is currently in the database — including nulls left behind by an old
"Clear All" on the Master Data Sheet, back when POS Code was still
editable there.

Unlike seed_master_data.py (which only INSERTS products that don't exist
yet, and never touches existing rows), this script's whole purpose is to
overwrite existing rows' pos_code back to the source-of-truth value. Safe
to run any number of times — it always just re-applies the same file.

Usage (from /backend, inside the container or a venv with DATABASE_URL set):
    python -m scripts.restore_pos_codes
"""
import csv
import os

from app.core.database import SessionLocal
from app.models import Product

SEED_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "database", "seed")


def main():
    db = SessionLocal()
    path = os.path.join(SEED_DIR, "products.csv")

    updated = 0
    unmatched = []
    still_missing = []

    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            product_code = row["product_code"].strip()
            pos_code = row["pos_code"].strip() or None
            pos_flag = row["pos_code_flag"].strip() or None

            product = db.query(Product).filter_by(product_code=product_code).first()
            if not product:
                unmatched.append(product_code)
                continue

            if product.pos_code != pos_code or product.pos_code_flag != pos_flag:
                product.pos_code = pos_code
                product.pos_code_flag = pos_flag
                updated += 1

            if pos_code is None:
                still_missing.append((product_code, row["description"].strip()))

    db.commit()

    print(f"POS codes restored/verified for {updated} product(s) that had drifted from the source file.")
    if unmatched:
        print(f"\n{len(unmatched)} product_code(s) in products.csv have no matching row in the database:")
        for code in unmatched:
            print(f"  - {code}")
    if still_missing:
        print(f"\n{len(still_missing)} product(s) genuinely have no POS code in the original source file (not an error — just missing at the source):")
        for code, desc in still_missing:
            print(f"  - {code}  {desc}")


if __name__ == "__main__":
    main()
