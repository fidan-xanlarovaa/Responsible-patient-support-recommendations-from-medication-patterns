"""
edw_helpers.py
================
Shared setup + helper functions for the P2U Leeds Interns EDW blob export.
Import this from any notebook instead of copy-pasting Sections 1-2 of
Interns_EDW_Tables_Navigation_FINAL.ipynb every time.

Usage (in any notebook, any folder):

    from edw_helpers import authenticate, load_table_smart, mem_check, \
        read_first_parquet, table_inventory, list_parts, FOLDERS, TIER_A

    authenticate()   # <- run this once per kernel session; prints the
                     #    device-code login URL, same as before

    df = load_table_smart("Dim_Customer", columns=["CustomerKey", "gender"])

Note: authenticate() must still be called explicitly in every new kernel —
a device-code login is an interactive step and can't happen silently at
import time. Everything else (constants, load_table_smart, mem_check, etc.)
is available immediately on import.
"""

import io
import re
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.dataset as ds
import psutil

from azure.identity import DeviceCodeCredential
from azure.ai.ml import MLClient
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import HttpResponseError
import adlfs

pd.set_option("display.max_columns", 200)
pd.set_option("display.width", 200)

# ---------------------------------------------------------------------------
# 1.5 — Auth constants (unchanged from the navigation notebook)
# ---------------------------------------------------------------------------
TENANT_ID = "43e95248-7ed6-4937-90a9-2940c888a25f"   # Pharmacy2U Entra
SUBSCRIPTION_ID = "e3f80064-70e1-47b8-a1ea-fe9938349b16"  # P2U-SDLC
RESOURCE_GROUP = "SMRT-TEMP-RG"
WORKSPACE_NAME = "SMRT-TEMP-AML00"
DATASTORE_NAME = "workspaceblobstore"

# Module-level state, populated by authenticate(). None until you call it.
credential = None
ml_client = None
datastore = None
blob_service = None
container = None
fs = None

# ---------------------------------------------------------------------------
# 2.1 — Constants: table registry
# ---------------------------------------------------------------------------
BASE_PATH = "landing/p2u_leeds_interns/20260618"

FOLDERS = {
    # ---- 13 reference / dimension / smaller-fact tables ----
    "Dim.BNFHierarchy": "Dim_BNFHierarchy",
    "Dim.Date": "Dim_Date",
    "Dim.FDBDMDProduct": "Dim_FDBDMDProduct",
    "Dim.Postcode": "Dim_Postcode",
    "Dim.Product": "Dim_Product",
    "Fact.BNFSnomedConvert": "Fact_BNFSnomedConvert",
    "Fact.CustomerDeregistration": "Fact_CustomerDeregistration",
    "Fact.RepeatItems": "Fact_RepeatItems",
    "Report.NHS_Performance_IMD2025EnglandLSOA": "Report_NHS_Performance_IMD2025EnglandLSOA",
    "Report.NHS_Performance_PostcodesToLSOA2022": "Report_NHS_Performance_PostcodesToLSOA2022",
    "Fact.CustomerNomination": "Fact_CustomerNomination",
    "Fact.CustomerNominationStatus": "Fact_CustomerNominationStatus",
    "Fact.Despatch": "Fact_Despatch",
    # ---- 5 big EDW tables, all landed 2026-06-30 ----
    "Dim.Customer": "Dim_Customer",
    "Dim.Order": "Dim_Order",
    "Dim.Prescription": "Dim_Prescription",
    "Dim.PrescriptionItem": "Dim_PrescriptionItem",
    "Dim.DispenseItem": "Dim_DispenseItem",
}

# Tier-A = big tables that REFUSE to be read without a filter/cap.
TIER_A = {
    "Fact_Despatch",
    "Dim_Prescription",
    "Dim_PrescriptionItem",
    "Dim_DispenseItem",
    "Dim_Order",
}


# ---------------------------------------------------------------------------
# 1.5 — Auth + datastore + blob container + adlfs filesystem
# ---------------------------------------------------------------------------
def authenticate():
    """
    Run this once per kernel session. Prints a device-code login URL —
    open it in a browser tab, sign in with your @pharmacy2u.co.uk account.
    Populates the module-level `container` and `fs` objects that every
    other function in this module relies on.
    """
    global credential, ml_client, datastore, blob_service, container, fs

    credential = DeviceCodeCredential(tenant_id=TENANT_ID)
    print("Stage A  DeviceCodeCredential created")

    ml_client = MLClient(credential, SUBSCRIPTION_ID, RESOURCE_GROUP, WORKSPACE_NAME)
    datastore = ml_client.datastores.get(DATASTORE_NAME)
    print("Stage B  datastore resolved")
    print(f"         account_name   = {datastore.account_name}")
    print(f"         container_name = {datastore.container_name}")

    blob_service = BlobServiceClient(
        account_url=f"https://{datastore.account_name}.blob.core.windows.net",
        credential=credential,
    )
    container = blob_service.get_container_client(datastore.container_name)

    fs = adlfs.AzureBlobFileSystem(
        account_name=datastore.account_name,
        credential=credential,
    )
    print("Stage C  BlobServiceClient + adlfs filesystem ready")
    return container, fs


