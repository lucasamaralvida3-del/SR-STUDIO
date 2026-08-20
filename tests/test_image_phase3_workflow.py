from pathlib import Path


def test_phase3_workflow_is_scoped_to_image_db_branch_only():
    workflow = Path('.github/workflows/image-db-phase3.yml').read_text(encoding='utf-8')
    assert 'g2/parallel-image-database' in workflow
    assert 'workflow_dispatch:' in workflow
    # The Phase 3 validation workflow must never auto-run on integration/main/stable.
    push_section = workflow.split('push:', 1)[1].split('permissions:', 1)[0]
    assert 'main' not in push_section
    assert 'stable' not in push_section
    assert 'g2/integration-beta' not in push_section


def test_phase3_workflow_uploads_evidence_even_on_failure():
    workflow = Path('.github/workflows/image-db-phase3.yml').read_text(encoding='utf-8')
    assert 'actions/upload-artifact@v4' in workflow
    assert 'image-db-phase3-report' in workflow
    assert 'if: always()' in workflow
