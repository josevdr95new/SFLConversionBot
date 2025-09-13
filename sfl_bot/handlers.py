import re
import asyncio
from decimal import Decimal, InvalidOperation, DecimalException
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes, CallbackContext
from httpx import HTTPStatusError
from .config import MAX_INPUT_LENGTH, MARKET_FEE, BOT_VERSION, DONATION_ADDRESS
from .services import PriceBot
from .calculations import Calculations
from datetime import datetime

def escape_markdown(text: str) -> str:
    """Escapa todos los caracteres reservados de MarkdownV2"""
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return ''.join(['\\' + char if char in escape_chars else char for char in text])

class Handlers(PriceBot, Calculations):
    def __init__(self):
        PriceBot.__init__(self)
        Calculations.__init__(self)
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
        # Nuevo: Almacenar la elección de recurso para oil
        self.oil_resource_choice = {}  # {chat_id: 'leather' or 'wool'}

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
/flower 10.5678 - Value in USD
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
/oil leather - Use leather for oil production
/oil wool - Use wool for oil production

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
        donate_msg = DONATION_ADDRESS  # Solo la dirección sin texto adicional
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
            # Get resource choice from command or use default (leather)
            resource_choice = "leather"  # default
            if context.args and len(context.args) > 0:
                arg = context.args[0].lower()
                if arg in ["leather", "wool"]:
                    resource_choice = arg
            
            # Store the choice for this chat
            chat_id = update.message.chat_id
            self.oil_resource_choice[chat_id] = resource_choice
            
            # Calculate oil cost
            oil_data = await self.calculate_oil_cost(resource_choice)
            
            msg = (
                f"🛢 Oil Production Cost Analysis ({oil_data['resource_name']})\n\n"
                f"📦 Resources for 3 drills (50 oil):\n"
                f"• 60 Wood: {self.format_decimal(oil_data['total_wood_cost'])} Flower\n"
                f"• 27 Iron: {self.format_decimal(oil_data['total_iron_cost'])} Flower\n"
                f"• {oil_data['total_resource']} {oil_data['resource_name']}: "
                f"{self.format_decimal(oil_data['total_resource_cost'])} Flower\n"
                f"💸 Total cost: {self.format_decimal(oil_data['total_cost'])} Flower +300 coins\n\n"
                f"📊 Unit cost: {self.format_decimal(oil_data['unit_price'])} Flower/oil\n\n"
                f"💡 Price for:\n"
                f"• 1 oil: {self.format_decimal(oil_data['unit_price'])} Flower\n"
                f"• 10 oil: {self.format_decimal(oil_data['price_10'])} Flower\n"
                f"• 50 oil: {self.format_decimal(oil_data['price_50'])} Flower\n\n"
                f"Note: Based on current market prices\n"
                f"3 drills produce 50 oil (10+10+30)\n"
                f"Use /oil leather or /oil wool to change resource type"
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
            # Get the oil resource choice for this chat, default to leather
            chat_id = update.message.chat_id
            resource_choice = self.oil_resource_choice.get(chat_id, "leather")
            
            # Calculate the oil production cost
            oil_data = await self.calculate_oil_cost(resource_choice)
            oil_unit_cost = oil_data['unit_price']

            # Calculate Lava Pit costs
            season_costs = await self.calculate_lavapit_costs(oil_unit_cost, resource_choice)

            # Formatear mensaje
            msg = ["🌋 Lava Pit Production Cost by Season\n"]
            msg.append(f"💡 Oil uses {resource_choice} production cost, other items use market prices\n")
            msg.append(f"Use /oil leather or /oil wool to change oil resource type\n")
            
            for season, data in season_costs.items():
                msg.append(f"\n🍂 {season.capitalize()}:")
                msg.extend(data["breakdown"])
                msg.append(f"  💰 Total: {self.format_decimal(data['total'])} Flower")
            
            # Añadir total de todas las temporadas
            grand_total = sum(data["total"] for data in season_costs.values())
            msg.append(f"\n🌻 Grand Total (all seasons): {self.format_decimal(grand_total)} Flower")
            msg.append(f"\n📝 Note: Oil cost is based on {resource_choice} production, not market price")

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

    async def handle_item_conversion(self, update: Update, item_name: str, amount: Optional[Decimal]) -> None:
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
            
            # New fields from API
            gem = land_info.get('gem', 0)
            marks = land_info.get('marks', 0)
            charm = land_info.get('charm', 0)
            cheer = land_info.get('cheer', 0)
            verified = "✅" if land_info.get('verified') else "❌"
            ban_status = land_info.get('ban', {}).get('status', 'unknown')
            is_social_verified = "✅" if land_info.get('ban', {}).get('isSocialVerified') else "❌"
            vip = "✅" if land_info.get('vip') else "❌"
            
            # VIP info details
            vip_info = land_info.get('vip_info', {})
            vip_details = []
            if vip_info and vip_info.get('have'):
                vip_details.append("Active")
                if vip_info.get('lifetime'):
                    vip_details.append("Lifetime")
                if vip_info.get('have_game'):
                    vip_details.append("Game")
                if vip_info.get('have_ronin'):
                    vip_details.append("Ronin")
                vip_details.append(f"Exp: {vip_info.get('exp_text', 'unknown')}")
            
            tax_free_sfl = Decimal(str(land_info.get('taxFreeSFL', 0)))
            tax_resource = Decimal(str(land_info.get('taxResource', 0))) * 100
            legacy = ", ".join(land_info.get('legacy', []))
            created = land_info.get('created', 'unknown')
            
            # Referrals info - Manejar tanto diccionario como entero
            referrals = land_info.get('referrals', {})
            total_referrals = 0
            total_vip_referrals = 0
            
            if isinstance(referrals, dict):
                total_referrals = referrals.get('totalReferrals', 0)
                total_vip_referrals = referrals.get('totalVIPReferrals', 0)
            elif isinstance(referrals, int):
                total_referrals = referrals
                total_vip_referrals = 0
            
            # Format Bumpkin information
            bumpkin_level = bumpkin_info.get('level', 0) if bumpkin_info else 0
            bumpkin_exp = Decimal(str(bumpkin_info.get('experience', 0))) if bumpkin_info else Decimal('0')
            
            # Count skills
            skills = bumpkin_info.get('skills', {}) if bumpkin_info else {}
            total_skills = len(skills) if skills else 0
            
            # Build message - Corregido el problema con la f-string
            vip_details_text = f" ({' '.join(vip_details)})" if vip_details else ""
            message = (
                f"🌾 Farm ID: {land_id}\n"
                f"🏜 Type: {land_type} | 📊 Expansion: {land_level}\n"
                f"💰 Coins: {self.format_decimal(land_coins)} | 🌻 Flower Balance: {self.format_decimal(land_balance)}\n"
                f"💎 Gems: {gem} | 🎖 Marks: {marks}\n"
                f"✨ Charm: {charm} | 🎉 Cheer: {cheer}\n"
                f"✅ Verified: {verified} | 👑 VIP: {vip}{vip_details_text}\n"
                f"📉 Tax Free SFL: {self.format_decimal(tax_free_sfl)} | 📈 Tax Resource: {self.format_decimal(tax_resource)}%\n"
                f"🏆 Legacy: {legacy if legacy else 'None'}\n"
                f"🗓 Created: {created}\n"
                f"👥 Referrals: {total_referrals} (VIP: {total_vip_referrals})\n"
                f"🔒 Ban Status: {ban_status} | Social Verified: {is_social_verified}\n\n"
                f"👤 Bumpkin\n"
                f"📊 Level: {bumpkin_level} | 🌟 Experience: {self.format_decimal(bumpkin_exp)}\n"
                f"🎯 Total Skills: {total_skills}"
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
        await self.update_user_stats(update.effective_user.id)
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
