import re
import asyncio
from decimal import Decimal, InvalidOperation, DecimalException
from typing import Optional, Dict, Tuple
from telegram import Update
from telegram.ext import ContextTypes, CallbackContext
from httpx import HTTPStatusError
from .config import MAX_INPUT_LENGTH, MARKET_FEE, BOT_VERSION, DONATION_ADDRESS
from .services import PriceBot
from datetime import datetime

def escape_markdown(text: str) -> str:
    """Escapa todos los caracteres reservados de MarkdownV2"""
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return ''.join(['\\' + char if char in escape_chars else char for char in text])

class BaseHandler(PriceBot):
    def __init__(self):
        super().__init__()
        self.command_count = 0
        self.error_stats = {
            'api': 0,
            'input': 0,
            'calculation': 0,
            'cache': 0,
            'other': 0
        }
        self.start_time = datetime.now()
        self.advertisement_shown = {}  # Diccionario para rastrear anuncios por chat
        # Nuevo: Seguimiento de usuarios únicos
        self.unique_users = set()
        self.daily_users = set()
        self.last_reset = datetime.now().date()

    def format_decimal(self, value: Decimal) -> str:
        """Format decimal values showing:
        - 8 decimals if value < 0.1
        - 4 decimals if value >= 0.1
        Removes trailing zeros"""
        if value < Decimal('0.1'):
            formatted = f"{value:.8f}"
        else:
            formatted = f"{value:.4f}"
        
        if '.' in formatted:
            formatted = formatted.rstrip('0').rstrip('.')
        return formatted

    async def update_user_stats(self, user_id: int) -> None:
        """Actualiza estadísticas de usuarios únicos"""
        current_date = datetime.now().date()
        
        # Reiniciar contador diario si cambió la fecha
        if current_date != self.last_reset:
            self.daily_users.clear()
            self.last_reset = current_date
            
        self.unique_users.add(user_id)
        self.daily_users.add(user_id)

    async def send_message(self, update: Update, text: str) -> None:
        try:
            # Escapar automáticamente todo el texto Markdown
            escaped_text = escape_markdown(text)
            await update.message.reply_text(
                escaped_text,
                parse_mode="MarkdownV2",
                disable_web_page_preview=True
            )
        except Exception as e:
            import logging
            logging.error(f"Error sending message: {e}")

    async def send_advertisement(self, update: Update, force: bool = False) -> None:
        """Envía el mensaje publicitario en inglés y español"""
        chat_id = update.message.chat_id
        
        if not force:
            # Mostrar anuncio máximo 1 vez cada 10 comandos por chat
            ad_count = self.advertisement_shown.get(chat_id, 0)
            
            # Mostrar anuncio cada 10 comandos (en el comando 10, 20, 30, etc.)
            if ad_count % 10 != 0:
                self.advertisement_shown[chat_id] = ad_count + 1
                return
                
            self.advertisement_shown[chat_id] = ad_count + 1

        try:
            # Separador visual (sin formato Markdown para evitar problemas)
            await update.message.reply_text(
                "══════════════════",
                disable_web_page_preview=True
            )
            
            # Mensaje bilingüe con formato MarkdownV2 correctamente escapado
            ad_text = (
                "🌟 *Please support the project by cleaning and following my farm\\!* 🌾\n"
                "[Visit my farm now](https://sunflower-land\\.com/play/#/visit/30911)\n\n"
                "🌟 *Por favor apoya el proyecto limpiando y siguiendo mi granja\\!* 🌾\n"
                "[Visita mi granja ahora](https://sunflower-land\\.com/play/#/visit/30911)"
            )
            await update.message.reply_text(
                ad_text,
                parse_mode="MarkdownV2",
                disable_web_page_preview=True
            )
        except Exception as e:
            import logging
            logging.error(f"Error sending advertisement: {e}")

    async def validate_amount(self, amount: Decimal) -> bool:
        """Validate amount is positive and within acceptable range"""
        return amount > Decimal('0') and amount <= Decimal('1000000000')

    async def calculate_oil_production_cost(self, prices: Dict[str, Decimal]) -> Tuple[Decimal, Dict[str, str]]:
        """Calculate oil production cost and return unit price and breakdown"""
        wood_price = prices.get("wood", Decimal('0'))
        iron_price = prices.get('iron', Decimal('0'))
        leather_price = prices.get('leather', Decimal('0'))
        
        if any(price == 0 for price in [wood_price, iron_price, leather_price]):
            raise ValueError("Could not fetch all required resource prices")
        
        # Calculate cost for 3 drills (produces 50 oil)
        # Each drill costs: 20 wood, 9 iron, 10 leather
        total_wood_cost = Decimal('60') * wood_price  # 3 drills * 20 wood
        total_iron_cost = Decimal('27') * iron_price  # 3 drills * 9 iron
        total_leather_cost = Decimal('30') * leather_price  # 3 drills * 10 leather
        
        total_cost = total_wood_cost + total_iron_cost + total_leather_cost
        
        # Calculate unit prices
        unit_price = total_cost / Decimal('50')
        
        # Create breakdown message
        breakdown = {
            'wood': f"60 Wood: {self.format_decimal(total_wood_cost)} Flower",
            'iron': f"27 Iron: {self.format_decimal(total_iron_cost)} Flower",
            'leather': f"30 Leather: {self.format_decimal(total_leather_cost)} Flower",
            'total': f"Total cost: {self.format_decimal(total_cost)} Flower +300 coins",
            'unit': f"Unit cost: {self.format_decimal(unit_price)} Flower/oil"
        }
        
        return unit_price, breakdown

    async def error_handler(self, update: object, context: CallbackContext) -> None:
        error = context.error
        if isinstance(error, HTTPStatusError):
            self.error_stats['api'] += 1
        elif isinstance(error, (InvalidOperation, ValueError)):
            self.error_stats['input'] += 1
        elif isinstance(error, (DecimalException, ZeroDivisionError)):
            self.error_stats['calculation'] += 1
        else:
            self.error_stats['other'] += 1

        if isinstance(update, Update) and update.message:
            await self.send_message(update, "⚠️ Internal error. Please try again.")

    async def shutdown(self) -> None:
        await self.http_client.aclose()
