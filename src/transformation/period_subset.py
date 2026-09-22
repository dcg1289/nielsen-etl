"""Subset joined Nielsen files by the latest available year and month."""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

DEFAULT_INPUT_FILE = "joined.txt"
PERIOD_DATE_COLUMN = "period_ending_datetime"
SUBSET_FILE_PATTERN = re.compile(r"^joined_(\d{4})_(\d{2})\.txt$")


def _posix(path: Path) -> str:
    return path.as_posix()


def subset_output_file(year: int, month: int) -> str:
    return f"joined_{year}_{month:02d}.txt"


def catalog_output_file(year: int, month: int) -> str:
    return f"{subset_output_file(year, month).removesuffix('.txt')}_catalog.txt"


def detect_latest_period(connection: duckdb.DuckDBPyConnection, source: str) -> tuple[int, int]:
    row = connection.execute(
        f"""
        SELECT
            EXTRACT(YEAR FROM MAX(TRY_CAST({PERIOD_DATE_COLUMN} AS DATE)))::INTEGER,
            EXTRACT(MONTH FROM MAX(TRY_CAST({PERIOD_DATE_COLUMN} AS DATE)))::INTEGER
        FROM read_csv('{source}', header = true, delim = '|', auto_detect = true)
        WHERE TRY_CAST({PERIOD_DATE_COLUMN} AS DATE) IS NOT NULL
        """
    ).fetchone()

    if not row or row[0] is None or row[1] is None:
        raise ValueError(f"No se pudo detectar el ultimo periodo en {source}")

    return int(row[0]), int(row[1])


def find_latest_subset_file(folder_path: Path) -> Path | None:
    candidates: list[tuple[int, int, Path]] = []

    for path in folder_path.glob("joined_*.txt"):
        if "_catalog" in path.name:
            continue

        match = SUBSET_FILE_PATTERN.match(path.name)
        if not match:
            continue

        year, month = int(match.group(1)), int(match.group(2))
        candidates.append((year, month, path))

    if not candidates:
        return None

    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def subset_folder(
    folder_path: Path,
    input_file: str = DEFAULT_INPUT_FILE,
    output_file: str | None = None,
    year: int | None = None,
    month: int | None = None,
) -> tuple[int, int] | None:
    input_path = folder_path / input_file

    if not input_path.exists():
        print(f"  [SKIP] No existe {input_file} en {folder_path}")
        return None

    source = _posix(input_path)

    print(f"\nFiltrando: {folder_path}")

    connection = duckdb.connect()
    try:
        if year is None or month is None:
            year, month = detect_latest_period(connection, source)

        resolved_output_file = output_file or subset_output_file(year, month)
        output_path = folder_path / resolved_output_file
        output = _posix(output_path)

        print(f"  Periodo seleccionado: {year}-{month:02d}")

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
    output_file: str | None = None,
    year: int | None = None,
    month: int | None = None,
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
