"""Join subset data with custom SQL catalogs."""

from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path

import duckdb

DEFAULT_INPUT_FILE = "joined_2026_07.txt"
DEFAULT_OUTPUT_FILE = "joined_2026_07_catalog.txt"
DEFAULT_HIERARCHY_LEVEL_NAMES = ("SEGMENTO I", "PRESENTACION REGULAR")
SEGMENTO_I_LEVEL = "SEGMENTO I"
CONTROLLED_LABEL_CORP = "CONTROLLED LABEL"
CONTROLLED_LABEL_CORP_COLUMN = "CSTM_948001"
SEGMENTO_I_COLUMN = "CSTM_940105"
JUGOS_CATEGORIES = frozenset({"JUGOS_RT", "JUGOS_ST"})
ST_UPC_CATEGORIES = frozenset({"CSD_ST", "JUGOS_ST"})
ST_UPC_LEVEL = "UPC"
JUGOS_PESO_LEVEL = "PESO CONVERTIDO"
JUGOS_FABRICANTE_LEVEL = "FABRICANTE UNIF.I"
JUGOS_CONTROLLED_LABEL_CORP_COLUMN = "CSTM_309849"
DOL_POSITIVE_FILTER = "try_cast(DOL AS DOUBLE) > 0"
CATALOG_COLUMNS = ("ID_PRODUCT", "ID_P", "ID_MARKET")

CONTROLLED_LABEL_PRODUCT_MAP: tuple[dict[str, str], ...] = (
    {
        "CSTM_948001": CONTROLLED_LABEL_CORP,
        "CSTM_940105": "COLAS GENERICAS",
        "ID_PRODUCT": "P10002",
    },
    {
        "CSTM_948001": CONTROLLED_LABEL_CORP,
        "CSTM_940105": "OTHERS",
        "ID_PRODUCT": "P10004",
    },
    {
        "CSTM_948001": CONTROLLED_LABEL_CORP,
        "CSTM_940105": "SABORES GENERICAS",
        "ID_PRODUCT": "P10003",
    },
    {
        "CSTM_948001": CONTROLLED_LABEL_CORP,
        "CSTM_940105": "AGUA MIN. GENERICAS",
        "ID_PRODUCT": "P10001",
    },
)

HIERARCHY_ROLE_RULES: tuple[tuple[str, Callable[[str], bool]], ...] = (
    ("prod_corporativo", lambda name: "FABRICANTE" in name or "CORPORATIVO" in name),
    ("segmento", lambda name: "SEGMENTO UNIF" in name),
    ("marca", lambda name: "MARCA" in name and "SEGMENTO" not in name),
    ("l_e", lambda name: name == "CONTENIDO" or ("CONTENIDO" in name and "CALORICO" not in name)),
    ("sabor", lambda name: "SABOR" in name),
    ("calorico", lambda name: "CALORICO" in name),
    ("presentacion", lambda name: "PRESENTACION" in name),
)

RT_PERIOD_JOIN = """
    LEFT JOIN read_csv('{periods}', header = true, encoding = 'latin-1') AS periods
        ON extract(year FROM cast(d.period_ending_datetime AS DATE)) = periods.YEAR
       AND extract(month FROM cast(d.period_ending_datetime AS DATE)) = periods.MONTH
"""

ST_PERIOD_JOIN = """
    LEFT JOIN read_csv('{periods}', header = true, encoding = 'latin-1') AS periods
        ON d.period_id - {period_offset} = periods.ID_P
"""

MARKET_JOIN = """
    LEFT JOIN read_csv('{markets}', header = true, encoding = 'latin-1') AS markets
        ON trim(d.MRKT_DSC_SHRT) = trim(markets.MKT_LDESC_2)
"""

ST_PRODUCT_JOIN = """
    LEFT JOIN read_csv('{products}', header = true, encoding = 'latin-1') AS products
        ON d.product_id = products.ID_PRODUCT
"""


def _posix(path: Path) -> str:
    return path.as_posix()


def _catalog_files(catalog_path: Path, is_st: bool) -> tuple[Path, Path, Path]:
    if is_st:
        return (
            catalog_path / "PRODUCTS_ST.csv",
            catalog_path / "PERIODS_ST.csv",
            catalog_path / "MARKETS.csv",
        )
    return (
        catalog_path / "PRODUCTS.csv",
        catalog_path / "PERIODS.csv",
        catalog_path / "MARKETS.csv",
    )


