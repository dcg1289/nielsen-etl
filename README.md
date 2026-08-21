# Nielsen ETL

Monthly Nielsen ZIP-to-SQL pipeline for FMCG revenue analytics.

Extracted from [`fmcg-revenue-platform`](https://github.com/codestorms37/fmcg-revenue-platform) (`data_ingest/nielsen_etl`).

## Layout

```text
nielsen_etl/
├── config/          # SQL + pipeline config (non-secret)
├── incoming/        # Raw Nielsen ZIP drops
├── processing/      # In-flight work
├── archive/         # Processed ZIPs
├── error/           # Quarantined failures
├── extracted/       # Unpacked source files
├── src/
│   ├── ingestion/
│   ├── validation/
│   ├── transformation/
│   ├── loaders/
│   └── audit/
├── logs/
├── tests/
├── main.py          # CLI entry point
└── settings.yaml    # Path + SQL defaults (override locally; never commit secrets)
```

## Quick start

```powershell
python main.py
```

Configure `settings.yaml` (or a local override) with SQL server/database before running loaders.

## Development

```powershell
python -m pytest tests/
```

Runtime folders (`incoming/`, `logs/`, etc.) are gitignored except `.gitkeep` placeholders.

## Related platform docs

- Nielsen integration brief: `fmcg-revenue-platform` → `docs/runbooks/nielsen_rgm_integration.md`
- Forecast methodology: `docs/runbooks/nielsen_forecast_methodology.md`
