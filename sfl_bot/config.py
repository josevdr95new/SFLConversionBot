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
BOT_VERSION = "1.6.3"
DONATION_ADDRESS = "0xf3Beb26e58FAe01f1D75454062B5A4F6d1F14F5F"  # Reemplazar con dirección real

def configure_logging():
    import logging
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )
    return logging.getLogger(__name__)