def _resolve_rt_product_columns(folder_path: Path) -> dict[str, str]:
    hierar_path = folder_path / "hierar.txt"
    if not hierar_path.exists():
        raise FileNotFoundError(f"No existe hierar.txt en {folder_path}")

    columns: dict[str, str] = {}
    with hierar_path.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="|")
        for row in reader:
            level_name = row["hierarchy_level_name"].upper()
            column_name = row["column_name"]

            for role, matcher in HIERARCHY_ROLE_RULES:
                if role in columns:
                    continue
                if matcher(level_name):
                    columns[role] = column_name

    required = ("prod_corporativo", "segmento", "marca")
    missing = [role for role in required if role not in columns]
    if missing:
        raise ValueError(
            f"No se pudieron resolver columnas RT {missing} en {folder_path / 'hierar.txt'}"
        )
    return columns


def _build_rt_product_sql(folder_path: Path, products: str) -> tuple[str, str]:
    columns = _resolve_rt_product_columns(folder_path)
    prod_corporativo = columns["prod_corporativo"]
    segmento = columns["segmento"]
    marca = columns["marca"]
    l_e = columns.get("l_e")
    sabor = columns.get("sabor")
    calorico = columns.get("calorico")
    presentacion = columns.get("presentacion")

    join_conditions = [
        f"d.{prod_corporativo} = p.PROD_CORPORATIVO",
        f"d.{segmento} = p.SEGMENTO",
        f"d.{marca} = p.MARCA",
    ]
    group_columns = [
        "d.product_id",
        f"d.{prod_corporativo}",
        f"d.{segmento}",
        f"d.{marca}",
    ]
    product_join_keys = [
        "d.product_id = products.product_id",
        f"d.{prod_corporativo} = products.prod_corporativo",
        f"d.{segmento} = products.segmento",
        f"d.{marca} = products.marca",
    ]

    if l_e:
        join_conditions.append(f"d.{l_e} = p.L_E")
        group_columns.append(f"d.{l_e}")
        product_join_keys.append(f"d.{l_e} = products.l_e")

    if sabor:
        join_conditions.append(
            f"coalesce(d.{sabor}, CASE WHEN d.{segmento} = 'COLAS' THEN 'COLA' END) = p.SABOR"
        )
    if calorico:
        join_conditions.append(
            f"(d.{calorico} IS NULL OR d.{calorico} = p.CONTENIDO_CALORICO)"
        )
    if presentacion:
        join_conditions.append(
            f"(d.{presentacion} IS NULL OR d.{presentacion} = p.PROD_PRESENTACION_REGULAR)"
        )

    l_e_select = f"d.{l_e} AS l_e," if l_e else "cast(NULL AS VARCHAR) AS l_e,"

    product_map = f"""
    product_map AS (
        SELECT
            d.product_id,
            d.{prod_corporativo} AS prod_corporativo,
            d.{segmento} AS segmento,
            d.{marca} AS marca,
            {l_e_select}
            min(cast(p.ID_PRODUCT AS VARCHAR)) AS ID_PRODUCT
        FROM source_data AS d
        LEFT JOIN read_csv('{products}', header = true, encoding = 'latin-1') AS p
            ON {" AND ".join(join_conditions)}
        GROUP BY {", ".join(group_columns)}
    )
    """

    product_join = f"""
    LEFT JOIN product_map AS products
        ON {" AND ".join(product_join_keys)}
    """
    return product_map, product_join


def _sql_string_list(values: list[str]) -> str:
    return ", ".join(f"'{value.replace(chr(39), chr(39) * 2)}'" for value in values)


def _sql_literal(value: str) -> str:
    return f"'{value.replace(chr(39), chr(39) * 2)}'"


def _build_hierarchy_where_sql(hierarchy_level_names: list[str]) -> str:
    conditions: list[str] = []

    for level_name in hierarchy_level_names:
        if level_name == SEGMENTO_I_LEVEL:
            conditions.append(
                "("
                f"hierarchy_level_name = {_sql_literal(SEGMENTO_I_LEVEL)} "
                f"AND {CONTROLLED_LABEL_CORP_COLUMN} = {_sql_literal(CONTROLLED_LABEL_CORP)}"
                ")"
            )
        else:
            conditions.append(f"hierarchy_level_name = {_sql_literal(level_name)}")

    return " OR ".join(conditions)


def _is_jugos_category(category: str) -> bool:
    return category.upper() in JUGOS_CATEGORIES


def _is_st_upc_category(category: str) -> bool:
    return category.upper() in ST_UPC_CATEGORIES


def _build_st_upc_hierarchy_where_sql() -> str:
    return f"hierarchy_level_name = {_sql_literal(ST_UPC_LEVEL)}"


