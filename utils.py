import time
import logging
from functools import wraps
from googleapiclient.errors import HttpError

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def retry_on_rate_limit(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        retries = 3
        for attempt in range(retries):
            try:
                return func(*args, **kwargs)
            except HttpError as e:
                if e.resp.status == 403 and 'rate limit' in str(e).lower():
                    if attempt < retries - 1:
                        wait_time = 2 ** attempt
                        logging.warning(f"Rate limit hit, retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                raise
        raise HttpError("Max retries reached for rate limit", resp={'status': 429})
    return wrapper