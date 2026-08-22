from __future__ import annotations

import argparse
import json
from pathlib import Path

PROFILES = ("costela", "pernil", "musculo", "moela")
ROLES = ("name", "currency", "integer", "decimal", "unit")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def current_rows(root: Path) -> dict[tuple[str, str], dict]:
    rows = load(root / "text-variant-metrics.json")
    return {
        (str(row["PROFILE"]), str(row["ROLE"])): row
        for row in rows
        if row.get("VARIANT") == "current"
    }


def role_result(before_summary: dict, after_summary: dict, role: str) -> dict:
    before = before_summary["VARIANTS"]["current"]
    after = after_summary["VARIANTS"]["current"]
    return {
        "BEFORE_MAE": float(before["ROLE_MAE"][role]),
        "AFTER_MAE": float(after["ROLE_MAE"][role]),
        "MAE_DELTA": float(after["ROLE_MAE"][role]) - float(before["ROLE_MAE"][role]),
        "BEFORE_CHANGED_RATIO": float(before["ROLE_CHANGED_RATIO"][role]),
        "AFTER_CHANGED_RATIO": float(after["ROLE_CHANGED_RATIO"][role]),
        "CHANGED_RATIO_DELTA": float(after["ROLE_CHANGED_RATIO"][role])
        - float(before["ROLE_CHANGED_RATIO"][role]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--before-sha", required=True)
    parser.add_argument("--after-sha", required=True)
    args = parser.parse_args()

    before = args.before.resolve()
    after = args.after.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    before_summary = load(before / "text-semantics-summary.json")
    after_summary = load(after / "text-semantics-summary.json")
    before_rows = current_rows(before)
    after_rows = current_rows(after)
    route = load(after / "wrap-route-trace.json")
    route_rows = {
        (str(row["PROFILE"]), str(row["ROLE"])): row for row in route["NODES"]
    }

    failures: list[str] = []
    if before_summary["SOURCE_SHA"] != args.before_sha:
        failures.append(f"BEFORE source mismatch: {before_summary['SOURCE_SHA']}")
    if after_summary["SOURCE_SHA"] != args.after_sha:
        failures.append(f"AFTER source mismatch: {after_summary['SOURCE_SHA']}")
    if before_summary["PPTX_SHA256"] != after_summary["PPTX_SHA256"]:
        failures.append("PPTX SHA mismatch between BEFORE and AFTER")

    role_results = {role: role_result(before_summary, after_summary, role) for role in ROLES}
    routes: dict[str, dict[str, dict]] = {"currency": {}, "decimal": {}}
    for role in ("currency", "decimal"):
        for profile in PROFILES:
            row = route_rows[(profile, role)]
            routes[role][profile] = {
                "FINAL_LAYOUT_ROUTE": row.get("FINAL_LAYOUT_ROUTE"),
                "WRAPPED_LINE_COUNT": int(row.get("PPTX_WRAPPED_LINE_COUNT") or 0),
                "RASTER_BANDS": int(row.get("RASTER_ACTIVE_ROW_BAND_COUNT") or 0),
                "QTEXTLAYOUT_LINE_COUNT": int(row.get("QTEXTLAYOUT_LINE_COUNT") or 0),
            }
            if row.get("FINAL_LAYOUT_ROUTE") != "pptx_shape_autofit_wrapped":
                failures.append(f"{profile}/{role}: route={row.get('FINAL_LAYOUT_ROUTE')}")
            if int(row.get("PPTX_WRAPPED_LINE_COUNT") or 0) <= 1:
                failures.append(f"{profile}/{role}: wrapped line count <= 1")

    eps = 1e-9
    currency = role_results["currency"]
    if currency["AFTER_MAE"] > currency["BEFORE_MAE"] + eps:
        failures.append(f"CURRENCY MAE regressed: {currency}")
    if currency["AFTER_CHANGED_RATIO"] > currency["BEFORE_CHANGED_RATIO"] + eps:
        failures.append(f"CURRENCY changed_ratio regressed: {currency}")

    decimal = role_results["decimal"]
    if not decimal["AFTER_MAE"] < decimal["BEFORE_MAE"] - eps:
        failures.append(f"DECIMAL MAE did not improve: {decimal}")
    if not decimal["AFTER_CHANGED_RATIO"] < decimal["BEFORE_CHANGED_RATIO"] - eps:
        failures.append(f"DECIMAL changed_ratio did not improve: {decimal}")

    for role in ("integer", "unit", "name"):
        result = role_results[role]
        if result["AFTER_MAE"] > result["BEFORE_MAE"] + eps:
            failures.append(f"{role.upper()} MAE regression: {result}")
        if result["AFTER_CHANGED_RATIO"] > result["BEFORE_CHANGED_RATIO"] + eps:
            failures.append(f"{role.upper()} changed_ratio regression: {result}")

    per_node = []
    for profile in PROFILES:
        for role in ROLES:
            b = before_rows[(profile, role)]
            a = after_rows[(profile, role)]
            per_node.append(
                {
                    "PROFILE": profile,
                    "ROLE": role,
                    "BEFORE_MAE": float(b["MAE"]),
                    "AFTER_MAE": float(a["MAE"]),
                    "MAE_DELTA": float(a["MAE"]) - float(b["MAE"]),
                    "BEFORE_CHANGED_RATIO": float(b["CHANGED_RATIO"]),
                    "AFTER_CHANGED_RATIO": float(a["CHANGED_RATIO"]),
                    "CHANGED_RATIO_DELTA": float(a["CHANGED_RATIO"])
                    - float(b["CHANGED_RATIO"]),
                    "BEFORE_RASTER_LINE_COUNT": int(b.get("LINE_COUNT") or 0),
                    "AFTER_RASTER_LINE_COUNT": int(a.get("LINE_COUNT") or 0),
                    "AFTER_LAYOUT_PATH": a.get("LAYOUT_PATH"),
                }
            )

    result = {
        "BEFORE_SOURCE_SHA": args.before_sha,
        "AFTER_SOURCE_SHA": args.after_sha,
        "PPTX_SHA256": after_summary["PPTX_SHA256"],
        "ANTON_EXACT_MATCH_AFTER": bool(after_summary.get("ANTON_EXACT_MATCH")),
        "ROLE_RESULTS": role_results,
        "ROUTES": routes,
        "PER_NODE": per_node,
        "CURRENCY_ROUTE_REGRESSION": any(
            value["FINAL_LAYOUT_ROUTE"] != "pptx_shape_autofit_wrapped"
            for value in routes["currency"].values()
        ),
        "DECIMAL_4_OF_4_WRAPPED": all(
            value["FINAL_LAYOUT_ROUTE"] == "pptx_shape_autofit_wrapped"
            and value["WRAPPED_LINE_COUNT"] > 1
            for value in routes["decimal"].values()
        ),
        "INTEGER_REGRESSION": any(item.startswith("INTEGER ") for item in failures),
        "UNIT_REGRESSION": any(item.startswith("UNIT ") for item in failures),
        "NAME_REGRESSION": any(item.startswith("NAME ") for item in failures),
        "FAILURES": failures,
        "PASS": not failures,
    }
    if not result["ANTON_EXACT_MATCH_AFTER"]:
        failures.append("Anton exactMatch failed AFTER")
        result["FAILURES"] = failures
        result["PASS"] = False

    (out / "ink-wrap-recert-summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["PASS"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
