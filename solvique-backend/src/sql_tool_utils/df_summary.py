import json
import numpy as np
import pandas as pd


def _to_records(df: pd.DataFrame) -> list[dict]:
    return json.loads(
        df.replace({np.nan: None}).to_json(orient="records", date_format="iso")
    )


def build_result_eda_text(df: pd.DataFrame, sample_rows: int = 5) -> str:
    try:
        describe_df = (
            df.describe(include="all", datetime_is_numeric=True)
            .transpose()
            .reset_index(names="column")
        )
        descriptive_stats = _to_records(describe_df)
    except Exception:
        descriptive_stats = []

    payload = {
        "row_count": int(df.shape[0]),
        "column_count": int(df.shape[1]),
        "columns": list(df.columns),
        "dtypes": {k: str(v) for k, v in df.dtypes.to_dict().items()},
        "null_counts": {
            k: int(v) for k, v in df.isna().sum().to_dict().items() if int(v) > 0
        },
        "sample_rows": _to_records(df.head(sample_rows)),
        "descriptive_statistics": descriptive_stats,
    }

    return json.dumps(payload, ensure_ascii=False, default=str, indent=2)
