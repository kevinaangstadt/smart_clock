import requests
import time

_cached_result = None
_cached_result_time = 0
_cached_result_ttl = 3600  # Cache for 3600 seconds

def get_localized_time(refresh=False):
    """
    Fetches the current time from the Timezone-API and caches the result.
    If `refresh` is set to True, it will bypass the cache and fetch a new result.
    Returns the JSON response containing the current time and timezone information.
    Raises ValueError if the API request fails.
    Uses a simple caching mechanism to avoid frequent API calls.
    The cache is valid for 3600 seconds (1 hour) by default.
    If the cache is still valid, it returns the cached result instead of making a new request.

    :param refresh: If True, forces a new API call and refreshes the cache.
    :return: JSON response with current time and timezone information.
    :raises ValueError: If the API request fails with a status code other than 200.
    """
    global _cached_result, _cached_result_time, _cached_result_ttl
    if not refresh and _cached_result is not None and (time.time() - _cached_result_time) < _cached_result_ttl:
        return _cached_result

    response = requests.get("https://timezone-api.kevinaangstadt.workers.dev", headers={"User-Agent": "SmartClock/1.0"})

    if response.status_code != 200:
        raise ValueError(f"Error fetching time: {response.status_code}")
    
    _cached_result = response.json()
    _cached_result_time = time.time()
    return _cached_result

def timezone_offset_seconds(refresh=False):
    """
    Returns the timezone offset in seconds from the cached result.
    If the cached result is not available, it fetches the time from the API.
    
    :return: Timezone offset in seconds.
    """
    data = get_localized_time(refresh=refresh)
    
    if 'raw_offset' not in data:
        raise ValueError("Invalid data format: 'raw_offset' not found")
    
    offset = data['raw_offset']
    if 'dst_offset' in data:
        offset += data['dst_offset']
    
    return offset

def timezone_offset_hours_minutes(refresh=False):
    """
    Returns the timezone offset in hours and minutes from the cached result.
    If the cached result is not available, it fetches the time from the API.
    
    :return: Tuple of (hours, minutes) representing the timezone offset.
    """
    offset_seconds = timezone_offset_seconds(refresh=refresh)
    hours = offset_seconds // 3600
    minutes = (offset_seconds % 3600) // 60
    return hours, minutes


def next_change_datetime_utc(refresh=False):
    data = get_localized_time(refresh=refresh)
    next_change = data.get('next_change_time_utc')
    if not next_change:
        return None

    next_change = next_change.split('.', 1)[0].rstrip('Z')
    date_part, time_part = next_change.split('T', 1)
    year, month, day = [int(part) for part in date_part.split('-')]
    hour, minute, second = [int(part) for part in time_part.split(':')]
    return year, month, day, hour, minute, second
