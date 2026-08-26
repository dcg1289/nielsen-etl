"""Join Nielsen DDM text files within each period folder."""

from __future__ import annotations

from pathlib import Path

import duckdb

from src.ingestion.gz_extractor import RENAME_RULES

FACT_FILE = RENAME_RULES["aggregated_data"]
DIMENSION_FILES = {
    "product": (RENAME_RULES["product"], "product_id"),
    "market": (RENAME_RULES["market"], "market_id"),
    "period": (RENAME_RULES["period"], "period_id"),
}
DEFAULT_OUTPUT_FILE = "joined.txt"


def _posix(path: Path) -> str:
    return path.as_posix()


def join_folder(folder_path: Path, output_file: str = DEFAULT_OUTPUT_FILE) -> bool:
    fact_path = folder_path / FACT_FILE

    if not fact_path.exists():
        print(f"  [SKIP] No existe {FACT_FILE} en {folder_path}")
        return False

    missing_dimensions = [
        filename
        for filename, _ in DIMENSION_FILES.values()
        if not (folder_path / filename).exists()
    ]
    if missing_dimensions:
        print(f"  [SKIP] Faltan dimensiones {missing_dimensions} en {folder_path}")
        return False

    output_path = folder_path / output_file
    fact = _posix(fact_path)
    product = _posix(folder_path / DIMENSION_FILES["product"][0])
    market = _posix(folder_path / DIMENSION_FILES["market"][0])
    period = _posix(folder_path / DIMENSION_FILES["period"][0])
    output = _posix(output_path)

    print(f"\nUniendo archivos en: {folder_path}")

    connection = duckdb.connect()
    try:
        connection.execute(
            f"""
            COPY (
                SELECT
                    d.*,
                    p.* EXCLUDE (product_id),
                    m.* EXCLUDE (market_id),
                    pe.* EXCLUDE (period_id)
                FROM read_csv('{fact}', header = true, delim = '|', auto_detect = true) AS d
                LEFT JOIN read_csv('{product}', header = true, delim = '|', auto_detect = true) AS p
                    USING (product_id)
                LEFT JOIN read_csv('{market}', header = true, delim = '|', auto_detect = true) AS m
                    USING (market_id)
                LEFT JOIN read_csv('{period}', header = true, delim = '|', auto_detect = true) AS pe
                    USING (period_id)
            ) TO '{output}' (HEADER, DELIMITER '|')
            """
        )
    finally:
        connection.close()

    print(f"  [OK] Guardado en: {output_path}")
    return True


def join_categories(
    base_path: Path,
    categories: list[str],
    output_file: str = DEFAULT_OUTPUT_FILE,
) -> None:
    joined_folders = 0

    for categoria in categories:
        categoria_path = base_path / categoria

        if not categoria_path.exists():
            print(f"\nNo existe la carpeta: {categoria_path}")
            continue

        print(f"\n{'=' * 50}")
        print(f"CATEGORIA: {categoria}")
        print(f"{'=' * 50}")

        for folder in sorted(categoria_path.iterdir()):
            if folder.is_dir() and join_folder(folder, output_file):
                joined_folders += 1

    print(f"\nUnion terminada. Carpetas procesadas: {joined_folders}")
