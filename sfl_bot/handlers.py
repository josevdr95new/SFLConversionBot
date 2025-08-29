import re
import asyncio
from decimal import Decimal, InvalidOperation, DecimalException
from typing import Optional
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
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
        self.advertisement_shown = {}
        self.unique_users = set()
        self.daily_users = set()
        self.last_reset = datetime.now().date()
        
        # Definir la botonera
        self.keyboard = [
            ["📊 Prices", "🛢 Oil Cost", "🌋 Lava Pit"],
            ["🧮 Calculator", "🌾 Farm Info", "📈 Status"],
            ["💵 USD to SFL", "🌻 SFL to USD", "❤️ Donate"],
            ["🆘 Help", "🚀 Start"]
        ]
        self.reply_markup = ReplyKeyboardMarkup(self.keyboard, resize_keyboard=True)

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

    async def send_message(self, update: Update, text: str, use_keyboard=True) -> None:
        try:
            # Escapar automáticamente todo el texto Markdown
            escaped_text = escape_markdown(text)
            reply_markup = self.reply_markup if use_keyboard else ReplyKeyboardRemove()
            await update.message.reply_text(
                escaped_text,
                parse_mode="MarkdownV2",
                disable_web_page_preview=True,
                reply_markup=reply_markup
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
                disable_web_page_preview=True,
                reply_markup=self.reply_markup
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
                disable_web_page_preview=True,
                reply_markup=self.reply_markup
            )
        except Exception as e:
            import logging
            logging.error(f"Error sending advertisement: {e}")

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.command_count += 1
        await self.update_user_stats(update.effective_user.id)
        try:
            prices = await self.get_prices()
            items_list = ", ".join(sorted(prices.keys()))
            
            welcome_msg = f"""
🌟 SFL Conversion Bot v{BOT_VERSION} 🌟

📌 Available commands:
/start - Show this message
/help - Detailed help
/prices - Show all resource prices
/donate - Show donation address
/<item> - Unit price
/<item> <amount> - Conversion with commission
/usd <amount> - Convert Flower to USD
/flower <amount> - Convert USD to Flower
/status - Show cache status and uptime
/calc <expression> - Mathematical calculator
/land <number> - Farm details
/oil - Oil production cost
/lavapit - Lava Pit seasonal production costs

🔹 Examples:
/merino wool - Price of Merino Wool
/merino wool 5 - Convert Merino Wool
/prices - Show all prices
/usd 1.2345 - Value of Flower
/flower 10.5678 - Value of USD
/status - System status
/calc (5+3)*2 - Calculate expression
/land 123 - Farm details
/oil - Oil production cost
/lavapit - Lava Pit seasonal production costs

💡 Suggestions? Contact: @codecode001

📦 Available items:
{items_list}
"""
            await self.send_message(update, welcome_msg)
            # Forzar mostrar publicidad inmediatamente después del start
            await self.send_advertisement(update, force=True)
        except Exception as e:
            self.error_stats['other'] += 1
            await self.send_message(update, "❌ Error showing available items")

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.command_count += 1
        await self.update_user_stats(update.effective_user.id)
        help_msg = f"""
🛠 Complete Help v{BOT_VERSION}

📝 Syntax:
- Items: Case-insensitive, spaces allowed
- Amounts: Numbers with up to 8 decimals

📊 Prices Command:
/prices - Show all resource prices
Example: /prices

💰 Donate Command:
/donate - Show donation address
Example: /donate

🧮 Calculator Command:
/calc <expression> - Basic math operations
Example: /calc (5+3)*2

🌾 Farm Command:
/land <number> - Show farm details
Example: /land 123

🛢 Oil Command:
/oil - Show oil production cost
Example: /oil

🌋 Lava Pit Command:
/lavapit - Show Lava Pit seasonal production costs
Example: /lavapit

📈 Status Command:
/status - Show cache status and uptime
Example: /status

💡 Examples:
/stone - Unit price
/stone 20 - Conversion
/prices - All prices
/usd 5.5 - Value in USD
/flower 10.5 - Value in Flower
/oil - Oil production cost
/lavapit - Lava Pit seasonal production costs
/status - System status

💡 Suggestions? Contact: @codecode001
"""
        await self.send_message(update, help_msg)
        await self.send_advertisement(update)

    async def handle_donate(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.command_count += 1
        await self.update_user_stats(update.effective_user.id)
        donate_msg = f"❤️ Donation Address:\n`{DONATION_ADDRESS}`"
        await self.send_message(update, donate_msg)
        # No mostrar publicidad en donación

    async def handle_prices(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.command_count += 1
        await self.update_user_stats(update.effective_user.id)
        try:
            prices = await self.get_prices()
            rates = await self.get_exchange_rates()
            flower_rate = rates.get("sfl", {}).get("usd", Decimal('0'))
            
            # Ordenar alfabéticamente
            sorted_items = sorted(prices.items(), key=lambda x: x[0])
            
            # Crear lista formateada: solo el precio en Flower, cada elemento en una línea
            price_list = []
            for item, price in sorted_items:
                price_list.append(f"{item}: {self.format_decimal(price)} Flower")
            
            # Añadir el precio de Flower (USD) al final
            price_list.append(f"\n💱 Exchange rate: 1 Flower ≈ ${self.format_decimal(flower_rate)}")
            
            msg = f"📊 All Resource Prices\n\n{chr(10).join(price_list)}"
            
            await self.send_message(update, msg)
            await self.send_advertisement(update)
            
        except Exception as e:
            self.error_stats['other'] += 1
            error_msg = f"❌ Error fetching prices: {str(e)[:100]}"
            await self.send_message(update, error_msg)

    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.command_count += 1
        await self.update_user_stats(update.effective_user.id)
        try:
            now = datetime.now()
            uptime = now - self.start_time
            days = uptime.days
            hours, remainder = divmod(uptime.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            prices_expiry = getattr(self, "_get_prices_expiry", None)
            exchange_expiry = getattr(self, "_get_exchange_rates_expiry", None)
            
            prices_ttl = (prices_expiry - now).seconds if prices_expiry else 0
            exchange_ttl = (exchange_expiry - now).seconds if exchange_expiry else 0
            
            status_msg = (
                f"🔄 System Status v{BOT_VERSION}\n\n"
                f"👥 Unique users today: {len(self.daily_users)}\n"
                f"👥 Total unique users: {len(self.unique_users)}\n"
                f"⏰ Uptime: {days}d {hours}h {minutes}m {seconds}s\n\n"
                f"📊 Prices cache:\n"
                f"{'✅ Valid' if prices_ttl > 0 else '❌ Expired'} "
                f"(TTL: {max(0, prices_ttl)}s)\n\n"
                f"💱 Exchange cache:\n"
                f"{'✅ Valid' if exchange_ttl > 0 else '❌ Expired'} "
                f"(TTL: {max(0, exchange_ttl)}s)"
            )
            
            await self.send_message(update, status_msg)
            await self.send_advertisement(update)
        except Exception as e:
            self.error_stats['cache'] += 1
            await self.send_message(update, "❌ Error checking system status")

    async def handle_oil(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.command_count += 1
        await self.update_user_stats(update.effective_user.id)
        try:
            prices = await self.get_prices()
            
            # Get required resource prices
            wood_price = prices.get("wood", Decimal('0'))
            iron_price = prices.get("iron", Decimal('0'))
            leather_price = prices.get("leather", Decimal('0'))
            
            if any(price == 0 for price in [wood_price, iron_price, leather_price]):
                self.error_stats['api'] += 1
                await self.send_message(update, "❌ Could not fetch all required resource prices")
                return
            
            # Calculate cost for 3 drills (produces 50 oil)
            # Each drill costs: 20 wood, 9 iron, 10 leather
            total_wood_cost = Decimal('60') * wood_price  # 3 drills * 20 wood
            total_iron_cost = Decimal('27') * iron_price  # 3 drills * 9 iron
            total_leather_cost = Decimal('30') * leather_price  # 3 drills * 10 leather
            
            total_cost = total_wood_cost + total_iron_cost + total_leather_cost
            
            # Calculate unit prices
            unit_price = total_cost / Decimal('50')
            price_10 = unit_price * Decimal('10')
            price_50 = unit_price * Decimal('50')
            
            msg = (
                f"🛢 Oil Production Cost Analysis\n\n"
                f"📦 Resources for 3 drills (50 oil):\n"
                f"• 60 Wood: {self.format_decimal(total_wood_cost)} Flower\n"
                f"• 27 Iron: {self.format_decimal(total_iron_cost)} Flower\n"
                f"• 30 Leather: {self.format_decimal(total_leather_cost)} Flower\n"
                f"💸 Total cost: {self.format_decimal(total_cost)} Flower +300 coins\n\n"
                f"📊 Unit cost: {self.format_decimal(unit_price)} Flower/oil\n\n"
                f"💡 Price for:\n"
                f"• 1 oil: {self.format_decimal(unit_price)} Flower\n"
                f"• 10 oil: {self.format_decimal(price_10)} Flower\n"
                f"• 50 oil: {self.format_decimal(price_50)} Flower\n\n"
                f"Note: Based on current market prices\n"
                f"3 drills produce 50 oil (10+10+30)"
            )
            
            await self.send_message(update, msg)
            await self.send_advertisement(update)
            
        except Exception as e:
            self.error_stats['calculation'] += 1
            error_msg = (
                f"❌ Error calculating oil production cost:\n"
                f"{str(e)[:100]}"
            )
            await self.send_message(update, error_msg)

    async def handle_lavapit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.command_count += 1
        await self.update_user_stats(update.effective_user.id)
        try:
            prices = await self.get_prices()
            
            # Calcular el costo de producción del petróleo (similar al comando /oil)
            wood_price = prices.get("wood", Decimal('0'))
            iron_price = prices.get("iron", Decimal('0'))
            leather_price = prices.get("leather", Decimal('0'))
            
            if any(price == 0 for price in [wood_price, iron_price, leather_price]):
                self.error_stats['api'] += 1
                await self.send_message(update, "❌ Could not fetch all required resource prices for oil calculation")
                return
            
            # Calcular costo de producción del petróleo (misma lógica que /oil)
            total_wood_cost = Decimal('60') * wood_price  # 3 drills * 20 wood
            total_iron_cost = Decimal('27') * iron_price  # 3 drills * 9 iron
            total_leather_cost = Decimal('30') * leather_price  # 3 drills * 10 leather
            total_oil_cost = total_wood_cost + total_iron_cost + total_leather_cost
            oil_unit_cost = total_oil_cost / Decimal('50')  # Costo por unidad de petróleo

            # Requisitos del Lava Pit por temporada
            seasons = {
                "autumn": {
                    "artichoke": 30,
                    "broccoli": 750,
                    "yam": 1000,
                    "gold": 5,
                    "crimstone": 4
                },
                "winter": {
                    "merino wool": 200,
                    "onion": 400,
                    "turnip": 200
                },
                "spring": {
                    "celestine": 2,
                    "lunara": 2,
                    "duskberry": 2,
                    "rhubarb": 2000,
                    "kale": 100
                },
                "summer": {
                    "oil": 100,  # Usaremos el costo de producción calculado
                    "pepper": 750,
                    "zucchini": 1000
                }
            }

            # Calcular costos para cada temporada
            season_costs = {}
            for season, requirements in seasons.items():
                season_total = Decimal('0')
                breakdown = []
                
                for item, quantity in requirements.items():
                    # Para el petróleo, usar el costo de producción en lugar del precio de mercado
                    if item == "oil":
                        item_total = oil_unit_cost * quantity
                        breakdown.append(
                            f"  • {item.capitalize()} x{quantity}: "
                            f"{self.format_decimal(item_total)} Flower (production cost)"
                        )
                    else:
                        # Para otros items, usar precios de mercado
                        item_key = next(
                            (k for k in prices.keys() if k.replace(" ", "").lower() == item.replace(" ", "").lower()),
                            None
                        )
                        
                        if not item_key:
                            breakdown.append(f"❌ {item}: Not found")
                            continue
                        
                        item_price = prices[item_key]
                        item_total = quantity * item_price
                        breakdown.append(
                            f"  • {item_key.capitalize()} x{quantity}: "
                            f"{self.format_decimal(item_total)} Flower"
                        )
                    
                    season_total += item_total
                
                season_costs[season] = {
                    "total": season_total,
                    "breakdown": breakdown
                }

            # Formatear mensaje
            msg = ["🌋 Lava Pit Production Cost by Season\n"]
            msg.append("💡 Oil uses production cost calculation, other items use market prices\n")
            
            for season, data in season_costs.items():
                msg.append(f"\n🍂 {season.capitalize()}:")
                msg.extend(data["breakdown"])
                msg.append(f"  💰 Total: {self.format_decimal(data['total'])} Flower")
            
            # Añadir total de todas las temporadas
            grand_total = sum(data["total"] for data in season_costs.values())
            msg.append(f"\n🌻 Grand Total (all seasons): {self.format_decimal(grand_total)} Flower")
            msg.append("\n📝 Note: Oil cost is based on production, not market price")

            await self.send_message(update, "\n".join(msg))
            await self.send_advertisement(update)
            
        except Exception as e:
            self.error_stats['calculation'] += 1
            error_msg = f"❌ Error calculating Lava Pit costs: {str(e)[:100]}"
            await self.send_message(update, error_msg)

    async def handle_usd_conversion(self, update: Update, amount: Decimal) -> None:
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

    async def handle_calc(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.command_count += 1
        await self.update_user_stats(update.effective_user.id)
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
        await self.update_user_stats(update.effective_user.id)
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
                f"🌾 -Farm ID: {land_id}-\n"
                f"🏜 Type: {land_type}\n"
                f"📊 Expansion: {land_level}\n"
                f"💰 Coins: {self.format_decimal(land_coins)}\n"
                f"🌻 Flower Balance: {self.format_decimal(land_balance)}\n"
                f"\n"
                f"👤 -Bumpkin-\n"
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

    async def handle_button_press(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Maneja las pulsaciones de botones del teclado personalizado"""
        text = update.message.text
        self.command_count += 1
        await self.update_user_stats(update.effective_user.id)
        
        if text == "📊 Prices":
            await self.handle_prices(update, context)
        elif text == "🛢 Oil Cost":
            await self.handle_oil(update, context)
        elif text == "🌋 Lava Pit":
            await self.handle_lavapit(update, context)
        elif text == "🧮 Calculator":
            await self.send_message(update, "🧮 Please type your calculation after /calc command\nExample: /calc (5+3)*2")
        elif text == "🌾 Farm Info":
            await self.send_message(update, "🌾 To get farm information, use /land followed by the farm ID\nExample: /land 123")
        elif text == "📈 Status":
            await self.handle_status(update, context)
        elif text == "💵 USD to SFL":
            await self.send_message(update, "💵 To convert USD to SFL, use /flower followed by the amount\nExample: /flower 10.50")
        elif text == "🌻 SFL to USD":
            await self.send_message(update, "🌻 To convert SFL to USD, use /usd followed by the amount\nExample: /usd 5.75")
        elif text == "❤️ Donate":
            await self.handle_donate(update, context)
        elif text == "🆘 Help":
            await self.handle_help(update, context)
        elif text == "🚀 Start":
            await self.handle_start(update, context)
        else:
            await self.handle_item(update, context)

    async def handle_item(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.command_count += 1
        await self.update_user_stats(update.effective_user.id)
        if not update.message or not update.message.text:
            return

        try:
            text = update.message.text.strip()
            if len(text) > MAX_INPUT_LENGTH:
                self.error_stats['input'] += 1
                await self.send_message(update, "⚠️ Input too long. Please shorten your request.")
                return

            # Check if it's a button press first
            if text in ["📊 Prices", "🛢 Oil Cost", "🌋 Lava Pit", "🧮 Calculator", 
                       "🌾 Farm Info", "📈 Status", "💵 USD to SFL", "🌻 SFL to USD", 
                       "❤️ Donate", "🆘 Help", "🚀 Start"]:
                await self.handle_button_press(update, context)
                return

            match = re.match(r"^\/(.+?)(?:\s+([\d\.]{1,20}))?$", text, re.IGNORECASE)
            
            if not match:
                self.error_stats['input'] += 1
                await self.send_message(update, "⚠️ Invalid format. Use /help or tap a button below.")
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
