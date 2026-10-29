"""Adaptive due selection. Polling never drives the website's per-second clock."""
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo


def cadence(event,now):
    start=datetime.fromisoformat(event['startDate']).replace(tzinfo=ZoneInfo(event['timeZone'])).astimezone(timezone.utc)
    end=(datetime.fromisoformat(event['endDate'])+timedelta(days=1)).replace(tzinfo=ZoneInfo(event['timeZone'])).astimezone(timezone.utc)
    if start<=now<end:return 30  # minutes; covers entire local competition days
    if start-timedelta(hours=48)<=now<start:return 30
    if start-timedelta(hours=72)<=now<start:return 120
    if start-timedelta(days=14)<=now<start:return 240
    return 1440


def due(events,last_checks,now):
    result=[]
    for event in events:
        prev=last_checks.get(event['id'])
        interval=cadence(event,now)
        if not prev or now-datetime.fromisoformat(prev)>=timedelta(minutes=interval)-timedelta(seconds=60):result.append(event)
    return result
