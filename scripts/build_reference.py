"""Membangun ulang CSV referensi FoodKeeper dari file Excel asli.

Pemakaian:
    python scripts/build_reference.py path/ke/FoodKeeper-Data.xls

File .xls lama membutuhkan paket ``xlrd`` (ada di requirements.txt).
Hasil: data/foodkeeper_product.csv dan data/foodkeeper_category.csv
"""
import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def main(path: str) -> None:
    src = Path(path)
    engine = "xlrd" if src.suffix.lower() == ".xls" else None
    product = pd.read_excel(src, sheet_name="Product", engine=engine)
    category = pd.read_excel(src, sheet_name="Category", engine=engine)
    DATA_DIR.mkdir(exist_ok=True)
    product.to_csv(DATA_DIR / "foodkeeper_product.csv", index=False, encoding="utf-8")
    category.to_csv(DATA_DIR / "foodkeeper_category.csv", index=False, encoding="utf-8")
    print(f"Produk: {len(product)} baris | Kategori: {len(category)} baris")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
