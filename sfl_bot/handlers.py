import re
import asyncio
from decimal import Decimal, InvalidOperation, DecimalException
from typing import Optional
from telegram import Update, helpers
from telegram.ext import ContextTypes, CallbackContext
from httpx import HTTPStatusError
from .config import MAX_INPUT_LENGTH, MARKET_FEE
from .services import PriceBot
from datetime import datetime

class Handlers(PriceBot):
    def __init__(self):
        super().__init__()
        self.command_count = 0
        self.error_stats = {
            'api': 0,        # Errores de conexión con APIs externas
            'input': 0,      # Errores de entrada inválida
            'calculation': 0,# Errores en cálculos
            'cache': 0,      # Errores de caché
            'other': 0       # Otros errores no categorizados
        }
        self.start_time = datetime.now()

    def format_decimal(self, value: Decimal) -> str:
        """Formatea valores decimales mostrando:
        - 8 decimales si el valor es < 0.1
        - 4 decimales si el valor es >= 0.1
        Elimina ceros redundantes al final"""
        if value < Decimal('0.1'):
            formatted = f"{value:.8f}"
        else:
            formatted = f"{value:.4f}"
        
        if '.' in formatted:
            formatted = formatted.rstrip('0').rstrip('.')
        return formatted

    async def send_message(self, update: Update, text: str) -> None:
        try:
            await update.message.reply_text(
                text,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except Exception as e:
            import logging
            logging.error(f"Error sending message: {e}")

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.command_count += 1
        try:
            prices = await self.get_prices()
            items_list = ", ".join(sorted(prices.keys()))
            
            welcome_msg = f"""
🌟 *SFL Conversion Bot* 🌟

📌 *Available commands:*
/start - Show this message
/help - Detailed help
`/<item>` ≈ Unit price
`/<item> <amount>` ≈ Conversion with commission
`/usd <amount>` ≈ Convert SFL to USD
`/sfl <amount>` ≈ Convert USD to SFL
`/status` ≈ Show cache status

🔹 *Examples:*
/merino wool ≈ Price of Merino Wool
/merino wool 5 ≈ Convert Merino Wool
/usd 1.2345 ≈ Value of SFL
/sfl 10.5678 ≈ Value of USD

📦 *Available items:*
{items_list}
"""
            await self.send_message(update, welcome_msg)
        except Exception as e:
            self.error_stats['other'] += 1
            await self.send_message(update, "❌ Error showing available items")

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.command_count += 1
        help_msg = """
🛠 *Complete Help*

📝 *Syntax:*
- Items: Case-insensitive, spaces allowed
- Amounts: Numbers with up to 8 decimals

💡 *Examples:*
/stone ≈ Unit price
/stone 20 ≈ Conversion
/usd 1.2345 ≈ Value in USD
/sfl 10.5678 ≈ Value in SFL
"""
        await self.send_message(update, help_msg)

    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.command_count += 1
        try:
            now = datetime.now()
            prices_expiry = getattr(self, "_get_prices_expiry", None)
            exchange_expiry = getattr(self, "_get_exchange_rates_expiry", None)
            
            prices_ttl = (prices_expiry - now).seconds if prices_expiry else 0
            exchange_ttl = (exchange_expiry - now).seconds if exchange_expiry else 0
            
            status_msg = f"""
🔄 *System Status*

📊 Prices cache:
{'Valid' if prices_ttl > 0 else 'Expired'} (TTL: {max(0, prices_ttl)}s)

💱 Exchange cache:
{'Valid' if exchange_ttl > 0 else 'Expired'} (TTL: {max(0, exchange_ttl)}s)
"""
            await self.send_message(update, status_msg)
        except Exception as e:
            self.error_stats['cache'] += 1
            await self.send_message(update, "❌ Error checking system status")

    async def handle_usd_conversion(self, update: Update, amount: Decimal) -> None:
        self.command_count += 1
        try:
            if not await self.validate_amount(amount):
                self.error_stats['input'] += 1
                await self.send_message(update, "⚠️ Amount must be at least 0.00000001")
                return

            rates = await self.get_exchange_rates()
            sfl_rate = rates.get("sfl", {}).get("usd", Decimal('0'))
            
            if sfl_rate <= 0:
                self.error_stats['api'] += 1
                await self.send_message(update, "❌ Invalid exchange rate")
                return
            
            usd_value = amount * sfl_rate
            msg = (
                f"🌻 *{self.format_decimal(amount)} SFL* ≈ *${self.format_decimal(usd_value)} USD*\n"
                f"📊 Current rate: 1 SFL ≈ ${self.format_decimal(sfl_rate)}"
            )
            await self.send_message(update, msg)
        except InvalidOperation:
            self.error_stats['input'] += 1
            await self.send_message(update, "⚠️ Invalid amount format")
        except DecimalException:
            self.error_stats['calculation'] += 1
            await self.send_message(update, "⚠️ Calculation error")
        except Exception as e:
            self.error_stats['other'] += 1
            await self.send_message(update, "❌ Error processing your request")

    async def handle_sfl_conversion(self, update: Update, amount: Decimal) -> None:
        self.command_count += 1
        try:
            if not await self.validate_amount(amount):
                self.error_stats['input'] += 1
                await self.send_message(update, "⚠️ Amount must be at least 0.00000001")
                return

            rates = await self.get_exchange_rates()
            sfl_rate = rates.get("sfl", {}).get("usd", Decimal('0'))
            
            if sfl_rate <= 0:
                self.error_stats['api'] += 1
                await self.send_message(update, "❌ Invalid exchange rate")
                return
            
            sfl_value = amount / sfl_rate
            msg = (
                f"💵 *${self.format_decimal(amount)} USD* ≈ *{self.format_decimal(sfl_value)} SFL*\n"
                f"📊 Current rate: 1 SFL ≈ ${self.format_decimal(sfl_rate)}"
            )
            await self.send_message(update, msg)
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
        self.command_count += 1
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
                safe_name = helpers.escape_markdown(item_name, version=2)
                await self.send_message(update, f"❌ Item '{safe_name}' not found")
                return

            price = prices[item_key]
            sfl_rate = rates.get("sfl", {}).get("usd", Decimal('0'))

            if amount:
                if not await self.validate_amount(amount):
                    self.error_stats['input'] += 1
                    await self.send_message(update, "⚠️ Amount must be at least 0.00000001")
                    return

                gross_sfl = amount * price
                gross_usd = gross_sfl * sfl_rate
                fee = gross_usd * MARKET_FEE
                net_usd = gross_usd - fee
                
                msg = (
                    f"🪙 *{self.format_decimal(amount)} {item_key}* ≈ *{self.format_decimal(gross_sfl)} SFL*\n"
                    f"💵 Gross value: ≈ *${self.format_decimal(gross_usd)}*\n"
                    f"📉 Commission (10%): ≈ *-${self.format_decimal(fee)}*\n"
                    f"🤑 Net received: ≈ *${self.format_decimal(net_usd)}*"
                )
            else:
                msg = f"📈 1 {item_key} ≈ *{self.format_decimal(price)} SFL* (≈ ${self.format_decimal(price * sfl_rate)} USD)"

            await self.send_message(update, msg)
        except InvalidOperation:
            self.error_stats['input'] += 1
            await self.send_message(update, "⚠️ Invalid amount format")
        except DecimalException:
            self.error_stats['calculation'] += 1
            await self.send_message(update, "⚠️ Calculation error")
        except Exception as e:
            self.error_stats['other'] += 1
            await self.send_message(update, "❌ Error processing your request")

    async def handle_item(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.command_count += 1
        if not update.message or not update.message.text:
            return

        try:
            text = update.message.text.strip()
            if len(text) > MAX_INPUT_LENGTH:
                self.error_stats['input'] += 1
                await self.send_message(update, "⚠️ Input too long. Please shorten your request.")
                return

            match = re.match(r"^\/(.+?)(?:\s+([\d\.]{1,20}))?$", text, re.IGNORECASE)
            
            if not match:
                self.error_stats['input'] += 1
                await self.send_message(update, "⚠️ Invalid format. Use /help")
                return

            command, amount_str = match.groups()
            
            try:
                amount = Decimal(amount_str) if amount_str else None
            except InvalidOperation:
                self.error_stats['input'] += 1
                await self.send_message(update, "⚠️ Invalid amount format")
                return

            if command.lower() == "usd":
                if amount is None:
                    await self.send_message(update, "ℹ️ Example: /usd 5.5")
                    return
                await self.handle_usd_conversion(update, amount)
            elif command.lower() == "sfl":
                if amount is None:
                    await self.send_message(update, "ℹ️ Example: /sfl 1.2345")
                    return
                await self.handle_sfl_conversion(update, amount)
            else:
                await self.handle_item_conversion(update, command, amount)

        except Exception as e:
            self.error_stats['other'] += 1
            await self.send_message(update, "❌ Error processing your request")

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