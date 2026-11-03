"""Protect production and active work while reclaiming merged preview branches."""
import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "cleanup_neon_preview.py"


def cleanup_module():
    assert SCRIPT.exists(), "The merged-preview cleanup policy is not implemented"
    spec = importlib.util.spec_from_file_location("cleanup_neon_preview", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preview(**overrides):
    return {
        "id": "br-test", "name": "preview/codex/example",
        "project_id": "gentle-king-25994955", "parent_id": "br-blue-salad-anselaqv",
        "creation_source": "vercel", "primary": False, "default": False,
        "protected": False, "restricted_actions": [], **overrides,
    }


def merged_pr(**overrides):
    return {
        "number": 68, "merged_at": "2026-11-03T03:17:33Z", "state": "closed",
        "head": {"ref": "codex/example", "sha": "merged-head",
                 "repo": {"full_name": "zzzhhn/alpha-agent"}}, **overrides,
    }


def test_only_matching_merged_preview_is_selected():
    cleanup = cleanup_module()
    branches = [preview(), preview(id="br-other", name="preview/codex/other")]
    assert cleanup.select_preview(branches, merged_pr(), [], "merged-head") == "br-test"


@pytest.mark.parametrize("overrides", [
    {"id": "br-blue-salad-anselaqv"}, {"name": "main"}, {"primary": True},
    {"default": True}, {"protected": True}, {"creation_source": "console"},
    {"project_id": "another-project"}, {"parent_id": "another-parent"},
    {"restricted_actions": [{"name": "delete", "reason": "production"}]},
])
def test_production_and_unmanaged_branches_are_never_selected(overrides):
    cleanup = cleanup_module()
    assert cleanup.select_preview([preview(**overrides)], merged_pr(), [], None) is None


def test_open_or_reused_git_branch_is_preserved():
    cleanup = cleanup_module()
    assert cleanup.select_preview([preview()], merged_pr(), [{"number": 69}], "merged-head") is None
    assert cleanup.select_preview([preview()], merged_pr(), [], "new-work") is None


def test_unmerged_or_fork_pr_cannot_delete_a_branch():
    cleanup = cleanup_module()
    assert cleanup.select_preview([preview()], merged_pr(merged_at=None), [], None) is None
    foreign = merged_pr(head={"ref": "codex/example", "sha": "merged-head",
                              "repo": {"full_name": "someone/fork"}})
    assert cleanup.select_preview([preview()], foreign, [], None) is None


def test_parent_with_children_and_absent_branch_are_preserved():
    cleanup = cleanup_module()
    child = preview(id="br-child", name="saved-experiment", parent_id="br-test")
    assert cleanup.select_preview([preview(), child], merged_pr(), [], None) is None
    assert cleanup.select_preview([], merged_pr(), [], None) is None


class FakeGitHub:
    def __init__(self, head="merged-head"):
        self.head = head

    def request(self, path, method="GET", allow_missing=False):
        assert method == "GET"
        if path == "/repos/zzzhhn/alpha-agent/pulls/68":
            return merged_pr()
        if "/git/ref/heads/" in path:
            return {"object": {"sha": self.head}}
        if "/pulls?state=open&head=zzzhhn%3Acodex%2Fexample" in path:
            return []
        raise AssertionError(f"Unexpected GitHub request: {path}")


class FakeNeon:
    def __init__(self):
        self.branches = [preview()]
        self.deleted = []

    def request(self, path, method="GET", allow_missing=False):
        if path == "/projects/gentle-king-25994955/branches?limit=100" and method == "GET":
            return {"branches": self.branches}
        if path == "/projects/gentle-king-25994955/branches/br-test" and method == "DELETE":
            self.deleted.append("br-test")
            self.branches = []
            return {"branch": preview(), "operations": []}
        raise AssertionError(f"Unexpected Neon request: {method} {path}")


def test_dry_run_preserves_data_and_apply_deletes_only_the_eligible_branch():
    cleanup = cleanup_module()
    github, neon = FakeGitHub(), FakeNeon()
    assert cleanup.cleanup_pr(github, neon, 68)["status"] == "would_delete"
    assert neon.deleted == []
    assert cleanup.cleanup_pr(github, neon, 68, apply=True)["status"] == "deleted"
    assert neon.deleted == ["br-test"]
    assert cleanup.cleanup_pr(github, neon, 68, apply=True)["status"] == "preserved_or_absent"
    assert neon.deleted == ["br-test"]


def test_a_reused_branch_is_not_deleted_through_the_real_cleanup_path():
    cleanup = cleanup_module()
    neon = FakeNeon()
    assert cleanup.cleanup_pr(FakeGitHub(head="new-work"), neon, 68, apply=True)["status"] == "preserved_or_absent"
    assert neon.deleted == []


def test_an_incomplete_neon_inventory_stops_deletion():
    cleanup = cleanup_module()

    class PagedNeon(FakeNeon):
        def request(self, path, method="GET", allow_missing=False):
            result = super().request(path, method, allow_missing)
            return {**result, "pagination": {"next": "next-page"}}

    neon = PagedNeon()
    with pytest.raises(RuntimeError, match="inventory incomplete"):
        cleanup.cleanup_pr(FakeGitHub(), neon, 68, apply=True)
    assert neon.deleted == []