def _check_authenticated():
    if container is None or fs is None:
        raise RuntimeError(
            "Not authenticated yet. Call authenticate() first "
            "(once per kernel session) — it prints a device-code login URL."
        )


# ---------------------------------------------------------------------------
# 2.2 — helper: list parquet parts under <BASE>/<folder>
# ---------------------------------------------------------------------------
def list_parts(folder: str) -> list:
    """Return sorted list of parquet blob names under a table folder."""
    _check_authenticated()
    prefix = f"{BASE_PATH}/{folder}/"
    parts = sorted(
        b.name for b in container.list_blobs(name_starts_with=prefix)
        if b.name.endswith(".parquet")
    )
    return parts


# ---------------------------------------------------------------------------
# 2.3 — helper: read first N rows from the first parquet part
# ---------------------------------------------------------------------------
def read_first_parquet(folder: str, n_rows: int = 5, columns: list = None) -> pd.DataFrame:
    """
    Reads N rows from part-00000 only. Cheap. Use for schema discovery + sampling.
    Always pass `columns=` for wide tables to keep the read small.
    """
    _check_authenticated()
    parts = list_parts(folder)
    if not parts:
        raise FileNotFoundError(f"No parquet parts under {BASE_PATH}/{folder}/")
    blob_name = parts[0]
    bc = container.get_blob_client(blob_name)
    data = bc.download_blob(max_concurrency=1).readall()
    buf = pa.BufferReader(data)
    pf = pq.ParquetFile(buf)
    tbl = pf.read_row_group(0, columns=columns) if pf.num_row_groups > 0 else pf.read(columns=columns)
    df = tbl.to_pandas()
    return df.head(n_rows)


# ---------------------------------------------------------------------------
# 2.4 — helper: inventory of all available tables (parts + total bytes)
# ---------------------------------------------------------------------------
def table_inventory() -> pd.DataFrame:
    _check_authenticated()
    rows = []
    for fqn, folder in FOLDERS.items():
        prefix = f"{BASE_PATH}/{folder}/"
        parts, total_bytes = 0, 0
        for b in container.list_blobs(name_starts_with=prefix):
            if b.name.endswith(".parquet"):
                parts += 1
                total_bytes += (b.size or 0)
        rows.append({
            "fqn": fqn,
            "folder": folder,
            "n_parts": parts,
            "total_MB": round(total_bytes / 1e6, 2),
            "tier_A": folder in TIER_A,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 2.5 — load_table_smart — the one you should default to.
# ---------------------------------------------------------------------------
def load_table_smart(
    folder: str,
    columns: list,                   # REQUIRED
    customer_keys=None,              # iterable of CustomerKey ints
    date_range: tuple = None,        # (start_str, end_str)
    date_column: str = None,         # column to apply date_range to
    n_rows: int = None,              # caps result via slice
    return_pandas: bool = True,
):
    _check_authenticated()
    assert columns, (
        "load_table_smart requires explicit `columns=` list. "
        "Whole-table reads OOM the kernel on wide / Tier-A tables."
    )
    if folder in TIER_A:
        assert customer_keys is not None or date_range is not None or n_rows is not None, (
            f"{folder} is Tier-A — must pass customer_keys, date_range, or n_rows."
        )

    dataset = ds.dataset(
        f"{container.container_name}/{BASE_PATH}/{folder}/",
        filesystem=fs, format="parquet",
    )

    filt = None
    if date_range is not None and date_column is not None:
        start, end = date_range
        filt = (ds.field(date_column) >= pd.Timestamp(start)) & \
               (ds.field(date_column) <= pd.Timestamp(end))
    if customer_keys is not None:
        ck_filt = ds.field("CustomerKey").isin(list(customer_keys))
        filt = ck_filt if filt is None else (filt & ck_filt)

    tbl = dataset.to_table(columns=columns, filter=filt)
    if n_rows is not None:
        tbl = tbl.slice(0, n_rows)
    return tbl.to_pandas() if return_pandas else tbl


def mem_check(estimated_bytes: int, label: str = "") -> None:
    """Refuses if planned read > 70% of available RAM. Call BEFORE the read."""
    available = psutil.virtual_memory().available
    pct = (estimated_bytes / available) * 100
    print(f"[mem_check {label}] planned ~{estimated_bytes/1e9:.2f} GB / "
          f"available {available/1e9:.2f} GB  ({pct:.1f}%)")
    if estimated_bytes > 0.7 * available:
        raise MemoryError(
            f"Planned read ~{estimated_bytes/1e9:.2f} GB exceeds 70% of available "
            f"({available/1e9:.2f} GB). Add column pruning, date filter, or "
            f"customer-key filter before retrying."
        )
