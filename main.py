import discord
from discord.ext import commands
import os
import asyncio
import logging
from dotenv import load_dotenv
from contenido import TikTokNotifier

# ==================== CONFIGURACIÓN DE LOGGING ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('TammyBot')

# Cargar variables de entorno
load_dotenv()

# ==================== CONFIGURAR INTENTS ====================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

# ==================== CLASE PRINCIPAL DEL BOT ====================
class TammyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix='/',
            intents=intents,
            help_command=None,  # Desactivar el help por defecto
            case_insensitive=True
        )

    async def setup_hook(self):
        """Se ejecuta antes de que el bot se conecte — carga los cogs aquí."""
        await self.cargar_cogs()

    async def cargar_cogs(self):
        """Carga todos los cogs desde la carpeta commands/"""
        commands_dir = './commands'
        if not os.path.exists(commands_dir):
            os.makedirs(commands_dir)
            logger.warning('📁 Carpeta "commands" creada (estaba vacía)')
            return

        cogs_cargados = 0
        cogs_fallidos = 0

        for filename in sorted(os.listdir(commands_dir)):
            if filename.endswith('.py') and not filename.startswith('_'):
                cog_name = f'commands.{filename[:-3]}'
                try:
                    await self.load_extension(cog_name)
                    logger.info(f'✅ Cog cargado: {filename}')
                    cogs_cargados += 1
                except Exception as e:
                    logger.error(f'❌ Error cargando {filename}: {e}')
                    cogs_fallidos += 1

        logger.info(f'📦 Cogs: {cogs_cargados} cargados, {cogs_fallidos} fallidos')

    async def on_ready(self):
        logger.info(f'✅ Bot conectado como {self.user} (ID: {self.user.id})')
        logger.info(f'🌐 Servidores conectados: {len(self.guilds)}')

        # Sincronizar comandos slash
        try:
            synced = await self.tree.sync()
            logger.info(f'🔧 {len(synced)} comandos slash sincronizados')
            for cmd in synced:
                logger.info(f'   /{cmd.name}')
        except Exception as e:
            logger.error(f'❌ Error sincronizando comandos slash: {e}')

        # Establecer el estado del bot
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f'{len(self.guilds)} servidor(es) | /help'
            ),
            status=discord.Status.online
        )
                # ── Notificador de TikTok ──
        canal_live = int(os.getenv('TIKTOK_LIVE_CHANNEL_ID'))
        canal_videos = int(os.getenv('TIKTOK_VIDEO_CHANNEL_ID'))
        usuario_tiktok = os.getenv('TIKTOK_USERNAME')
        self.notifier = TikTokNotifier(self, canal_live, canal_videos, usuario_tiktok)
        await self.notifier.start()

    async def on_command_error(self, ctx, error):
        """Manejo global de errores de comandos de prefijo."""
        if isinstance(error, commands.CommandNotFound):
            return
        logger.error(f'Error en comando: {error}')

    async def on_guild_join(self, guild):
        logger.info(f'📥 Bot añadido al servidor: {guild.name} ({guild.id})')

    async def on_guild_remove(self, guild):
        logger.info(f'📤 Bot eliminado del servidor: {guild.name} ({guild.id})')


# ==================== COMANDO GLOBAL DE PING ====================
bot = TammyBot()

@bot.tree.command(name="ping", description="🏓 Verifica la latencia del bot")
async def ping(interaction: discord.Interaction):
    latencia = round(bot.latency * 1000)
    color = discord.Color.green() if latencia < 100 else discord.Color.orange() if latencia < 200 else discord.Color.red()
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latencia del bot: **{latencia}ms**",
        color=color
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="help", description="📋 Muestra todos los comandos disponibles")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📋 COMANDOS DE TAMMYBOT",
        color=discord.Color.blue()
    )
    embed.add_field(name="🛠️ Admin", value="`/clear` `/mute` `/unmute` `/kick` `/ban` `/unban` `/warn` `/warnings` `/clearwarns` `/slowmode` `/lock` `/unlock` `/userinfo` `/serverinfo` `/voice_mute` `/voice_unmute`", inline=False)
    embed.add_field(name="🤖 AutoMod", value="`/automod` `/automod_filter` `/automod_threshold` `/automod_action` `/automod_ignore` `/automod_stats` `/automod_reset` `/automod_whitelist`", inline=False)
    embed.add_field(name="🎫 Tickets", value="`/ticket_setup` `/ticket_stats` `/ticket_close`", inline=False)
    embed.add_field(name="✅ Verificación", value="`/verificar` `/reset_verificacion` `/stats_verificacion`", inline=False)
    embed.add_field(name="🤖 Tammy IA", value="`/tammy` `/tammy_reset` `/tammy_status` `/tammy_config`", inline=False)
    embed.add_field(name="⚙️ Setup", value="`/setup_servidor`", inline=False)
    embed.set_footer(text="TammyBot • Todos los derechos reservados")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ==================== EJECUTAR EL BOT ====================
if __name__ == "__main__":
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        logger.critical("❌ No se encontró DISCORD_TOKEN en el archivo .env")
        logger.critical("📝 Crea un archivo .env con: DISCORD_TOKEN=tu_token_aqui")
        exit(1)

    try:
        bot.run(TOKEN, log_handler=None)  # log_handler=None para usar nuestro logger
    except discord.LoginFailure:
        logger.critical("❌ Token inválido. Verifica tu DISCORD_TOKEN en el archivo .env")
    except KeyboardInterrupt:
        logger.info("🛑 Bot detenido manualmente")
    except Exception as e:
        logger.critical(f"❌ Error fatal al iniciar: {e}")
