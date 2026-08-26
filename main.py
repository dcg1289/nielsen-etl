"""Entry point for Nielsen ETL orchestration."""

from pathlib import Path

from src.ingestion.gz_extractor import extract_categories
from src.settings import load_settings
from src.transformation.catalog_joiner import catalog_join_categories
from src.transformation.period_subset import subset_categories
from src.transformation.txt_joiner import join_categories


def main() -> int:
    settings = load_settings()

    base_path = Path(settings["paths"]["ddm_base"])
    catalog_path = Path(settings["paths"]["catalogs"])
    categories = settings["ingestion"]["categories"]
    join_output = settings["transformation"]["join"]["output_file"]
    subset_settings = settings["transformation"]["subset"]
    catalog_settings = settings["transformation"]["catalog"]

    extract_categories(base_path, categories)
    join_categories(base_path, categories, join_output)
    subset_categories(
        base_path,
        categories,
        input_file=subset_settings["input_file"],
        output_file=subset_settings["output_file"],
        year=subset_settings["year"],
        month=subset_settings["month"],
    )
    catalog_join_categories(
        base_path,
        categories,
        catalog_path,
        input_file=catalog_settings["input_file"],
        output_file=catalog_settings["output_file"],
        period_offset=catalog_settings["st_period_offset"],
        hierarchy_level_names=catalog_settings["hierarchy_level_names"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
