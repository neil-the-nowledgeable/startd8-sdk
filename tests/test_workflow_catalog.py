from startd8.workflows.registry import WORKFLOW_CATALOG, WorkflowDescriptor


def test_catalog_contains_minimal_workflows():
    assert "iterative-dev" in WORKFLOW_CATALOG
    assert "skill-aware" in WORKFLOW_CATALOG
    assert "doc-enhancement-chain" in WORKFLOW_CATALOG
    assert "prompt-builder" in WORKFLOW_CATALOG


def test_catalog_descriptors_have_required_fields():
    for desc in WORKFLOW_CATALOG.values():
        assert isinstance(desc, WorkflowDescriptor)
        assert desc.id
        assert desc.title
        assert desc.runner
        assert isinstance(desc.inputs, list)
        assert desc.supports_multi_agent in (True, False)


def test_catalog_ids_unique():
    ids = [desc.id for desc in WORKFLOW_CATALOG.values()]
    assert len(ids) == len(set(ids))
