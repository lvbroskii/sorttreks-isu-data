from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def local_instant(day, clock, zone):
    """Reject DST gaps and folds rather than choose an arbitrary instant."""
    wall = datetime.fromisoformat(f"{day}T{clock}")
    tz = ZoneInfo(zone)
    candidates = {}
    for fold in (0, 1):
        aware = wall.replace(tzinfo=tz, fold=fold)
        if aware.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) == wall:
            candidates[aware.astimezone(timezone.utc)] = aware
    if len(candidates) != 1:
        raise ValueError(f"Ambiguous/nonexistent local time: {day} {clock} {zone}")
    return next(iter(candidates.values())).isoformat(timespec='seconds')


def display(instant, zone='Europe/Riga', lang='lv'):
    dt = datetime.fromisoformat(instant).astimezone(ZoneInfo(zone))
    return dt.strftime('%d.%m. %H:%M' if lang == 'lv' else '%d %b, %H:%M')
