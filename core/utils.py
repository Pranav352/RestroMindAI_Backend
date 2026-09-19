import zoneinfo
from datetime import datetime, timedelta, timezone as dt_timezone
from django.utils import timezone

def get_restaurant_tz(restaurant):
    """
    Safely resolves zoneinfo.ZoneInfo for a given Restaurant instance.
    Defaults to 'Asia/Kolkata' if invalid or unassigned.
    """
    tz_str = getattr(restaurant, 'timezone', None) or 'Asia/Kolkata'
    try:
        return zoneinfo.ZoneInfo(tz_str)
    except Exception:
        return zoneinfo.ZoneInfo('Asia/Kolkata')


def get_local_timeframe_bounds(restaurant, timeframe='today', custom_date=None):
    """
    Computes local date range boundaries for a restaurant in its active timezone,
    then converts start_date and end_date to timezone-aware UTC datetimes for exact database filtering.

    Supported timeframes:
      - 'today': Current local day bounds (00:00:00 to 23:59:59 local)
      - 'yesterday': Previous local day bounds
      - 'custom' or 'YYYY-MM-DD': Single date bounds specified by custom_date or string pattern
      - 'all' / 'all_time': Unbounded historical search
      - '7d' / '30d': Rolling interval bounds
    """
    restaurant_tz = get_restaurant_tz(restaurant)
    now_utc = timezone.now()
    now_local = now_utc.astimezone(restaurant_tz)

    tf = (timeframe or 'today').strip().lower()
    is_custom = False
    target_date_obj = None

    if custom_date:
        try:
            target_date_obj = datetime.strptime(str(custom_date).strip(), "%Y-%m-%d").date()
            is_custom = True
        except ValueError:
            pass

    if not is_custom and tf not in ['today', 'yesterday', 'all', 'all_time', '7d', '30d']:
        try:
            target_date_obj = datetime.strptime(tf, "%Y-%m-%d").date()
            is_custom = True
            tf = 'custom'
        except ValueError:
            tf = 'today'

    if tf == 'custom':
        is_custom = True

    if is_custom and target_date_obj:
        start_local = datetime.combine(target_date_obj, datetime.min.time()).replace(tzinfo=restaurant_tz)
        end_local = datetime.combine(target_date_obj, datetime.max.time()).replace(tzinfo=restaurant_tz)

        prev_date_obj = target_date_obj - timedelta(days=1)
        prev_start_local = datetime.combine(prev_date_obj, datetime.min.time()).replace(tzinfo=restaurant_tz)
        prev_end_local = datetime.combine(prev_date_obj, datetime.max.time()).replace(tzinfo=restaurant_tz)

        timeframe_label = target_date_obj.strftime("%b %d, %Y")
    elif tf in ['all', 'all_time']:
        start_local = datetime(2020, 1, 1, 0, 0, 0, tzinfo=restaurant_tz)
        end_local = now_local
        prev_start_local = datetime(2020, 1, 1, 0, 0, 0, tzinfo=restaurant_tz)
        prev_end_local = now_local
        timeframe_label = "All Time"
    elif tf == 'yesterday':
        start_local = (now_local - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local.replace(hour=23, minute=59, second=59, microsecond=999999)
        prev_start_local = (now_local - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
        prev_end_local = prev_start_local.replace(hour=23, minute=59, second=59, microsecond=999999)
        timeframe_label = "Yesterday"
    elif tf == '7d':
        start_local = now_local - timedelta(days=7)
        end_local = now_local
        prev_start_local = now_local - timedelta(days=14)
        prev_end_local = now_local - timedelta(days=7)
        timeframe_label = "Last 7 Days"
    elif tf == '30d':
        start_local = now_local - timedelta(days=30)
        end_local = now_local
        prev_start_local = now_local - timedelta(days=60)
        prev_end_local = now_local - timedelta(days=30)
        timeframe_label = "Last 30 Days"
    else:  # 'today'
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = now_local
        prev_start_local = (now_local - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        prev_end_local = start_local - timedelta(microseconds=1)
        timeframe_label = "Today"

    return {
        "now_local": now_local,
        "restaurant_tz": restaurant_tz,
        "start_date": start_local.astimezone(dt_timezone.utc),
        "end_date": end_local.astimezone(dt_timezone.utc),
        "prev_start_date": prev_start_local.astimezone(dt_timezone.utc),
        "prev_end_date": prev_end_local.astimezone(dt_timezone.utc),
        "timeframe_label": timeframe_label,
        "is_custom": is_custom,
        "timeframe": tf
    }
