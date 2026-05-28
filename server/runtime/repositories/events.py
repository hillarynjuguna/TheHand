from runtime import events


def recent(limit: int = 100) -> list[dict]:
    return events.fetch_events(limit=limit)


def timeline(entity_id: str, limit: int = 200) -> list[dict]:
    return events.fetch_entity_timeline(entity_id, limit=limit)
