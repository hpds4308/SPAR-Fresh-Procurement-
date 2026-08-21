"""
Seed the database with initial master data:
  - 13 branches
  - 16 suppliers
  - product categories + units
  - the real 188-item fresh produce product list (with data-quality flags preserved)

Usage (from /backend, inside the container or a venv with DATABASE_URL set):
    python -m scripts.seed_master_data

Idempotent: safe to run more than once — existing rows (matched by unique
code) are left untouched, not duplicated or silently overwritten.
"""
import csv
import os

from app.core.database import SessionLocal
from app.models import Branch, Supplier, ProductCategory, ProductUnit, Product

SEED_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "database", "seed")


def seed_branches(db):
    path = os.path.join(SEED_DIR, "branches.csv")
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            exists = db.query(Branch).filter_by(branch_code=row["branch_code"]).first()
            if not exists:
                db.add(Branch(branch_code=row["branch_code"], branch_name=row["branch_name"]))
    db.commit()
    print(f"Branches seeded: {db.query(Branch).count()}")


def seed_suppliers(db):
    path = os.path.join(SEED_DIR, "suppliers.csv")
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            exists = db.query(Supplier).filter_by(supplier_code=row["supplier_code"]).first()
            if not exists:
                db.add(Supplier(supplier_code=row["supplier_code"], supplier_name=row["supplier_name"]))
    db.commit()
    print(f"Suppliers seeded: {db.query(Supplier).count()}")


def seed_products(db):
    path = os.path.join(SEED_DIR, "products.csv")
    category_cache: dict[str, ProductCategory] = {}
    # Fresh produce is sold by weight by default; adjust per-product later via admin UI if needed.
    unit = db.query(ProductUnit).filter_by(code="kg").first()
    if not unit:
        unit = ProductUnit(code="kg")
        db.add(unit)
        db.commit()

    flagged = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cat_name = row["category"].strip()
            if cat_name not in category_cache:
                cat = db.query(ProductCategory).filter_by(name=cat_name).first()
                if not cat:
                    cat = ProductCategory(name=cat_name)
                    db.add(cat)
                    db.commit()
                category_cache[cat_name] = cat

            exists = db.query(Product).filter_by(product_code=row["product_code"]).first()
            if exists:
                continue

            pos_code = row["pos_code"].strip() or None
            pos_flag = row["pos_code_flag"].strip() or None

            db.add(
                Product(
                    product_code=row["product_code"].strip(),
                    pos_code=pos_code,
                    pos_code_flag=pos_flag,
                    description=row["description"].strip(),
                    category_id=category_cache[cat_name].id,
                    unit_id=unit.id,
                )
            )
            if pos_flag:
                flagged.append((row["product_code"], row["description"], pos_flag))
    db.commit()
    print(f"Products seeded: {db.query(Product).count()}")
    if flagged:
        print("\nData-quality issues flagged for admin review (no values were invented):")
        for code, desc, flag in flagged:
            print(f"  - [{flag}] {code} — {desc}")


def main():
    db = SessionLocal()
    try:
        seed_branches(db)
        seed_suppliers(db)
        seed_products(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
