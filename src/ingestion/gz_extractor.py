"""Extract and rename Nielsen DDM gzip files."""

from __future__ import annotations

import gzip
import shutil
from pathlib import Path

RENAME_RULES = {
    "aggregated_data": "data.txt",
    "characteristics": "charact.txt",
    "hierarchies": "hierar.txt",
    "market": "market.txt",
    "period": "period.txt",
    "product": "product.txt",
    "facts": "facts.txt",
}


def get_target_name(filename: str) -> str | None:
    filename = filename.lower()

    for pattern, new_name in RENAME_RULES.items():
        if pattern in filename:
            return new_name

    return None


def process_folder(folder_path: Path) -> None:
    print(f"\nProcesando carpeta: {folder_path}")

    gz_files = list(folder_path.glob("*.gz"))
    print(f"Archivos GZ encontrados: {len(gz_files)}")

    for gz_file in gz_files:
        try:
            final_name = get_target_name(gz_file.name)

            if final_name is None:
                print(f"  [SKIP] No reconocido: {gz_file.name}")
                continue

            output_file = folder_path / final_name

            if output_file.exists():
                output_file.unlink()

            with gzip.open(gz_file, "rb") as f_in:
                with open(output_file, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)

            print(f"  [OK] {gz_file.name} -> {final_name}")

            gz_file.unlink()
            print(f"  [OK] Eliminado: {gz_file.name}")

        except OSError as exc:
            print(f"  [ERROR] {gz_file.name}: {exc}")


def extract_categories(base_path: Path, categories: list[str]) -> None:
    for categoria in categories:
        categoria_path = base_path / categoria

        if not categoria_path.exists():
            print(f"\nNo existe la carpeta: {categoria_path}")
            continue

        print(f"\n{'=' * 50}")
        print(f"CATEGORIA: {categoria}")
        print(f"{'=' * 50}")

        for folder in sorted(categoria_path.iterdir()):
            if folder.is_dir():
                process_folder(folder)

    print("\nProceso terminado.")