def _build_jugos_hierarchy_where_sql() -> str:
    return (
        f"hierarchy_level_name = {_sql_literal(JUGOS_PESO_LEVEL)} "
        f"OR ("
        f"hierarchy_level_name = {_sql_literal(JUGOS_FABRICANTE_LEVEL)} "
        f"AND {JUGOS_CONTROLLED_LABEL_CORP_COLUMN} = {_sql_literal(CONTROLLED_LABEL_CORP)}"
        ")"
    )


def _source_columns(connection: duckdb.DuckDBPyConnection, source: str) -> set[str]:
    columns = connection.execute(
        f"""
        SELECT column_name
        FROM (DESCRIBE SELECT * FROM read_csv('{source}', header = true, delim = '|', auto_detect = true))
        """
    ).fetchall()
    return {column_name for column_name, in columns}


def _has_controlled_label_columns(columns: set[str]) -> bool:
    return (
        CONTROLLED_LABEL_CORP_COLUMN in columns
        and SEGMENTO_I_COLUMN in columns
    )


def _build_controlled_label_cte() -> str:
    rows = ", ".join(
        (
            f"({_sql_literal(row['CSTM_948001'])}, "
            f"{_sql_literal(row['CSTM_940105'])}, "
            f"{_sql_literal(row['ID_PRODUCT'])})"
        )
        for row in CONTROLLED_LABEL_PRODUCT_MAP
    )
    return f"""
    controlled_label_products AS (
        SELECT *
        FROM (VALUES {rows}) AS t(
            {CONTROLLED_LABEL_CORP_COLUMN},
            {SEGMENTO_I_COLUMN},
            ID_PRODUCT
        )
    ),
    """


