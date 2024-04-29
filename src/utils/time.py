import time
from datetime import datetime
import pytz

def current_datetime_millis() -> str:
    """ 
    Returns current datetime with millisecond precision, suitable for logging or charting.
    """
    current_time = datetime.now()
    return current_time.strftime("%Y-%m-%d %H:%M:%S") + f".{current_time.microsecond // 1000:03d}"

def time_ms() -> int:
    """ 
    Returns the current time in milliseconds. Marginally faster than using time() * 1000.
    """
    return int(time.time() * 1000)

def time_us() -> int:
    """ 
    Returns the current time in microseconds. Marginally faster than using time() * 1_000_000.
    """
    return int(time.time() * 1_000_000)

def datetime_to_unix(date_str: str, timezone: str = 'America/New_York') -> int:
    """
    Converts a datetime string of the format 'YYYYMMDD HH:MM:SS' from a given timezone to a Unix timestamp in milliseconds in UTC.
    
    Args:
        date_str (str): The datetime string to convert, e.g., '20240311 05:30:17'.
        timezone (str): The timezone of the datetime string, default is 'America/New_York'.
    
    Returns:
        int: Unix timestamp in milliseconds (UTC).
    """
    tz = pytz.timezone(timezone)
    naive_datetime = datetime.strptime(date_str, "%Y%m%d %H:%M:%S")
    local_datetime = tz.localize(naive_datetime, is_dst=None)  # Localize the naive datetime with the specified timezone
    
    utc_datetime = local_datetime.astimezone(pytz.utc)  # Convert the local datetime to UTC
    
    return int(utc_datetime.timestamp() * 1000)