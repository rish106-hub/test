"""Source manifest and source log writers (R002): append-only, stable IDs.

`SourceBook` loads data/source_manifest.csv and data/canonical/source_log.csv, hands out DOC-nnnnnn /
SRC-nnnnnn ids, and is idempotent: registering the same document (same local path or URL and same
SHA256) or the same logged value again returns the existing id. A changed file gets a new row.
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from src.common.schema import SOURCE_LOG, SOURCE_MANIFEST

ROOT = Path(__file__).resolve().parents[2]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})


class SourceBook:
    MANIFEST = ROOT / SOURCE_MANIFEST.csv_path
    LOG = ROOT / SOURCE_LOG.csv_path

    def __init__(self):
        self.docs = read_csv(self.MANIFEST)
        self.log_rows = read_csv(self.LOG)

    # ------------------------------------------------------------------ manifest
    def add_doc(self, *, entity: str, name: str, doc_type: str, tier: str, url: str = "", local_path: str = "",
                sha256: str = "", pub_date: str = "", period: str = "", retrieved: str, note: str = "") -> str:
        """Register a document. If `local_path` exists under the repo its SHA256 is computed here."""
        if local_path and (ROOT / local_path).exists():
            sha256 = sha256_of(ROOT / local_path)
        for d in self.docs:
            same_place = (d["Local_Path"] == local_path and local_path) or (not local_path and d["URL"] == url)
            if same_place and d["SHA256"] == sha256 and d["Document_Name"] == name:
                return d["Source_Doc_ID"]
        doc_id = f"DOC-{len(self.docs) + 1:06d}"
        self.docs.append({
            "Source_Doc_ID": doc_id, "Entity_or_Fund_ID": entity, "Document_Name": name, "Document_Type": doc_type,
            "Source_Tier": tier, "URL": url, "Local_Path": local_path, "SHA256": sha256, "Publication_Date": pub_date,
            "Period_Covered": period, "Retrieval_Date": retrieved, "Access_or_Licence_Note": note,
        })
        return doc_id

    def doc(self, doc_id: str) -> dict:
        return next(d for d in self.docs if d["Source_Doc_ID"] == doc_id)

    # ------------------------------------------------------------------ log
    def add_log(self, *, doc_id: str, entity: str, metric: str, reported_value: str, unit: str, period: str = "",
                obs_date: str = "", page: str, dest: str, status: str, retrieved: str | None = None) -> str:
        d = self.doc(doc_id)
        key = (doc_id, entity, metric, period, obs_date, reported_value, page, dest)
        for r in self.log_rows:
            if (r["Source_Doc_ID"], r["Entity_ID"], r["Metric"], r["Reporting_Period"], r["Observation_Date"],
                    r["Reported_Value"], r["Page_or_Table"], r["Destination_Table"]) == key:
                return r["Source_ID"]
        sid = f"SRC-{len(self.log_rows) + 1:06d}"
        self.log_rows.append({
            "Source_ID": sid, "Source_Doc_ID": doc_id, "Entity_ID": entity, "Metric": metric,
            "Reported_Value": reported_value, "Unit": unit, "Reporting_Period": period, "Observation_Date": obs_date,
            "Document_Name": d["Document_Name"], "URL_or_File_Path": d["Local_Path"] or d["URL"],
            "Page_or_Table": page, "Retrieval_Date": retrieved or d["Retrieval_Date"], "Source_Type": d["Source_Tier"],
            "Destination_Table": dest, "Data_Quality_Status": status,
        })
        return sid

    def save(self) -> None:
        write_csv(self.MANIFEST, [c.name for c in SOURCE_MANIFEST.stored_columns], self.docs)
        write_csv(self.LOG, [c.name for c in SOURCE_LOG.stored_columns], self.log_rows)
