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

class Handlers(PriceBot):
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
        self.ad_text = (
            "✨ You can clean my farm please ✨\n"
            "(Puedes limpiar mi granja por favor)\n"
            "👉 [Visit Farm](https://sunflower-land.com/play/#/visit/30911)"
        )

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

    async def send_message(self, update: Update, text: str) -> None:
        try:
            # Construir el mensaje completo con recuadro de publicidad
            full_text = (
                f"{text}\n\n"
                "────────────────\n"
                f"{self.ad_text}\n"
                "────────────────"
            )
            
            await update.message.reply_text(
                full_text,
                parse_mode="MarkdownV2",
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
🌟 SFL Conversion Bot v{BOT_VERSION} 🌟

📌 Available commands:
/start - Show this message
/help - Detailed help
/<item> - Unit price
/<item> <amount> - Conversion with commission
/usd <amount> - Convert Flower to USD
/flower <amount> - Convert USD to Flower
/status - Show cache status
/calc <expression> - Mathematical calculator
/land <number> - Farm details (coming soon)

🔹 Examples:
/merino wool - Price of Merino Wool
/merino wool 5 - Convert Merino Wool
/usd 1.2345 - Value of Flower
/flower 10.5678 - Value of USD
/calc (5+3)*2 - Calculate expression

💝 Donate to support development:
{DONATION_ADDRESS}

📦 Available items:
{items_list}
"""
            await self.send_message(update, welcome_msg)
        except Exception as e:
            self.error_stats['other'] += 1
            await self.send_message(update, "❌ Error showing available items")

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.command_count += 1
        help_msg = f"""
🛠 Complete Help v{BOT_VERSION}

📝 Syntax:
- Items: Case-insensitive, spaces allowed
- Amounts: Numbers with up to 8 decimals

🧮 Calculator Command:
/calc <expression> - Basic math operations
Example: /calc (5+3)*2

🌾 Farm Command (coming soon):
/land <number> - Future farm features

💡 Examples:
/stone - Unit price
/stone 20 - Conversion
/usd 5.5 - Value in USD
/flower 10.5 - Value in Flower
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
🔄 System Status v{BOT_VERSION}

📊 Prices cache:
{'✅ Valid' if prices_ttl > 0 else '❌ Expired'} (TTL: {max(0, prices_ttl)}s)

💱 Exchange cache:
{'✅ Valid' if exchange_ttl > 0 else '❌ Expired'} (TTL: {max(0, exchange_ttl)}s)
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
        self.command_count += 1
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
        except InvalidOperation:
            self.error_stats['input'] += 1
            await self.send_message(update, "⚠️ Invalid amount format")
        except DecimalException:
            self.error_stats['calculation'] += 1
            await self.send_message(update, "⚠️ Calculation error")
        except Exception as e:
            self.error_stats['other'] += 1
            await self.send_message(update, "❌ Error processing your request")

    async def handle_calc(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.command_count += 1
        try:
            expression = ' '.join(context.args)
            if not expression:
                await self.send_message(update, "ℹ️ Example: /calc (5+3)*2")
                return
            
            # Safe evaluation with Decimal
            try:
                # Remove potential harmful characters
                safe_expr = re.sub(r'[^\d\.\+\-\*\/\(\)]', '', expression)
                result = eval(safe_expr, {"__builtins__": None}, {})
                decimal_result = Decimal(str(result))
            except Exception as e:
                self.error_stats['calculation'] += 1
                await self.send_message(update, "⚠️ Error evaluating expression")
                return

            formatted_result = self.format_decimal(decimal_result)
            await self.send_message(update, f"🧮 {expression} = {formatted_result}")
        except Exception as e:
            self.error_stats['other'] += 1
            await self.send_message(update, "❌ Error processing calculation")

    async def handle_land(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.command_count += 1
        try:
            farm_id = ' '.join(context.args)
            if not farm_id:
                await self.send_message(update, "ℹ️ Example: /land 123")
                return
                
            await self.send_message(update, f"🌾 Farm ID {farm_id} details coming soon!")
        except Exception as e:
            self.error_stats['other'] += 1
            await self.send_message(update, "❌ Error processing farm ID")

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
            elif command.lower() == "flower":
                if amount is None:
                    await self.send_message(update, "ℹ️ Example: /flower 1.2345")
                    return
                await self.handle_flower_conversion(update, amount)
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
