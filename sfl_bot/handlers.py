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
        self.advertisement_shown = {}  # Diccionario para rastrear anuncios por chat
        
        # Configuración específica para Oil
        self.oil_drill_components = {
            "Wood": 20,
            "Iron": 9,
            "Leather": 10
        }
        self.oil_production = [10, 10, 30]  # Producción por cada taladro
        self.oil_drills_needed = 3  # Cantidad de taladros necesarios para la producción completa

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

    async def get_prices(self):
        """Obtiene precios y añade Oil calculado"""
        prices = await super().get_prices()
        
        # Calcular precio del petróleo si tenemos los materiales necesarios
        if all(item in prices for item in self.oil_drill_components):
            try:
                # Calcular costo total de los 3 taladros
                drill_cost = sum(
                    Decimal(qty) * prices[item] * Decimal(self.oil_drills_needed)
                    for item, qty in self.oil_drill_components.items()
                )
                
                # Calcular producción total de petróleo (10 + 10 + 30 = 50)
                total_oil = sum(self.oil_production)
                
                # Calcular precio por unidad de petróleo
                oil_price = drill_cost / Decimal(total_oil)
                prices["Oil"] = oil_price
            except (TypeError, InvalidOperation, DecimalException):
                # Si hay error en el cálculo, no añadimos el precio
                pass
        
        return prices

    async def send_advertisement(self, update: Update) -> None:
        """Envía el mensaje publicitario en inglés y español"""
        chat_id = update.message.chat_id
        
        # Mostrar anuncio máximo 1 vez cada 3 comandos por chat
        ad_count = self.advertisement_shown.get(chat_id, 0)
        if ad_count > 0 and ad_count % 3 != 0:
            self.advertisement_shown[chat_id] = ad_count + 1
            return
            
        self.advertisement_shown[chat_id] = ad_count + 1

        try:
            # Separador visual
            await update.message.reply_text(
                "══════════════════",
                parse_mode="MarkdownV2",
                disable_web_page_preview=True
            )
            
            # Mensaje bilingüe
            ad_text = (
                "🌟 *Please support the project by cleaning and following my farm\!* 🌾\n"
                "[Visit my farm now](https://sunflower-land.com/play/#/visit/30911)\n\n"
                "🌟 *Por favor apoya el proyecto limpiando y siguiendo mi granja\!* 🌾\n"
                "[Visita mi granja ahora](https://sunflower-land.com/play/#/visit/30911)"
            )
            await update.message.reply_text(
                ad_text,
                parse_mode="MarkdownV2",
                disable_web_page_preview=True
            )
        except Exception as e:
            import logging
            logging.error(f"Error sending advertisement: {e}")

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
/land <number> - Farm details

🔹 Examples:
/merino wool - Price of Merino Wool
/merino wool 5 - Convert Merino Wool
/usd 1.2345 - Value of Flower
/flower 10.5678 - Value of USD
/calc (5+3)*2 - Calculate expression
/land 123 - Farm details
/oil - Price of Oil (calculated from drill components)
/oil 100 - Convert Oil to Flower/USD

💝 Donate to support development:
{DONATION_ADDRESS}

📦 Available items:
{items_list}
"""
            await self.send_message(update, welcome_msg)
            await self.send_advertisement(update)
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

🌾 Farm Command:
/land <number> - Show farm details
Example: /land 123

🛢 Oil Calculation:
Oil price is calculated based on drill components:
- 3 Oil Drills required (60 Wood + 27 Iron + 30 Leather)
- Production: 10, 10, 30 Oil (total 50)
- Price per Oil = Total drill cost / 50

💡 Examples:
/stone - Unit price
/stone 20 - Conversion
/usd 5.5 - Value in USD
/flower 10.5 - Value in Flower
/oil - Price of Oil
/oil 500 - Convert Oil
"""
        await self.send_message(update, help_msg)
        await self.send_advertisement(update)

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
            await self.send_advertisement(update)
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
            await self.send_advertisement(update)
        except Exception as e:
            self.error_stats['other'] += 1
            await self.send_message(update, "❌ Error processing calculation")

    async def handle_land(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.command_count += 1
        try:
            if not context.args:
                await self.send_message(update, "ℹ️ Please specify a farm ID. Example: /land 123")
                return

            land_id_str = context.args[0].strip()
            try:
                land_id = int(land_id_str)
                if land_id <= 0:
                    raise ValueError("ID must be positive")
            except ValueError:
                self.error_stats['input'] += 1
                await self.send_message(update, "⚠️ Invalid ID. Must be a positive integer.")
                return

            # Get data from API
            data = await self.get_land_data(land_id)
            
            # Process land data
            land_info = data.get('land', {})
            bumpkin_info = data.get('bumpkin', {})
            
            if not land_info:
                await self.send_message(update, f"❌ Farm ID {land_id} not found")
                return

            # Format land information
            land_type = land_info.get('type', 'unknown').capitalize()
            land_level = land_info.get('level', 0)
            land_coins = Decimal(str(land_info.get('coins', 0)))
            land_balance = Decimal(str(land_info.get('balance', 0)))
            
            # Format Bumpkin information
            bumpkin_level = bumpkin_info.get('level', 0)
            bumpkin_exp = Decimal(str(bumpkin_info.get('experience', 0)))
            
            # Count skills
            skills = bumpkin_info.get('skills', {})
            total_skills = len(skills) if skills else 0
            
            # Build message
            message = (
                f"🌾 *Farm ID: {land_id}*\n"
                f"🏜 Type: {land_type}\n"
                f"📊 Expansion: {land_level}\n"
                f"💰 Coins: {self.format_decimal(land_coins)}\n"
                f"🌻 Flower Balance: {self.format_decimal(land_balance)}\n"
                f"\n"
                f"👤 *Bumpkin*\n"
                f"📊 Level: {bumpkin_level}\n"
                f"🌟 Experience: {self.format_decimal(bumpkin_exp)}\n"
                f"🎯 Skills: {total_skills}"
            )
            
            await self.send_message(update, message)
            await self.send_advertisement(update)

        except Exception as e:
            self.error_stats['api'] += 1
            error_msg = (
                f"❌ Error fetching farm data:\n"
                f"{str(e)[:100]}"
            )
            await self.send_message(update, error_msg)

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
