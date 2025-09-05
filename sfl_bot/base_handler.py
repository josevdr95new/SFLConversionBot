import re
import asyncio
from decimal import Decimal, InvalidOperation, DecimalException
from typing import Optional
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
        """Valida que la cantidad sea válida"""
        return amount >= Decimal('0.00000001')

    async def calculate_oil_production_cost(self) -> tuple[Decimal, Decimal]:
        """Calcula el costo de producción de petróleo"""
        try:
            prices = await self.get_prices()
            
            # Obtener precios de recursos requeridos
            wood_price = prices.get("wood", Decimal('0'))
            iron_price = prices.get('iron', Decimal('0'))
            leather_price = prices.get('leather', Decimal('0'))
            
            if any(price == 0 for price in [wood_price, iron_price, leather_price]):
                self.error_stats['api'] += 1
                raise ValueError("Could not fetch all required resource prices")
            
            # Calcular costo para 3 taladros (producen 50 petróleo)
            # Cada taladro cuesta: 20 madera, 9 hierro, 10 cuero
            total_wood_cost = Decimal('60') * wood_price  # 3 taladros * 20 madera
            total_iron_cost = Decimal('27') * iron_price  # 3 taladros * 9 hierro
            total_leather_cost = Decimal('30') * leather_price  # 3 taladros * 10 cuero
            
            total_cost = total_wood_cost + total_iron_cost + total_leather_cost
            unit_cost = total_cost / Decimal('50')  # Costo por unidad de petróleo
            
            return total_cost, unit_cost
            
        except Exception as e:
            self.error_stats['calculation'] += 1
            raise e

    async def handle_usd_conversion(self, update: Update, amount: Decimal) -> None:
        """Maneja la conversión de Flower a USD"""
        self.command_count += 1
        await self.update_user_stats(update.effective_user.id)
        try:
            if not await self.validate_amount(amount):
                self.error_stats['input'] += 1
                await self.send_message(update, "⚠️ Amount must be at least 0.00000001")
                return

            rates = await self.get_exchange_rates()
            flower_rate = rates.get("sfl", {}).get("usd", Decimal('0'))
            
            if flower_rate <= 0:
                self.error_stats['api'] += 1
                await self.send_message(update, "❌ Invalid exchange rate")
                return
            
            usd_value = amount * flower_rate
            msg = (
                f"🌻 {self.format_decimal(amount)} Flower ≈ ${self.format_decimal(usd_value)} USD\n"
                f"📊 Current rate: 1 Flower ≈ ${self.format_decimal(flower_rate)}"
            )
            await self.send_message(update, msg)
            await self.send_advertisement(update)
        except InvalidOperation:
            self.error_stats['input'] += 1
            await self.send_message(update, "⚠️ Invalid amount format")
        except DecimalException:
            self.error_stats['calculation'] += 1
            await self.send_message(update, "⚠️ Calculation error")
        except Exception as e:
            self.error_stats['other'] += 1
            await self.send_message(update, "❌ Error processing your request")

    async def handle_flower_conversion(self, update: Update, amount: Decimal) -> None:
        """Maneja la conversión de USD a Flower"""
        self.command_count += 1
        await self.update_user_stats(update.effective_user.id)
        try:
            if not await self.validate_amount(amount):
                self.error_stats['input'] += 1
                await self.send_message(update, "⚠️ Amount must be at least 0.00000001")
                return

            rates = await self.get_exchange_rates()
            flower_rate = rates.get("sfl", {}).get("usd", Decimal('0'))
            
            if flower_rate <= 0:
                self.error_stats['api'] += 1
                await self.send_message(update, "❌ Invalid exchange rate")
                return
            
            flower_value = amount / flower_rate
            msg = (
                f"💵 ${self.format_decimal(amount)} USD ≈ {self.format_decimal(flower_value)} Flower\n"
                f"📊 Current rate: 1 Flower ≈ ${self.format_decimal(flower_rate)}"
            )
            await self.send_message(update, msg)
            await self.send_advertisement(update)
        except InvalidOperation:
            self.error_stats['input'] += 1
            await self.send_message(update, "⚠️ Invalid amount format")
        except DecimalException:
            self.error_stats['calculation'] += 1
            await self.send_message(update, "⚠️ Calculation error")
        except Exception as e:
            self.error_stats['other'] += 1
            await self.send_message(update, "❌ Error processing your request")

    async def handle_item_conversion(self, update: Update, item_name: str, amount: Optional[Decimal]) -> None:
        """Maneja la conversión de items"""
        self.command_count += 1
        await self.update_user_stats(update.effective_user.id)
        try:
            prices, rates = await asyncio.gather(
                self.get_prices(),
                self.get_exchange_rates()
            )
            
            item_key = next(
                (k for k in prices.keys() if k.replace(" ", "").lower() == item_name.replace(" ", "").lower()),
                None
            )
            
            if not item_key:
                self.error_stats['input'] += 1
                await self.send_message(update, f"❌ Item '{item_name}' not found")
                return

            price = prices[item_key]
            flower_rate = rates.get("sfl", {}).get("usd", Decimal('0'))

            if amount:
                if not await self.validate_amount(amount):
                    self.error_stats['input'] += 1
                    await self.send_message(update, "⚠️ Amount must be at least 0.00000001")
                    return

                gross_flower = amount * price
                gross_usd = gross_flower * flower_rate
                fee = gross_usd * MARKET_FEE
                net_usd = gross_usd - fee
                
                msg = (
                    f"📊 Unit Price: 1 {item_key} ≈ {self.format_decimal(price)} Flower\n"
                    f"🪙 {self.format_decimal(amount)} {item_key} ≈ {self.format_decimal(gross_flower)} Flower\n"
                    f"💵 Gross value: ≈ ${self.format_decimal(gross_usd)}\n"
                    f"📉 Commission (10%): ≈ -${self.format_decimal(fee)}\n"
                    f"🤑 Net received: ≈ ${self.format_decimal(net_usd)}"
                )
            else:
                msg = f"📈 1 {item_key} ≈ {self.format_decimal(price)} Flower (≈ ${self.format_decimal(price * flower_rate)} USD)"

            await self.send_message(update, msg)
            await self.send_advertisement(update)
        except InvalidOperation:
            self.error_stats['input'] += 1
            await self.send_message(update, "⚠️ Invalid amount format")
        except DecimalException:
            self.error_stats['calculation'] += 1
            await self.send_message(update, "⚠️ Calculation error")
        except Exception as e:
            self.error_stats['other'] += 1
            await self.send_message(update, "❌ Error processing your request")

    async def error_handler(self, update: object, context: CallbackContext) -> None:
        """Maneja errores globales"""
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
        """Cierra las conexiones al apagar"""
        await self.http_client.aclose()
