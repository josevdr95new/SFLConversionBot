import logging
from aiohttp import web
from datetime import datetime
from .config import configure_logging

logger = configure_logging()

async def handle_ping(request: web.Request) -> web.Response:
    try:
        bot = request.app.get('bot')
        if not bot:
            return web.Response(
                text="🏓 pong\nBot status: operational (no bot instance)",
                status=200
            )

        status_info = ["🏓 Estado del Bot"]
        
        # Tiempo de actividad
        if hasattr(bot, 'start_time'):
            uptime = datetime.now() - bot.start_time
            status_info.append(f"⏱ Uptime: {str(uptime).split('.')[0]}")

        # Estado de la caché
        cache_info = []
        now = datetime.now()
        
        try:
            # Caché de precios
            prices_expiry = getattr(bot, "_get_prices_expiry", None)
            prices_ttl = (prices_expiry - now).total_seconds() if prices_expiry else 0
            prices_status = "🟢 ACTIVA" if prices_ttl > 0 else "🔴 INACTIVA"
            cache_info.append(f"📊 Precios: {prices_status} (TTL: {max(0, int(prices_ttl))}s)")
            
            # Caché de exchange
            exchange_expiry = getattr(bot, "_get_exchange_rates_expiry", None)
            exchange_ttl = (exchange_expiry - now).total_seconds() if exchange_expiry else 0
            exchange_status = "🟢 ACTIVA" if exchange_ttl > 0 else "🔴 INACTIVA"
            cache_info.append(f"💱 Exchange: {exchange_status} (TTL: {max(0, int(exchange_ttl))}s)")
            
            if cache_info:
                status_info.append("\n💾 Estado de la Caché:")
                status_info.extend(cache_info)
        except Exception as e:
            logger.warning(f"Error checking cache status: {e}")
            status_info.append("\n⚠️ No se pudo verificar el estado de la caché")

        # Estadísticas de comandos
        if hasattr(bot, 'command_count'):
            status_info.append(f"\n📈 Comandos procesados: {bot.command_count}")

        # Estadísticas de errores
        if hasattr(bot, 'error_stats'):
            error_stats = bot.error_stats
            total_errors = sum(error_stats.values())
            status_info.append(f"\n❌ Errores totales: {total_errors}")
            
            if total_errors > 0:
                status_info.append("\n🔍 Desglose de errores:")
                status_info.append(f"• API: {error_stats.get('api', 0)}")
                status_info.append(f"• Entrada: {error_stats.get('input', 0)}")
                status_info.append(f"• Cálculos: {error_stats.get('calculation', 0)}")
                status_info.append(f"• Caché: {error_stats.get('cache', 0)}")
                status_info.append(f"• Otros: {error_stats.get('other', 0)}")

        return web.Response(
            text="\n".join(status_info),
            content_type='text/plain',
            status=200
        )

    except Exception as e:
        logger.error(f"Error en ping endpoint: {str(e)}", exc_info=True)
        return web.Response(
            text="🏓 pong\n⚠️ Error obteniendo estado completo del bot",
            status=500
        )

async def start_web_server(bot, port: int = 8000) -> tuple[web.AppRunner, web.TCPSite]:
    app = web.Application()
    if bot:
        app['bot'] = bot
    
    app.router.add_get('/ping', handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(
        runner,
        host='0.0.0.0',
        port=port
    )
    
    await site.start()
    logger.info(f"✅ Servidor web iniciado en puerto {port}")
    
    return runner, site