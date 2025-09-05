import re
from decimal import Decimal, InvalidOperation
from telegram import Update
from telegram.ext import ContextTypes
from .base_handler import BaseHandler

class Handlers(BaseHandler):
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
/compost - Compost production costs

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
/compost - Compost production costs

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

♻️ Compost Command:
/compost - Show compost production costs
Example: /compost

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
/compost - Compost production costs
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
            total_cost, unit_cost = await self.calculate_oil_production_cost()
            
            # Calcular precios para diferentes cantidades
            price_10 = unit_cost * Decimal('10')
            price_50 = unit_cost * Decimal('50')
            
            msg = (
                f"🛢 Oil Production Cost Analysis\n\n"
                f"📦 Resources for 3 drills (50 oil):\n"
                f"• 60 Wood: {self.format_decimal(total_wood_cost)} Flower\n"
                f"• 27 Iron: {self.format_decimal(total_iron_cost)} Flower\n"
                f"• 30 Leather: {self.format_decimal(total_leather_cost)} Flower\n"
                f"💸 Total cost: {self.format_decimal(total_cost)} Flower +300 coins\n\n"
                f"📊 Unit cost: {self.format_decimal(unit_cost)} Flower/oil\n\n"
                f"💡 Price for:\n"
                f"• 1 oil: {self.format_decimal(unit_cost)} Flower\n"
                f"• 10 oil: {self.format_decimal(price_10)} Flower\n"
                f"• 50 oil: {self.format_decimal(price_50)} Flower\n\n"
                f"Note: Based on current market prices\n"
                f"3 drills produce 50 oil (10+10+30)"
            )
            
            await self.send_message(update, msg)
            await self.send_advertisement(update)
            
        except ValueError as e:
            await self.send_message(update, f"❌ {str(e)}")
        except Exception as e:
            error_msg = (
                f"❌ Error calculating oil production cost:\n"
                f"{str(e)[:100]}"
            )
            await self.send_message(update, error_msg)

    async def handle_lavapit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.command_count += 1
        await self.update_user_stats(update.effective_user.id)
        try:
            # Calcular el costo de producción del petróleo usando el método centralizado
            total_oil_cost, oil_unit_cost = await self.calculate_oil_production_cost()

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

    async def handle_compost(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        self.command_count += 1
        await self.update_user_stats(update.effective_user.id)
        try:
            prices = await self.get_prices()
            
            # Definir requisitos de compost para cada composter y temporada
            composters = {
                "Compost Bin": {
                    "spring": {"rhubarb": 10, "carrot": 5},
                    "summer": {"zucchini": 10, "pepper": 2},
                    "autumn": {"yam": 15},
                    "winter": {"potato": 10, "cabbage": 3}
                },
                "Turbo Composter": {
                    "spring": {"soybean": 5, "corn": 3},
                    "summer": {"cauliflower": 4, "eggplant": 3},
                    "autumn": {"broccoli": 10, "artichoke": 2},
                    "winter": {"onion": 5, "turnip": 2}
                },
                "Premium Composter": {
                    "spring": {"blueberry": 8, "egg": 5},
                    "summer": {"banana": 3, "egg": 5},
                    "autumn": {"apple": 4, "tomato": 5},
                    "winter": {"lemon": 3, "apple": 3}
                }
            }

            msg = ["♻️ Compost Production Costs\n"]
            msg.append("💡 Based on current market prices\n")

            for composter, seasons in composters.items():
                msg.append(f"\n🏗 {composter}:")
                
                for season, requirements in seasons.items():
                    season_total = Decimal('0')
                    breakdown = []
                    
                    for item, quantity in requirements.items():
                        # Buscar el item en los precios (case-insensitive)
                        item_key = next(
                            (k for k in prices.keys() if k.replace(" ", "").lower() == item.replace(" ", "").lower()),
                            None
                        )
                        
                        if not item_key:
                            breakdown.append(f"❌ {item}: Not found")
                            continue
                        
                        item_price = prices[item_key]
                        item_total = quantity * item_price
                        season_total += item_total
                        breakdown.append(
                            f"  • {item_key.capitalize()} x{quantity}: "
                            f"{self.format_decimal(item_total)} Flower"
                        )
                    
                    msg.append(f"\n  🍂 {season.capitalize()}:")
                    msg.extend(breakdown)
                    msg.append(f"  💰 Total: {self.format_decimal(season_total)} Flower")

            await self.send_message(update, "\n".join(msg))
            await self.send_advertisement(update)
            
        except Exception as e:
            self.error_stats['calculation'] += 1
            error_msg = f"❌ Error calculating compost costs: {str(e)[:100]}"
            await self.send_message(update, error_msg)

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
