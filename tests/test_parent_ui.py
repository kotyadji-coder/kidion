"""
tests/test_parent_ui.py — TDD tests for Parent Dashboard UI (Этап 6).

Covers:
  GET /api/children/{child_id}/stats — new API endpoint
  GET /dashboard   — main parent page after login
  GET /children/new — add child form
  GET /children/{child_id} — child profile page
  GET /children/{child_id}/history — lesson history page
  GET / when logged in → redirects to /dashboard (not /chat)
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

CHILD_PAYLOAD = {
    "name": "Маша",
    "gender": "girl",
    "birth_date": "2018-03-15",
    "grade": 2,
    "universe": "Щенячий патруль",
    "pin_code": "1234",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def create_child_helper(auth_client: AsyncClient) -> int:
    resp = await auth_client.post("/api/children", json=CHILD_PAYLOAD)
    assert resp.status_code == 201, f"Failed to create child: {resp.text}"
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# GET /api/children/{child_id}/stats
# ---------------------------------------------------------------------------

class TestChildStats:
    async def test_stats_requires_auth(self, client: AsyncClient):
        """Returns 401 for unauthenticated requests."""
        resp = await client.get("/api/children/1/stats")
        assert resp.status_code == 401

    async def test_stats_not_found(self, auth_client: AsyncClient):
        """Returns 404 for non-existent child."""
        resp = await auth_client.get("/api/children/999/stats")
        assert resp.status_code == 404

    async def test_stats_forbidden_other_parent(
        self, client: AsyncClient, second_user: dict
    ):
        """Returns 403 if child belongs to another parent."""
        # Register first user, create child
        await client.post("/auth/register", json={"email": "first@example.com", "password": "password123"})
        await client.post("/auth/login", json={"email": "first@example.com", "password": "password123"})
        create_resp = await client.post("/api/children", json=CHILD_PAYLOAD)
        assert create_resp.status_code == 201
        child_id = create_resp.json()["id"]

        # Login as second user
        await client.post("/auth/login", json=second_user)
        resp = await client.get(f"/api/children/{child_id}/stats")
        assert resp.status_code == 403

    async def test_stats_returns_correct_structure(self, auth_client: AsyncClient):
        """Returns correct JSON structure for a child with no history."""
        child_id = await create_child_helper(auth_client)
        resp = await auth_client.get(f"/api/children/{child_id}/stats")
        assert resp.status_code == 200

        data = resp.json()
        assert "total_lessons" in data
        assert "average_stars" in data
        assert "current_streak" in data
        assert "longest_streak" in data
        assert "active_weekly_plan" in data
        assert "active_enrollments" in data

    async def test_stats_new_child_zero_values(self, auth_client: AsyncClient):
        """New child has zero lessons and no active plans."""
        child_id = await create_child_helper(auth_client)
        resp = await auth_client.get(f"/api/children/{child_id}/stats")
        assert resp.status_code == 200

        data = resp.json()
        assert data["total_lessons"] == 0
        assert data["current_streak"] == 0
        assert data["longest_streak"] == 0
        assert data["active_weekly_plan"] is None
        assert data["active_enrollments"] == []

    async def test_stats_average_stars_is_none_or_zero_when_no_results(
        self, auth_client: AsyncClient
    ):
        """average_stars is 0 or null when no lesson results exist."""
        child_id = await create_child_helper(auth_client)
        resp = await auth_client.get(f"/api/children/{child_id}/stats")
        data = resp.json()
        # Should be 0 or null — not an error
        assert data["average_stars"] in (0, 0.0, None)


# ---------------------------------------------------------------------------
# GET /dashboard
# ---------------------------------------------------------------------------

class TestDashboardPage:
    async def test_dashboard_requires_auth(self, client: AsyncClient):
        """Redirects to /login if not authenticated."""
        resp = await client.get("/dashboard", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert "/login" in resp.headers.get("location", "")

    async def test_dashboard_returns_200_when_auth(self, auth_client: AsyncClient):
        """Returns 200 for authenticated parent."""
        resp = await auth_client.get("/dashboard")
        assert resp.status_code == 200

    async def test_dashboard_contains_html(self, auth_client: AsyncClient):
        """Response is HTML containing dashboard content."""
        resp = await auth_client.get("/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    async def test_dashboard_shows_add_child_button(self, auth_client: AsyncClient):
        """Dashboard page contains add child link."""
        resp = await auth_client.get("/dashboard")
        assert resp.status_code == 200
        body = resp.text
        assert "/children/new" in body


# ---------------------------------------------------------------------------
# GET /children/new
# ---------------------------------------------------------------------------

class TestChildNewPage:
    async def test_child_new_requires_auth(self, client: AsyncClient):
        """Redirects to /login if not authenticated."""
        resp = await client.get("/children/new", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert "/login" in resp.headers.get("location", "")

    async def test_child_new_returns_200_when_auth(self, auth_client: AsyncClient):
        """Returns 200 for authenticated parent."""
        resp = await auth_client.get("/children/new")
        assert resp.status_code == 200

    async def test_child_new_contains_form(self, auth_client: AsyncClient):
        """Page contains a form for creating a child."""
        resp = await auth_client.get("/children/new")
        assert resp.status_code == 200
        body = resp.text
        assert "<form" in body


# ---------------------------------------------------------------------------
# GET /children/{child_id}
# ---------------------------------------------------------------------------

class TestChildProfilePage:
    async def test_child_profile_requires_auth(self, client: AsyncClient):
        """Redirects to /login if not authenticated."""
        resp = await client.get("/children/1", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert "/login" in resp.headers.get("location", "")

    async def test_child_profile_not_found(self, auth_client: AsyncClient):
        """Returns 404 for non-existent child."""
        resp = await auth_client.get("/children/999")
        assert resp.status_code == 404

    async def test_child_profile_forbidden(
        self, client: AsyncClient, second_user: dict
    ):
        """Returns 403 if child belongs to another parent."""
        await client.post("/auth/register", json={"email": "owner@example.com", "password": "password123"})
        await client.post("/auth/login", json={"email": "owner@example.com", "password": "password123"})
        create_resp = await client.post("/api/children", json=CHILD_PAYLOAD)
        child_id = create_resp.json()["id"]

        await client.post("/auth/login", json=second_user)
        resp = await client.get(f"/children/{child_id}", follow_redirects=False)
        assert resp.status_code in (403, 302, 307)

    async def test_child_profile_returns_200(self, auth_client: AsyncClient):
        """Returns 200 for owned child."""
        child_id = await create_child_helper(auth_client)
        resp = await auth_client.get(f"/children/{child_id}")
        assert resp.status_code == 200

    async def test_child_profile_contains_child_name(self, auth_client: AsyncClient):
        """Profile page contains the child's name."""
        child_id = await create_child_helper(auth_client)
        resp = await auth_client.get(f"/children/{child_id}")
        assert resp.status_code == 200
        assert "Маша" in resp.text


