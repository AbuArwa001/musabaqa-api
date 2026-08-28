import re

with open("app/api/v1/routes/scoring.py", "r") as f:
    content = f.read()

old_logic = """    # Check if this was the last judge — trigger ranking engine if so
    if await all_judges_submitted(db, data.round_id, data.student_id):
        await finalize_and_broadcast(db, data.round_id, data.student_id)

    await db.commit()"""

new_logic = """    # Check if this was the last judge — trigger ranking engine if so
    if await all_judges_submitted(db, data.round_id, data.student_id):
        await finalize_and_broadcast(db, data.round_id, data.student_id)

    # Always broadcast a real-time update to moderators/admins
    from app.core.websocket_manager import ws_manager
    await ws_manager.broadcast_admin({
        "type": "SCORE_UPDATED",
        "round_id": data.round_id,
        "student_id": data.student_id,
    })

    await db.commit()"""

content = content.replace(old_logic, new_logic)

with open("app/api/v1/routes/scoring.py", "w") as f:
    f.write(content)
