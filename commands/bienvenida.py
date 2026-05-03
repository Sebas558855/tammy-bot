import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import logging

logger = logging.getLogger('TammyBot.Bienvenida')

# ==============================================================
#   🖼️  CONFIGURACIÓN DE IMÁGENES / GIFs
#
#   Cambia las URLs de abajo por las tuyas.
#   Puedes usar:
#     - Un enlace directo a una imagen (termina en .png / .jpg / .gif)
#     - Un enlace de Tenor o Giphy (copia el enlace "directo" del GIF)
#     - Déjalo como None para no mostrar imagen
#
#   Ejemplos de cómo conseguir la URL:
#     · Sube la imagen a Discord, cópiala con clic derecho → "Copiar enlace de imagen"
#     · En Tenor: abre el GIF → clic derecho → "Copiar dirección de imagen"
#     · En Imgur: abre la imagen → copia la URL que termina en .gif o .png
# ==============================================================

BIENVENIDA_IMAGEN_URL: str | None = (
    None
    # Ejemplos:
    # "https://media.tenor.com/tu-gif-de-bienvenida.gif"
    # "https://i.imgur.com/tu-imagen.png"
    # "https://cdn.discordapp.com/attachments/.../bienvenida.gif"
)

DESPEDIDA_IMAGEN_URL: str | None = (
    None
    # Ejemplos:
    # "https://media.tenor.com/tu-gif-de-despedida.gif"
    # "https://i.imgur.com/tu-imagen-despedida.png"
)

# ==============================================================
#   📝  MENSAJES PERSONALIZABLES
#
#   Placeholders disponibles (se reemplazan automáticamente):
#     {usuario}    → Nombre de usuario (sin #0000)
#     {mencion}    → Mención clickeable (@Usuario)
#     {servidor}   → Nombre del servidor
#     {miembros}   → Número total de miembros
# ==============================================================

BIENVENIDA_TITULO   = "👋 ¡Nuevo miembro!"
BIENVENIDA_MENSAJE  = "¡Bienvenido/a a **{servidor}**, {mencion}! 🎉\nEres el miembro número **{miembros}**.\nVerifícate en ✅-verificacion para acceder a todos los canales."
BIENVENIDA_COLOR    = discord.Color.green()

DESPEDIDA_TITULO    = "👋 Un miembro se fue..."
DESPEDIDA_MENSAJE   = "**{usuario}** ha abandonado **{servidor}**.\nEsperamos verte de vuelta pronto. 💙"
DESPEDIDA_COLOR     = discord.Color.red()

# ==============================================================
#   📺  CANALES (nombres exactos de tus canales)
# ==============================================================

CANAL_BIENVENIDA = "👋-bienvenida"
CANAL_DESPEDIDA  = "👋-despedida"


# ==============================================================
#   COG PRINCIPAL
# ==============================================================

