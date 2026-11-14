"""Unit tests for purge_all_project_issues and /reset Jira cleanup."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from api.auth import mint_demo_jwt
from api.main import app
from connectors.jira_ops import purge_all_project_issues


def test_purge_all_project_issues_demo_mode(monkeypatch):
    """When real Jira credentials are unset, purge_all_project_issues returns demo mode cleanly."""
    monkeypatch.setenv("JIRA_BASE_URL", "")
    res = purge_all_project_issues()
    assert res["mode"] == "demo"
    assert res["purged"] == 0
    assert res["keys"] == []


def test_purge_all_project_issues_with_mocked_jira():
    """Verify purge_all_project_issues queries JQL and deletes issues."""
    with patch("connectors.jira_ops.has_real_jira_creds", return_value=True), \
         patch("connectors.jira_ops.httpx.post") as mock_post, \
         patch("connectors.jira_ops.httpx.delete") as mock_delete:

        # Mock JQL search response with 2 issues
        mock_search_resp = MagicMock()
        mock_search_resp.status_code = 200
        mock_search_resp.json.return_value = {
            "issues": [{"key": "SCRUM-101"}, {"key": "SCRUM-102"}],
            "isLast": True,
        }
        mock_post.return_value = mock_search_resp

        # Mock issue deletion responses
        mock_del_resp = MagicMock()
        mock_del_resp.status_code = 204
        mock_delete.return_value = mock_del_resp

        res = purge_all_project_issues("SCRUM")

        assert res["mode"] == "live_jira"
        assert res["purged"] == 2
        assert res["keys"] == ["SCRUM-101", "SCRUM-102"]
        assert mock_delete.call_count == 2


def test_reset_endpoint_schedules_purge_all_project_issues():
    """Calling POST /api/reset schedules purge_all_project_issues in background."""
    client = TestClient(app)
    mgr_token = mint_demo_jwt(user_id="user_test_mgr", org_id="org_demo_horizon", role="org:admin")

    with patch("connectors.jira_ops.purge_all_project_issues") as mock_purge:
        mock_purge.return_value = {"purged": 0, "keys": [], "mode": "demo"}
        resp = client.post(
            "/api/reset",
            headers={"Authorization": f"Bearer {mgr_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "reset"
        # Since BackgroundTasks runs during TestClient request cycle, purge must be called
        assert mock_purge.called
