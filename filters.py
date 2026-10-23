from typing import List, Dict, Any, Optional

def filter_ipo_data(
    records: List[Dict[str, Any]],
    category: Optional[str] = "all",
    min_total: Optional[float] = None,
    max_total: Optional[float] = None,
    min_rii: Optional[float] = None,
    min_qib: Optional[float] = None,
    min_nii: Optional[float] = None,
    min_gmp_pct: Optional[float] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Filter the scraped IPO subscription records based on customizable criteria.
    """
    filtered = []

    for r in records:
        # Category filter: 'mainboard' (or 'ipo'), 'sme', 'all'
        if category and category.lower() != "all":
            cat_lower = category.lower()
            if cat_lower in ["mainboard", "ipo"]:
                if r.get("is_sme"):
                    continue
            elif cat_lower == "sme":
                if not r.get("is_sme"):
                    continue

        # Total subscription filter
        total = r.get("total")
        if min_total is not None:
            if total is None or total < min_total:
                continue
        if max_total is not None:
            if total is not None and total > max_total:
                continue

        # Retail (RII) subscription filter
        if min_rii is not None:
            rii = r.get("rii")
            if rii is None or rii < min_rii:
                continue

        # QIB subscription filter
        if min_qib is not None:
            qib = r.get("qib")
            if qib is None or qib < min_qib:
                continue

        # NII subscription filter
        if min_nii is not None:
            nii = r.get("nii")
            if nii is None or nii < min_nii:
                continue

        # GMP percentage filter
        if min_gmp_pct is not None:
            gmp_pct = r.get("gmp_pct")
            if gmp_pct is None or gmp_pct < min_gmp_pct:
                continue

        # Status filter (e.g. 'CT' for closing today)
        if status:
            if r.get("status", "").upper() != status.upper():
                continue

        # Search term filter
        if search:
            q = search.lower()
            name_match = q in r.get("name", "").lower()
            cat_match = q in r.get("category", "").lower()
            if not (name_match or cat_match):
                continue

        filtered.append(r)

    return filtered


def project_columns(
    records: List[Dict[str, Any]],
    columns: List[str]
) -> List[Dict[str, Any]]:
    """
    Select only specific requested columns from records.
    Always preserves 'link' if present for reference/clickable links.
    """
    projected = []
    col_set = set(c.strip().lower() for c in columns)

    for r in records:
        row = {}
        for col in columns:
            col_key = col.strip().lower()
            # Map friendly aliases if any
            alias_map = {
                "retail": "rii",
                "hni": "nii",
                "date": "closing_date",
                "closes": "closing_date",
                "rii_lot": "rii_lot_size",
                "shni_lot": "shni_lot_size",
                "retail_lot": "rii_lot_size",
                "hni_lot": "shni_lot_size",
            }
            actual_key = alias_map.get(col_key, col_key)


            # Check if there is a formatted string representation
            str_key = f"{actual_key}_str"
            if str_key in r:
                row[col_key] = r[str_key]
            else:
                row[col_key] = r.get(actual_key, "-")

        if "link" in r and "link" not in row:
            row["_link"] = r["link"]
        projected.append(row)

    return projected