def catalog_join_folder(
    folder_path: Path,
    catalog_path: Path,
    is_st: bool,
    category: str = "",
    input_file: str = DEFAULT_INPUT_FILE,
    output_file: str = DEFAULT_OUTPUT_FILE,
    period_offset: int = 5800,
    hierarchy_level_names: list[str] | None = None,
) -> tuple[int, int] | None:
    input_path = folder_path / input_file

    if not input_path.exists():
        print(f"  [SKIP] No existe {input_file} en {folder_path}")
        return None

    products_file, periods_file, markets_file = _catalog_files(catalog_path, is_st)
    for catalog_file in (products_file, periods_file, markets_file):
        if not catalog_file.exists():
            print(f"  [SKIP] No existe catalogo: {catalog_file}")
            return None

    output_path = folder_path / output_file
    source = _posix(input_path)
    output = _posix(output_path)
    products = _posix(products_file)
    periods = _posix(periods_file)
    markets = _posix(markets_file)

    if is_st:
        product_cte = ""
        product_join = ST_PRODUCT_JOIN.format(products=products)
        id_product_expr = "coalesce(cast(products.ID_PRODUCT AS VARCHAR), 'NEW')"
    else:
        product_cte, product_join = _build_rt_product_sql(folder_path, products)
        product_cte = product_cte + ","
        id_product_expr = "coalesce(products.ID_PRODUCT, 'NEW')"

    period_join = (
        ST_PERIOD_JOIN.format(periods=periods, period_offset=period_offset)
        if is_st
        else RT_PERIOD_JOIN.format(periods=periods)
    )
    market_join = MARKET_JOIN.format(markets=markets)
    hierarchy_filter = hierarchy_level_names or list(DEFAULT_HIERARCHY_LEVEL_NAMES)
    catalog_id_product_expr = id_product_expr

    connection = duckdb.connect()
    try:
        source_columns = _source_columns(connection, source)
        is_st_upc = _is_st_upc_category(category)
        is_jugos = _is_jugos_category(category) and not is_st_upc

        if is_st_upc:
            hierarchy_where_sql = _build_st_upc_hierarchy_where_sql()
            controlled_label_cte = ""
            controlled_label_join = ""
            final_id_product_expr = catalog_id_product_expr
        elif is_jugos:
            hierarchy_where_sql = _build_jugos_hierarchy_where_sql()
            controlled_label_cte = ""
            controlled_label_join = ""
            final_id_product_expr = catalog_id_product_expr
        elif _has_controlled_label_columns(source_columns):
            hierarchy_where_sql = _build_hierarchy_where_sql(hierarchy_filter)
            controlled_label_cte = _build_controlled_label_cte()
            controlled_label_join = f"""
                LEFT JOIN controlled_label_products
                    ON d.{CONTROLLED_LABEL_CORP_COLUMN} = controlled_label_products.{CONTROLLED_LABEL_CORP_COLUMN}
                   AND d.{SEGMENTO_I_COLUMN} = controlled_label_products.{SEGMENTO_I_COLUMN}
            """
            final_id_product_expr = (
                f"coalesce(controlled_label_products.ID_PRODUCT, {catalog_id_product_expr})"
            )
        else:
            effective_filter = [
                level
                for level in hierarchy_filter
                if level != SEGMENTO_I_LEVEL
            ]
            if not effective_filter:
                print(
                    f"  [SKIP] Sin columnas CONTROLLED LABEL en {folder_path}; "
                    "no aplica filtro SEGMENTO I"
                )
                return None
            hierarchy_where_sql = _build_hierarchy_where_sql(effective_filter)
            controlled_label_cte = ""
            controlled_label_join = ""
            final_id_product_expr = catalog_id_product_expr

        print(f"\nAplicando catalogos en: {folder_path}")
        if is_st_upc:
            print(f"  Filtro: hierarchy_level_name = {ST_UPC_LEVEL}")
        elif is_jugos:
            print(f"  Filtro 1: hierarchy_level_name = {JUGOS_PESO_LEVEL} (todos los {JUGOS_CONTROLLED_LABEL_CORP_COLUMN})")
            print(
                f"  Filtro 2: hierarchy_level_name = {JUGOS_FABRICANTE_LEVEL} "
                f"AND {JUGOS_CONTROLLED_LABEL_CORP_COLUMN} = {CONTROLLED_LABEL_CORP}"
            )
            print("  Resultado: union de ambos filtros")
        else:
            print(f"  Filtro hierarchy_level_name IN ({', '.join(hierarchy_filter)})")
            if _has_controlled_label_columns(source_columns) and SEGMENTO_I_LEVEL in hierarchy_filter:
                print(
                    f"  SEGMENTO I requiere {CONTROLLED_LABEL_CORP_COLUMN} = "
                    f"{CONTROLLED_LABEL_CORP}"
                )
        print(f"  Filtro DOL > 0")

        connection.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE catalog_joined AS
            WITH source_data AS (
                SELECT *
                FROM read_csv('{source}', header = true, delim = '|', auto_detect = true)
            ),
            {controlled_label_cte}
            {product_cte}
            enriched AS (
                SELECT
                    d.*,
                    {final_id_product_expr} AS ID_PRODUCT,
                    cast(periods.ID_P AS VARCHAR) AS ID_P,
                    markets.ID_MARKET AS ID_MARKET
                FROM source_data AS d
                {market_join}
                {period_join}
                {product_join}
                {controlled_label_join}
            )
            SELECT *
            FROM enriched
            WHERE ({hierarchy_where_sql})
              AND {DOL_POSITIVE_FILTER}
            """
        )

        row_count = connection.execute("SELECT count(*) FROM catalog_joined").fetchone()[0]
        col_count = connection.execute(
            "SELECT count(*) FROM (DESCRIBE catalog_joined)"
        ).fetchone()[0]
        new_products = connection.execute(
            "SELECT count(*) FROM catalog_joined WHERE ID_PRODUCT = 'NEW'"
        ).fetchone()[0]

        connection.execute(
            f"COPY catalog_joined TO '{output}' (HEADER, DELIMITER '|')"
        )
    finally:
        connection.close()

    print(f"  [OK] Guardado en: {output_path}")
    print(f"  [OK] Shape: ({row_count}, {col_count})")
    print(f"  [OK] Productos NEW: {new_products}")
    return row_count, col_count


def catalog_join_categories(
    base_path: Path,
    categories: list[str],
    catalog_path: Path,
    input_file: str = DEFAULT_INPUT_FILE,
    output_file: str = DEFAULT_OUTPUT_FILE,
    period_offset: int = 5800,
    hierarchy_level_names: list[str] | None = None,
) -> None:
    processed_folders = 0

    for categoria in categories:
        categoria_path = base_path / categoria

        if not categoria_path.exists():
            print(f"\nNo existe la carpeta: {categoria_path}")
            continue

        is_st = categoria.upper().endswith("_ST")

        print(f"\n{'=' * 50}")
        print(f"CATEGORIA: {categoria} ({'ST' if is_st else 'RT'})")
        print(f"{'=' * 50}")

        for folder in sorted(categoria_path.iterdir()):
            if folder.is_dir():
                try:
                    result = catalog_join_folder(
                        folder,
                        catalog_path,
                        is_st=is_st,
                        category=categoria,
                        input_file=input_file,
                        output_file=output_file,
                        period_offset=period_offset,
                        hierarchy_level_names=hierarchy_level_names,
                    )
                except (FileNotFoundError, ValueError) as exc:
                    print(f"  [ERROR] {folder}: {exc}")
                    continue
                if result is not None:
                    processed_folders += 1

    print(f"\nCatalogos aplicados. Carpetas procesadas: {processed_folders}")