class Bienvenida(commands.Cog):
    """Sistema de bienvenida y despedida automática."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _build_embed(
        self,
        titulo: str,
        mensaje: str,
        color: discord.Color,
        imagen_url: str | None,
        member: discord.Member
    ) -> discord.Embed:
        """Construye el embed de bienvenida o despedida."""

        texto = mensaje.format(
            usuario=member.display_name,
            mencion=member.mention,
            servidor=member.guild.name,
            miembros=member.guild.member_count
        )

        embed = discord.Embed(
            title=titulo,
            description=texto,
            color=color,
            timestamp=datetime.now()
        )

        # Avatar del usuario como thumbnail (esquina superior derecha)
        embed.set_thumbnail(url=member.display_avatar.url)

        # ==============================================================
        #   🖼️  AQUÍ SE AGREGA LA IMAGEN / GIF AL EMBED
        #
        #   set_image()  → imagen grande abajo del texto
        #   set_thumbnail() → imagen pequeña arriba a la derecha (avatar)
        #
        #   Si quieres poner el GIF en lugar del avatar como thumbnail:
        #     embed.set_thumbnail(url=imagen_url)
        #
        #   Si quieres el GIF grande debajo del texto (recomendado):
        #     embed.set_image(url=imagen_url)   ← ya está abajo ↓
        # ==============================================================
        if imagen_url:
            embed.set_image(url=imagen_url)  # 👈 GIF/imagen grande debajo del texto

        embed.set_footer(text=f"ID: {member.id}")
        return embed

    # ──────────────────────────────────────────
    #  EVENTOS
    # ──────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Se dispara cuando alguien entra al servidor."""

        canal = discord.utils.get(member.guild.text_channels, name=CANAL_BIENVENIDA)
        if not canal:
            logger.warning(f"Canal '{CANAL_BIENVENIDA}' no encontrado en {member.guild.name}")
            return

        embed = self._build_embed(
            titulo=BIENVENIDA_TITULO,
            mensaje=BIENVENIDA_MENSAJE,
            color=BIENVENIDA_COLOR,
            imagen_url=BIENVENIDA_IMAGEN_URL,
            member=member
        )

        try:
            await canal.send(embed=embed)
            logger.info(f"Bienvenida enviada para {member} en {member.guild.name}")
        except discord.Forbidden:
            logger.error(f"Sin permisos para enviar en #{CANAL_BIENVENIDA}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Se dispara cuando alguien sale del servidor."""

        canal = discord.utils.get(member.guild.text_channels, name=CANAL_DESPEDIDA)
        if not canal:
            logger.warning(f"Canal '{CANAL_DESPEDIDA}' no encontrado en {member.guild.name}")
            return

        embed = self._build_embed(
            titulo=DESPEDIDA_TITULO,
            mensaje=DESPEDIDA_MENSAJE,
            color=DESPEDIDA_COLOR,
            imagen_url=DESPEDIDA_IMAGEN_URL,
            member=member
        )

        try:
            await canal.send(embed=embed)
            logger.info(f"Despedida enviada para {member} en {member.guild.name}")
        except discord.Forbidden:
            logger.error(f"Sin permisos para enviar en #{CANAL_DESPEDIDA}")

    # ──────────────────────────────────────────
    #  COMANDOS DE PRUEBA (solo admins)
    # ──────────────────────────────────────────

    @app_commands.command(name="test_bienvenida", description="🧪 Prueba el mensaje de bienvenida (Admin)")
    @app_commands.default_permissions(administrator=True)
    async def test_bienvenida(self, interaction: discord.Interaction):
        """Simula una bienvenida con tu propio perfil para ver cómo queda."""
        canal = discord.utils.get(interaction.guild.text_channels, name=CANAL_BIENVENIDA)
        if not canal:
            await interaction.response.send_message(
                f"❌ Canal `{CANAL_BIENVENIDA}` no encontrado.", ephemeral=True
            )
            return

        embed = self._build_embed(
            titulo=BIENVENIDA_TITULO,
            mensaje=BIENVENIDA_MENSAJE,
            color=BIENVENIDA_COLOR,
            imagen_url=BIENVENIDA_IMAGEN_URL,
            member=interaction.user
        )
        await canal.send(embed=embed)
        await interaction.response.send_message(
            f"✅ Mensaje de prueba enviado a {canal.mention}", ephemeral=True
        )

    @app_commands.command(name="test_despedida", description="🧪 Prueba el mensaje de despedida (Admin)")
    @app_commands.default_permissions(administrator=True)
    async def test_despedida(self, interaction: discord.Interaction):
        """Simula una despedida con tu propio perfil para ver cómo queda."""
        canal = discord.utils.get(interaction.guild.text_channels, name=CANAL_DESPEDIDA)
        if not canal:
            await interaction.response.send_message(
                f"❌ Canal `{CANAL_DESPEDIDA}` no encontrado.", ephemeral=True
            )
            return

        embed = self._build_embed(
            titulo=DESPEDIDA_TITULO,
            mensaje=DESPEDIDA_MENSAJE,
            color=DESPEDIDA_COLOR,
            imagen_url=DESPEDIDA_IMAGEN_URL,
            member=interaction.user
        )
        await canal.send(embed=embed)
        await interaction.response.send_message(
            f"✅ Mensaje de prueba enviado a {canal.mention}", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Bienvenida(bot))
