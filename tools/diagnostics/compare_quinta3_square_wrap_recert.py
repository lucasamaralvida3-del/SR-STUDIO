from __future__ import annotations

import argparse
import json
from pathlib import Path

ROLES = ("name", "currency", "integer", "decimal", "unit")
PROFILES = ("costela", "pernil", "musculo", "moela")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def current_rows(root: Path) -> list[dict]:
    rows = load_json(root / "text-variant-metrics.json")
    return [row for row in rows if row.get("VARIANT") == "current"]


def role_map(rows: list[dict]) -> dict[tuple[str, str], dict]:
    return {(str(row["PROFILE"]), str(row["ROLE"])): row for row in rows}


def aggregate(summary: dict, roles: tuple[str, ...], field: str) -> float:
    current = summary["VARIANTS"]["current"]
    key = "ROLE_MAE" if field == "MAE" else "ROLE_CHANGED_RATIO"
    values = [float(current[key][role]) for role in roles]
    return sum(values) / len(values)


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

    before_summary = load_json(before / "text-semantics-summary.json")
    after_summary = load_json(after / "text-semantics-summary.json")
    before_rows = role_map(current_rows(before))
    after_rows = role_map(current_rows(after))

    if before_summary["SOURCE_SHA"] != args.before_sha:
        raise RuntimeError(f"BEFORE source mismatch: {before_summary['SOURCE_SHA']}")
    if after_summary["SOURCE_SHA"] != args.after_sha:
        raise RuntimeError(f"AFTER source mismatch: {after_summary['SOURCE_SHA']}")
    if before_summary["PPTX_SHA256"] != after_summary["PPTX_SHA256"]:
        raise RuntimeError("PPTX SHA mismatch between BEFORE and AFTER")

    line_counts: dict[str, dict[str, int]] = {"currency": {}, "decimal": {}}
    for role in ("currency", "decimal"):
        for profile in PROFILES:
            count = int(after_rows[(profile, role)]["LINE_COUNT"])
            line_counts[role][profile] = count
            if count <= 1:
                raise RuntimeError(f"{profile}/{role}: expected multiline AFTER, got {count}")

    before_currency_decimal_mae = aggregate(before_summary, ("currency", "decimal"), "MAE")
    after_currency_decimal_mae = aggregate(after_summary, ("currency", "decimal"), "MAE")
    before_currency_decimal_changed = aggregate(
        before_summary, ("currency", "decimal"), "CHANGED_RATIO"
    )
    after_currency_decimal_changed = aggregate(
        after_summary, ("currency", "decimal"), "CHANGED_RATIO"
    )

    if not after_currency_decimal_mae < before_currency_decimal_mae:
        raise RuntimeError(
            f"aggregate CURRENCY+DECIMAL MAE did not improve: "
            f"{before_currency_decimal_mae} -> {after_currency_decimal_mae}"
        )
    if not after_currency_decimal_changed < before_currency_decimal_changed:
        raise RuntimeError(
            f"aggregate CURRENCY+DECIMAL changed_ratio did not improve: "
            f"{before_currency_decimal_changed} -> {after_currency_decimal_changed}"
        )

    role_results = {}
    for role in ROLES:
        before_mae = float(before_summary["VARIANTS"]["current"]["ROLE_MAE"][role])
        after_mae = float(after_summary["VARIANTS"]["current"]["ROLE_MAE"][role])
        before_changed = float(
            before_summary["VARIANTS"]["current"]["ROLE_CHANGED_RATIO"][role]
        )
        after_changed = float(
            after_summary["VARIANTS"]["current"]["ROLE_CHANGED_RATIO"][role]
        )
        role_results[role] = {
            "BEFORE_MAE": before_mae,
            "AFTER_MAE": after_mae,
            "MAE_DELTA": after_mae - before_mae,
            "BEFORE_CHANGED_RATIO": before_changed,
            "AFTER_CHANGED_RATIO": after_changed,
            "CHANGED_RATIO_DELTA": after_changed - before_changed,
        }

    for role in ("integer", "unit"):
        result = role_results[role]
        if result["AFTER_MAE"] > result["BEFORE_MAE"] + 1e-9:
            raise RuntimeError(f"{role.upper()} MAE regression: {result}")
        if result["AFTER_CHANGED_RATIO"] > result["BEFORE_CHANGED_RATIO"] + 1e-12:
            raise RuntimeError(f"{role.upper()} changed_ratio regression: {result}")

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
                    "BEFORE_CHANGED_RATIO": float(b["CHANGED_RATIO"]),
                    "AFTER_CHANGED_RATIO": float(a["CHANGED_RATIO"]),
                    "BEFORE_LINE_COUNT": int(b["LINE_COUNT"]),
                    "AFTER_LINE_COUNT": int(a["LINE_COUNT"]),
                    "AFTER_RENDERED_BBOX": a.get("RENDERED_BBOX"),
                    "AFTER_RENDERED_WIDTH": a.get("RENDERED_WIDTH"),
                    "AFTER_RENDERED_HEIGHT": a.get("RENDERED_HEIGHT"),
                    "AFTER_BASELINES": a.get("BASELINE_POSITIONS_LOCAL"),
                }
            )

    result = {
        "BEFORE_SOURCE_SHA": args.before_sha,
        "AFTER_SOURCE_SHA": args.after_sha,
        "PPTX_SHA256": after_summary["PPTX_SHA256"],
        "ANTON_EXACT_MATCH_AFTER": bool(after_summary.get("ANTON_EXACT_MATCH")),
        "CURRENCY_DECIMAL_AGGREGATE": {
            "BEFORE_MAE": before_currency_decimal_mae,
            "AFTER_MAE": after_currency_decimal_mae,
            "BEFORE_CHANGED_RATIO": before_currency_decimal_changed,
            "AFTER_CHANGED_RATIO": after_currency_decimal_changed,
            "MAE_IMPROVED": after_currency_decimal_mae < before_currency_decimal_mae,
            "CHANGED_RATIO_IMPROVED": after_currency_decimal_changed
            < before_currency_decimal_changed,
        },
        "ROLE_RESULTS": role_results,
        "AFTER_LINE_COUNTS": line_counts,
        "INTEGER_REGRESSION": False,
        "UNIT_REGRESSION": False,
        "PER_NODE": per_node,
    }
    if not result["ANTON_EXACT_MATCH_AFTER"]:
        raise RuntimeError("Anton exactMatch failed AFTER")

    (out / "square-wrap-recert-summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result["CURRENCY_DECIMAL_AGGREGATE"], indent=2))
    print("INTEGER_REGRESSION=FALSE")
    print("UNIT_REGRESSION=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
