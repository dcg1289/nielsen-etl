"""Subset joined Nielsen files by year and month."""

from __future__ import annotations

from pathlib import Path

import duckdb

DEFAULT_INPUT_FILE = "joined.txt"
DEFAULT_OUTPUT_FILE = "joined_2026_07.txt"
PERIOD_DATE_COLUMN = "period_ending_datetime"


def _posix(path: Path) -> str:
    return path.as_posix()


def subset_folder(
    folder_path: Path,
    input_file: str = DEFAULT_INPUT_FILE,
    output_file: str = DEFAULT_OUTPUT_FILE,
    year: int = 2026,
    month: int = 7,
) -> tuple[int, int] | None:
    input_path = folder_path / input_file

    if not input_path.exists():
        print(f"  [SKIP] No existe {input_file} en {folder_path}")
        return None

    output_path = folder_path / output_file
    source = _posix(input_path)
    output = _posix(output_path)

    print(f"\nFiltrando: {folder_path}")

    connection = duckdb.connect()
    try:
        connection.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE filtered AS
            SELECT *
            FROM read_csv('{source}', header = true, delim = '|', auto_detect = true)
            WHERE EXTRACT(YEAR FROM TRY_CAST({PERIOD_DATE_COLUMN} AS DATE)) = {year}
              AND EXTRACT(MONTH FROM TRY_CAST({PERIOD_DATE_COLUMN} AS DATE)) = {month}
            """
        )

        row_count = connection.execute("SELECT count(*) FROM filtered").fetchone()[0]
        col_count = connection.execute(
            "SELECT count(*) FROM (DESCRIBE filtered)"
        ).fetchone()[0]

        connection.execute(
            f"COPY filtered TO '{output}' (HEADER, DELIMITER '|')"
        )
    finally:
        connection.close()

    print(f"  [OK] Guardado en: {output_path}")
    print(f"  [OK] Shape: ({row_count}, {col_count})")
    return row_count, col_count


def subset_categories(
    base_path: Path,
    categories: list[str],
    input_file: str = DEFAULT_INPUT_FILE,
    output_file: str = DEFAULT_OUTPUT_FILE,
    year: int = 2026,
    month: int = 7,
) -> None:
    processed_folders = 0

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
                result = subset_folder(
                    folder,
                    input_file=input_file,
                    output_file=output_file,
                    year=year,
                    month=month,
                )
                if result is not None:
                    processed_folders += 1

    print(f"\nFiltrado terminado. Carpetas procesadas: {processed_folders}")
