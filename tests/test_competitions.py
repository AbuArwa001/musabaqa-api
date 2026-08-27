import pytest
from app.models.competition import Competition, CompetitionStatus, HostOrganization
from app.models.admin_user import AdminUser, AdminRole
from app.core.security import hash_password, create_staff_token


@pytest.mark.asyncio
async def test_list_and_crud_competitions(client, db):
    admin = AdminUser(
        name="Super Admin",
        email="superadmin@musabaqa.org",
        password_hash=hash_password("adminpass123"),
        role=AdminRole.SUPERADMIN,
        active=True,
    )
    db.add(admin)
    await db.flush()

    token = create_staff_token(user_id=admin.id, role="SUPERADMIN")
    headers = {"Authorization": f"Bearer {token}"}

    # Initial list
    res = await client.get("/api/v1/competitions")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # Create
    create_payload = {
        "title_en": "Test Edition 2027",
        "title_ar": "مسابقة تجريبية",
        "edition_label": "15th Edition (2027)",
        "year": 2027,
        "host_org": "JAMIA_MOSQUE",
        "status": "DRAFT",
        "scope": "COUNTY_REGIONAL",
    }
    res = await client.post("/api/v1/competitions", json=create_payload, headers=headers)
    assert res.status_code == 201
    comp_data = res.json()
    comp_id = comp_data["id"]
    assert comp_data["title_en"] == "Test Edition 2027"

    # Update
    patch_payload = {
        "theme_image_url": "https://example.com/theme.jpg",
        "status": "ACTIVE",
    }
    res_patch = await client.patch(f"/api/v1/competitions/{comp_id}", json=patch_payload, headers=headers)
    assert res_patch.status_code == 200
    assert res_patch.json()["theme_image_url"] == "https://example.com/theme.jpg"
    assert res_patch.json()["status"] == "ACTIVE"

    # Add gallery item
    gal_payload = {
        "url": "https://example.com/photo1.jpg",
        "title": "Recitation Photo",
        "caption": "Candidate reciting",
        "stage": "Semifinals",
    }
    res_gal = await client.post(f"/api/v1/competitions/{comp_id}/gallery", json=gal_payload, headers=headers)
    assert res_gal.status_code == 200
    assert len(res_gal.json()["gallery"]) == 1

    # Replicate to jamia events
    res_rep = await client.post(f"/api/v1/competitions/{comp_id}/replicate-to-jamia-events", headers=headers)
    assert res_rep.status_code == 200
    rep_data = res_rep.json()
    assert rep_data["success"] is True
    assert "description_html" in rep_data

    # Set as current
    res_curr = await client.post(f"/api/v1/competitions/{comp_id}/set-current", headers=headers)
    assert res_curr.status_code == 200
    assert res_curr.json()["is_current"] is True

    # Delete
    res_del = await client.delete(f"/api/v1/competitions/{comp_id}", headers=headers)
    assert res_del.status_code == 204