# ---------------------------------------------------------------------------
# GET /children/{child_id}/history
# ---------------------------------------------------------------------------

class TestChildHistoryPage:
    async def test_history_requires_auth(self, client: AsyncClient):
        """Redirects to /login if not authenticated."""
        resp = await client.get("/children/1/history", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert "/login" in resp.headers.get("location", "")

    async def test_history_not_found(self, auth_client: AsyncClient):
        """Returns 404 for non-existent child."""
        resp = await auth_client.get("/children/999/history")
        assert resp.status_code == 404

    async def test_history_returns_200(self, auth_client: AsyncClient):
        """Returns 200 for owned child."""
        child_id = await create_child_helper(auth_client)
        resp = await auth_client.get(f"/children/{child_id}/history")
        assert resp.status_code == 200

    async def test_history_is_html(self, auth_client: AsyncClient):
        """Returns HTML content."""
        child_id = await create_child_helper(auth_client)
        resp = await auth_client.get(f"/children/{child_id}/history")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# GET / → redirect to /dashboard when logged in
# ---------------------------------------------------------------------------

class TestRootRedirect:
    async def test_root_redirects_to_dashboard_when_auth(
        self, auth_client: AsyncClient
    ):
        """Logged-in user is redirected to /dashboard from /."""
        resp = await auth_client.get("/", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert resp.headers.get("location", "").rstrip("/") in ("/dashboard", "http://testserver/dashboard")

    async def test_root_shows_landing_when_not_auth(self, client: AsyncClient):
        """Unauthenticated user sees landing page at /."""
        resp = await client.get("/", follow_redirects=False)
        # Either 200 (landing) or redirect to login — not redirect to /dashboard
        location = resp.headers.get("location", "")
        if resp.status_code in (302, 307):
            assert "/dashboard" not in location
        else:
            assert resp.status_code == 200
