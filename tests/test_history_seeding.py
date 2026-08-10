from agent_md.config.models import AgentConfig


def _cfg(history):
    return AgentConfig(
        name="seedy",
        model={"provider": "google", "name": "gemini-2.5-flash"},
        history=history,
    )


async def test_get_last_finished_excludes_self_and_running(db):
    e1 = await db.create_execution("seedy", "manual")
    await db.update_execution(e1, status="success")
    e2 = await db.create_execution("seedy", "manual")  # running
    assert (await db.get_last_finished_execution("seedy", exclude_id=e2)).id == e1
    assert await db.get_last_finished_execution("seedy", exclude_id=e1) is None
