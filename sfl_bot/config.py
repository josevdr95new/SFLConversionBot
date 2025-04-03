import os
import locale
from decimal import Decimal, getcontext
from dotenv import load_dotenv

# Initial configuration
load_dotenv()
getcontext().prec = 12
locale.setlocale(locale.LC_ALL, '')

# API Constants
PRICES_API_URL = "https://sfl.world/api/v1/prices"
EXCHANGE_API_URL = "https://sfl.world/api/v1/exchange"
REQUEST_TIMEOUT = 5.0
CACHE_TTL = int(os.getenv("CACHE_TTL", 300))
MARKET_FEE = Decimal(os.getenv("MARKET_FEE", "0.10"))
MAX_INPUT_LENGTH = 50

def configure_logging():
    import logging
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )
    return logging.getLogger(__name__)