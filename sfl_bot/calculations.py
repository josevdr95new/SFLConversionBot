from decimal import Decimal
from typing import Dict, Any
from .services import PriceBot

class Calculations(PriceBot):
    def __init__(self):
        super().__init__()
    
    async def calculate_oil_cost(self, resource_type: str = "leather") -> Dict[str, Any]:
        """Calculate oil production cost based on resource type (leather or wool)"""
        prices = await self.get_prices()
        
        # Get required resource prices
        wood_price = prices.get("wood", Decimal('0'))
        iron_price = prices.get('iron', Decimal('0'))
        
        if resource_type == "leather":
            resource_price = prices.get('leather', Decimal('0'))
            resource_name = "Leather"
            resource_per_drill = Decimal('10')
            total_resource = Decimal('30')  # 3 drills * 10 leather
        else:  # wool
            resource_price = prices.get('wool', Decimal('0'))
            resource_name = "Wool"
            resource_per_drill = Decimal('20')
            total_resource = Decimal('60')  # 3 drills * 20 wool
        
        if any(price == 0 for price in [wood_price, iron_price, resource_price]):
            raise Exception("Could not fetch all required resource prices")
        
        # Calculate cost for 3 drills (produces 50 oil)
        total_wood_cost = Decimal('60') * wood_price  # 3 drills * 20 wood
        total_iron_cost = Decimal('27') * iron_price  # 3 drills * 9 iron
        total_resource_cost = total_resource * resource_price
        
        total_cost = total_wood_cost + total_iron_cost + total_resource_cost
        
        # Calculate unit prices
        unit_price = total_cost / Decimal('50')
        price_10 = unit_price * Decimal('10')
        price_50 = unit_price * Decimal('50')
        
        return {
            "resource_type": resource_type,
            "resource_name": resource_name,
            "total_resource": total_resource,
            "total_wood_cost": total_wood_cost,
            "total_iron_cost": total_iron_cost,
            "total_resource_cost": total_resource_cost,
            "total_cost": total_cost,
            "unit_price": unit_price,
            "price_10": price_10,
            "price_50": price_50
        }

    async def calculate_lavapit_costs(self, oil_unit_cost: Decimal, resource_type: str = "leather") -> Dict[str, Any]:
        """Calculate Lava Pit seasonal production costs"""
        prices = await self.get_prices()
        
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
                        f"  • {item.capitalize()} x{quantity} ({resource_type}): "
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

        return season_costs

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
