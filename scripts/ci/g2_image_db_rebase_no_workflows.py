from __future__ import annotations

from pathlib import Path
import subprocess

REPO_BRANCH = "g2/integrate-existing-image-db"
CURRENT_BRANCH = "g2/integrate-studio-shell"
CURRENT_BASE = "bfcbde94f3d7750f1bca25e9c3490e76ff28284c"


def run(*args: str, capture: bool = False) -> str:
    completed = subprocess.run(list(args), check=True, text=True, capture_output=capture)
    return completed.stdout.strip() if capture else ""


def show(ref: str, path: str) -> str:
    return run("git", "show", f"{ref}:{path}", capture=True)


def write(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly 1 marker, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    run("git", "fetch", "origin", CURRENT_BRANCH)
    actual_base = run("git", "rev-parse", f"origin/{CURRENT_BRANCH}", capture=True)
    print(f"EXPECTED_CURRENT_BASE={CURRENT_BASE}")
    print(f"ACTUAL_CURRENT_BASE={actual_base}")
    if actual_base != CURRENT_BASE:
        raise RuntimeError("integration head changed; refusing stale Image DB rebase")

    run("git", "config", "user.name", "github-actions[bot]")
    run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    run("git", "merge", "--no-ff", "-s", "ours", CURRENT_BASE, "-m", "chore(g2): join Image DB work with current integration head")
    feature_ref = "HEAD^1"
    current_ref = "HEAD^2"

    for path in [
        "scripts/ci/image_db_build_distribution_seed.py",
        "src/srstudio/graphics2/full_studio_bridge.py",
        "src/srstudio/graphics2/image_database_runtime.py",
        "tests/test_graphics2_existing_image_database.py",
    ]:
        write(path, show(feature_ref, path))

    qml_path = "src/srstudio/graphics2/qml/GraphicsEditor.qml"
    current_qml = show(current_ref, qml_path)
    feature_qml = show(feature_ref, qml_path)
    start = "                                delegate: Rectangle {\n                                    id: productCard\n"
    end = "                                Label { anchors.centerIn: parent; visible: productList.count === 0;"
    for label, source in (("current qml", current_qml), ("feature qml", feature_qml)):
        if source.count(start) != 1 or source.count(end) != 1:
            raise RuntimeError(f"{label}: product delegate markers changed")
    current_block = current_qml[current_qml.index(start):current_qml.index(end)]
    feature_block = feature_qml[feature_qml.index(start):feature_qml.index(end)]
    write(qml_path, replace_once(current_qml, current_block, feature_block, "qml product delegate"))

    host_path = "src/srstudio/graphics2/qt_host.py"
    host = show(current_ref, host_path)
    host = replace_once(
        host,
        "from .fonts import register_qt_document_fonts\nfrom .model import GraphicsDocument\n",
        "from .fonts import register_qt_document_fonts\nfrom .image_database_runtime import GraphicsImageDatabaseRuntime\nfrom .model import GraphicsDocument\n",
        "qt_host import",
    )
    host = replace_once(
        host,
        "    session = GraphicsSession(context.document)\n    router = GraphicsCommandRouter(session)\n    gate = context.gate or inspect_production_gate(session.document, require_visual_fidelity=False)\n",
        "    session = GraphicsSession(context.document)\n    router = GraphicsCommandRouter(session)\n    image_database = GraphicsImageDatabaseRuntime.from_environment()\n    image_database.attach(session, router)\n    gate = context.gate or inspect_production_gate(session.document, require_visual_fidelity=False)\n",
        "qt_host runtime attach",
    )
    host = replace_once(
        host,
        "            payload = inject_preview_image_urls(router.payload(), session.document)\n            editor = payload.setdefault(\"editor\", {})\n",
        "            payload = inject_preview_image_urls(router.payload(), session.document)\n            image_database.augment_payload(payload)\n            editor = payload.setdefault(\"editor\", {})\n            editor[\"image_database\"] = {\n                \"available\": image_database.available,\n                \"status\": image_database.status,\n                \"root\": str(image_database.library_root),\n                \"error\": image_database.error,\n                \"seed_manifest\": dict(image_database.seed_manifest),\n            }\n",
        "qt_host payload augment",
    )
    host = replace_once(
        host,
        "    if bridge._recovery_point is not None:\n        details.append(\"recovery disponível\")\n    bridge.set_status(\" · \".join(details))\n",
        "    if bridge._recovery_point is not None:\n        details.append(\"recovery disponível\")\n    details.append(\"Image DB pronto\" if image_database.available else \"Image DB indisponível\")\n    bridge.set_status(\" · \".join(details))\n",
        "qt_host status",
    )
    host = replace_once(
        host,
        "    parser.add_argument(\"--project-name\", default=\"\", help=\"Nome opcional para o projeto importado.\")\n",
        "    parser.add_argument(\"--project-name\", default=\"\", help=\"Nome opcional para o projeto importado.\")\n    parser.add_argument(\n        \"--image-db-probe\",\n        default=\"\",\n        metavar=\"PRODUCT\",\n        help=\"Valida o Image Database existente no runtime/frozen e imprime o match em JSON.\",\n    )\n",
        "qt_host probe parser",
    )
    host = replace_once(
        host,
        "    try:\n        if args.probe_graphics_api:\n",
        "    try:\n        if args.image_db_probe:\n            runtime = GraphicsImageDatabaseRuntime.from_environment(require_library=True)\n            product = {\"id\": \"probe\", \"name\": str(args.image_db_probe), \"display_name\": str(args.image_db_probe)}\n            candidates = runtime.product_candidates(product)\n            automatic = next((row for row in candidates if row.get(\"automatic\") is True), None)\n            top = candidates[0] if candidates else None\n            manifest = dict(runtime.seed_manifest)\n            report = {\n                \"available\": runtime.available,\n                \"status\": runtime.status,\n                \"library_root\": str(runtime.library_root),\n                \"product\": str(args.image_db_probe),\n                \"candidate_count\": len(candidates),\n                \"top_candidate\": str(top.get(\"image_id\") or \"\") if top else \"\",\n                \"confidence\": float(top.get(\"confidence\") or 0.0) if top else 0.0,\n                \"found\": automatic is not None,\n                \"automatic_image_id\": str(automatic.get(\"image_id\") or \"\") if automatic else \"\",\n                \"catalog_version\": manifest.get(\"catalog_version\"),\n                \"total_products\": manifest.get(\"total_products\"),\n                \"total_images\": manifest.get(\"total_images\"),\n                \"provenance_status\": manifest.get(\"provenance_status\"),\n                \"dedup_status\": manifest.get(\"dedup_status\"),\n            }\n            print(json.dumps(report, ensure_ascii=False, sort_keys=True))\n            return 0 if automatic is not None else 3\n        if args.probe_graphics_api:\n",
        "qt_host probe main",
    )
    write(host_path, host)

    runtime_path = "src/srstudio/graphics2/image_database_runtime.py"
    runtime = Path(runtime_path).read_text(encoding="utf-8")
    runtime = replace_once(
        runtime,
        "        if lookup.best_match is not None:\n            add(lookup.best_match, automatic=True)\n",
        "        if lookup.best_match is not None:\n            add(lookup.best_match, automatic=False)\n",
        "best initially non-automatic",
    )
    runtime = replace_once(
        runtime,
        "            add(candidate, automatic=False)\n        return rows[:limit]\n\n    def augment_payload",
        "            add(candidate, automatic=False)\n        limited = rows[:limit]\n        automatic_id, automatic_reason = self._automatic_selection(limited)\n        for row in limited:\n            row[\"automatic\"] = bool(automatic_id and row[\"image_id\"] == automatic_id)\n            row[\"auto_selection_reason\"] = automatic_reason if row[\"automatic\"] else \"\"\n        return limited\n\n    @staticmethod\n    def _automatic_selection(rows: list[dict[str, Any]]) -> tuple[str, str]:\n        \"\"\"Gate auto-apply using the existing lookup ranking; never re-ranks candidates.\"\"\"\n        if not rows:\n            return \"\", \"no-candidates\"\n        top = rows[0]\n        if str(top.get(\"review_status\") or \"\") != \"accepted\":\n            return \"\", \"top-not-accepted\"\n        top_confidence = float(top.get(\"confidence\") or 0.0)\n        top_identity = float(top.get(\"identity_score\") or 0.0)\n        if top_confidence < 0.67:\n            return \"\", \"below-existing-threshold\"\n        for candidate in rows[1:]:\n            if str(candidate.get(\"review_status\") or \"\") != \"accepted\":\n                continue\n            if str(candidate.get(\"image_id\") or \"\") == str(top.get(\"image_id\") or \"\"):\n                continue\n            confidence = float(candidate.get(\"confidence\") or 0.0)\n            identity = float(candidate.get(\"identity_score\") or 0.0)\n            same_identity_band = identity >= max(0.72, top_identity - 0.08)\n            score_close = confidence >= max(0.67, top_confidence - 0.06)\n            if same_identity_band and score_close:\n                return \"\", \"ambiguous-existing-ranking\"\n        return str(top.get(\"image_id\") or \"\"), \"unambiguous-existing-ranking\"\n\n    def augment_payload",
        "ambiguity gate",
    )
    runtime = replace_once(
        runtime,
        "            if selected is not None and self.library is not None:\n                self.library.record_use(selected[\"image_id\"])\n",
        "            if selected is not None and selected.get(\"image_id\") and self.library is not None:\n                self.library.record_use(selected[\"image_id\"])\n",
        "record selected guard",
    )
    runtime = replace_once(
        runtime,
        "        if confident is None:\n            for key in (\"image_path\", \"image\", \"image_uri\", \"image_asset_id\"):\n                prepared.pop(key, None)\n            return prepared, None\n",
        "        if confident is None:\n            for key in (\"image_path\", \"image\", \"image_uri\", \"image_asset_id\"):\n                prepared.pop(key, None)\n            if candidates:\n                return prepared, {\n                    \"status\": \"candidates\",\n                    \"normalized_name\": normalize_product_name(self._product_name(product)),\n                    \"candidate_ids\": [str(row.get(\"image_id\") or \"\") for row in candidates],\n                    \"confidence\": float(candidates[0].get(\"confidence\") or 0.0),\n                    \"reason\": \"ambiguous-existing-ranking\",\n                }\n            return prepared, None\n",
        "ambiguous binding state",
    )
    write(runtime_path, runtime)

    test_path = "tests/test_graphics2_existing_image_database.py"
    tests = Path(test_path).read_text(encoding="utf-8")
    if "def test_ambiguous_existing_matches_require_manual_choice" in tests:
        raise RuntimeError("ambiguity test already exists")
    tests += '''\n\ndef test_ambiguous_existing_matches_require_manual_choice(tmp_path: Path) -> None:\n    runtime, _, assets = _runtime(tmp_path, [("BATATA INGLESA", (), True), ("BATATA INGLESA", (), True)])\n    candidates = runtime.product_candidates({"id": "p", "name": "BATATA INGLESA"})\n    assert len(candidates) >= 2\n    assert {row["image_id"] for row in candidates[:2]} == {assets[0].id, assets[1].id}\n    assert not any(row["automatic"] for row in candidates)\n    document, slot, image = _document("BATATA INGLESA")\n    session, _ = _attach(runtime, document)\n    transform_before = deepcopy(image.transform)\n    session.bind_product(slot.id, document.metadata["products"][0])\n    assert image.asset_id == ""\n    assert image.visible is False\n    assert image.transform == transform_before\n    assert slot.metadata["image_db_lookup"]["status"] == "candidates"\n    assert len(slot.metadata["image_db_lookup"]["candidate_ids"]) >= 2\n'''
    write(test_path, tests)

    Path("scripts/ci/g2_image_db_rebase_current.py").unlink(missing_ok=True)
    Path("scripts/ci/g2_image_db_rebase_no_workflows.py").unlink(missing_ok=True)
    run("git", "add", "-A")
    changed = run("git", "diff", "--cached", "--name-only", capture=True).splitlines()
    forbidden = [path for path in changed if path.startswith(".github/workflows/")]
    if forbidden:
        raise RuntimeError(f"code-only push unexpectedly modifies workflows: {forbidden}")
    print(run("git", "diff", "--cached", "--stat", capture=True))
    run("git", "commit", "-m", "feat(g2): integrate existing Image Database on current Studio head")
    final_sha = run("git", "rev-parse", "HEAD", capture=True)
    run("git", "push", "origin", f"HEAD:{REPO_BRANCH}")
    print(f"IMAGE_DB_REBASED_SHA={final_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
