import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_db, require_role
from app.models.admin_user import AdminRole
from app.models.competition import Competition, CompetitionStatus, HostOrganization
from app.models.category import Category
from app.schemas.competition import (
    CompetitionCreate,
    CompetitionRead,
    CompetitionUpdate,
    GalleryItem,
    CategoryWinnersPodium,
    EventReplicationResponse,
)

router = APIRouter(prefix="/competitions", tags=["Competitions & History"])


@router.get("", response_model=list[CompetitionRead])
async def list_competitions(
    status_filter: CompetitionStatus | None = Query(default=None, alias="status"),
    host_org: HostOrganization | None = None,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Lists all competition editions ordered by year desc, then created_at desc."""
    q = select(Competition)
    if status_filter:
        q = q.where(Competition.status == status_filter)
    if host_org:
        q = q.where(Competition.host_org == host_org)
    if year:
        q = q.where(Competition.year == year)

    q = q.order_by(Competition.is_current.desc(), Competition.year.desc(), Competition.id.desc())
    return (await db.execute(q)).scalars().all()


@router.get("/{comp_id}", response_model=CompetitionRead)
async def get_competition(comp_id: int, db: AsyncSession = Depends(get_db)):
    """Fetches details of a specific competition edition."""
    comp = await db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Competition edition not found")
    return comp


@router.post("", response_model=CompetitionRead, status_code=status.HTTP_201_CREATED)
async def create_competition(
    data: CompetitionCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    """Creates a new competition edition."""
    # If is_current is true, un-set other active current competitions
    if data.is_current:
        existing_current = (await db.execute(
            select(Competition).where(Competition.is_current == True)
        )).scalars().all()
        for ec in existing_current:
            ec.is_current = False
            db.add(ec)

    comp = Competition(**data.model_dump())
    db.add(comp)
    await db.flush()
    await db.refresh(comp)
    await db.commit()
    return comp


@router.patch("/{comp_id}", response_model=CompetitionRead)
async def update_competition(
    comp_id: int,
    data: CompetitionUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    """Updates competition metadata, banner, theme image, dates, or status."""
    comp = await db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Competition edition not found")

    dump = data.model_dump(exclude_unset=True)

    if dump.get("is_current") is True:
        existing_current = (await db.execute(
            select(Competition).where(Competition.is_current == True, Competition.id != comp_id)
        )).scalars().all()
        for ec in existing_current:
            ec.is_current = False
            db.add(ec)

    for field, value in dump.items():
        setattr(comp, field, value)

    comp.updated_at = datetime.now(timezone.utc)
    db.add(comp)
    await db.flush()
    await db.refresh(comp)
    await db.commit()
    return comp


@router.delete("/{comp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_competition(
    comp_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    """Deletes a competition edition."""
    comp = await db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Competition edition not found")
    await db.delete(comp)
    await db.commit()


@router.post("/{comp_id}/set-current", response_model=CompetitionRead)
async def set_current_competition(
    comp_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    """Switches the active current competition edition."""
    comp = await db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Competition edition not found")

    # Set all other competitions to is_current = False
    all_comps = (await db.execute(select(Competition))).scalars().all()
    for c in all_comps:
        c.is_current = (c.id == comp_id)
        if c.id == comp_id and c.status == CompetitionStatus.DRAFT:
            c.status = CompetitionStatus.ACTIVE
        db.add(c)

    await db.flush()
    await db.refresh(comp)
    await db.commit()
    return comp


@router.post("/{comp_id}/gallery", response_model=CompetitionRead)
async def add_gallery_item(
    comp_id: int,
    item: GalleryItem,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    """Adds an image or media item to the competition gallery."""
    comp = await db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Competition edition not found")

    new_item = item.model_dump()
    if not new_item.get("id"):
        new_item["id"] = f"gal_{uuid.uuid4().hex[:8]}"
    if not new_item.get("date"):
        new_item["date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    current_gallery = list(comp.gallery or [])
    current_gallery.append(new_item)
    comp.gallery = current_gallery
    comp.updated_at = datetime.now(timezone.utc)

    db.add(comp)
    await db.flush()
    await db.refresh(comp)
    await db.commit()
    return comp


@router.delete("/{comp_id}/gallery/{item_id}", response_model=CompetitionRead)
async def delete_gallery_item(
    comp_id: int,
    item_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    """Removes a media item from the competition gallery."""
    comp = await db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Competition edition not found")

    current_gallery = [g for g in (comp.gallery or []) if g.get("id") != item_id]
    comp.gallery = current_gallery
    comp.updated_at = datetime.now(timezone.utc)

    db.add(comp)
    await db.flush()
    await db.refresh(comp)
    await db.commit()
    return comp


@router.get("/{comp_id}/podium", response_model=list[CategoryWinnersPodium])
async def get_competition_podium(comp_id: int, db: AsyncSession = Depends(get_db)):
    """
    Returns the Podium / Winners Hall of Fame (Top 1, 2, 3) for each judging category
    for this competition edition.
    """
    comp = await db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Competition edition not found")

    categories = (await db.execute(select(Category).order_by(Category.display_order.asc()))).scalars().all()
    podium_list: list[CategoryWinnersPodium] = []

    # Check if winners array is already populated in the competition record
    stored_winners_by_cat = {w.get("category_id"): w for w in (comp.winners or [])}

    for cat in categories:
        if cat.id in stored_winners_by_cat:
            w_data = stored_winners_by_cat[cat.id]
            podium_list.append(CategoryWinnersPodium(
                category_id=cat.id,
                category_name_en=cat.name_en,
                category_name_ar=cat.name_ar,
                rank_1=w_data.get("rank_1"),
                rank_2=w_data.get("rank_2"),
                rank_3=w_data.get("rank_3"),
                honorable_mentions=w_data.get("honorable_mentions", []),
            ))
        else:
            podium_list.append(CategoryWinnersPodium(
                category_id=cat.id,
                category_name_en=cat.name_en,
                category_name_ar=cat.name_ar,
                rank_1=None,
                rank_2=None,
                rank_3=None,
                honorable_mentions=[],
            ))

    return podium_list


@router.post("/{comp_id}/replicate-to-jamia-events", response_model=EventReplicationResponse)
async def replicate_to_jamia_events(
    comp_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    """
    Generates a structured event payload formatted for jamia-admin / jamia events.
    Includes rich HTML description, podium winners breakdown, venue, and gallery links.
    """
    comp = await db.get(Competition, comp_id)
    if not comp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Competition edition not found")

    # Build rich HTML description
    html_parts = []
    if comp.description_en:
        html_parts.append(f"<p>{comp.description_en}</p>")

    html_parts.append(f"<p><strong>Organizer / Host:</strong> {comp.host_org_name_en}</p>")
    html_parts.append(f"<p><strong>Venue:</strong> {comp.venue_en or 'Jamia Mosque, Nairobi'}</p>")

    if comp.grand_finale_date:
        html_parts.append(f"<p><strong>Grand Finale Date:</strong> {comp.grand_finale_date.strftime('%B %d, %Y')}</p>")

    # Add Winners Podium section if available
    if comp.winners:
        html_parts.append("<h3>🏆 Quran Musabaqa Winners & Podium</h3><ul>")
        for cat_w in comp.winners:
            cat_name = cat_w.get("category_name_en") or f"Category #{cat_w.get('category_id')}"
            html_parts.append(f"<li><strong>{cat_name}:</strong>")
            html_parts.append("<ol>")
            if cat_w.get("rank_1"):
                r1 = cat_w["rank_1"]
                html_parts.append(f"<li>🥇 1st Place: {r1.get('student_name', '')} ({r1.get('institution_name', '')}) — Score: {r1.get('score', 0)}%</li>")
            if cat_w.get("rank_2"):
                r2 = cat_w["rank_2"]
                html_parts.append(f"<li>🥈 2nd Place: {r2.get('student_name', '')} ({r2.get('institution_name', '')}) — Score: {r2.get('score', 0)}%</li>")
            if cat_w.get("rank_3"):
                r3 = cat_w["rank_3"]
                html_parts.append(f"<li>🥉 3rd Place: {r3.get('student_name', '')} ({r3.get('institution_name', '')}) — Score: {r3.get('score', 0)}%</li>")
            html_parts.append("</ol></li>")
        html_parts.append("</ul>")

    description_html = "".join(html_parts)

    payload = {
        "title": comp.title_en,
        "location": comp.venue_en or "Jamia Mosque Multi-Purpose Hall, Nairobi, Kenya",
        "start_at": comp.start_date.isoformat() if comp.start_date else None,
        "end_at": comp.end_date.isoformat() if comp.end_date else None,
        "published": True,
        "image_url": comp.theme_image_url or comp.banner_url,
        "description": description_html,
        "category": "Musabaqa",
    }

    return EventReplicationResponse(
        success=True,
        competition_id=comp.id,
        title=comp.title_en,
        location=payload["location"],
        start_at=payload["start_at"],
        end_at=payload["end_at"],
        image_url=payload["image_url"],
        description_html=description_html,
        gallery_count=len(comp.gallery or []),
        winners_count=len(comp.winners or []),
        payload_ready_for_jamia_events=payload,
    )
