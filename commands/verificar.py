import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
import string
import logging
from datetime import datetime, timedelta

logger = logging.getLogger('TammyBot.Verificar')

VERIFIED_ROLE_NAME = "✅ Verificado"


def generate_captcha(length: int = 6) -> str:
    """Genera un código alfanumérico aleatorio."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


class VerifyModal(discord.ui.Modal, title="🔐 Verificación de Seguridad"):
    """Modal (ventana emergente) para ingresar el código CAPTCHA."""

    codigo = discord.ui.TextInput(
        label="Ingresa el código exactamente como aparece",
        placeholder="Ej: A3B9XZ",
        min_length=6,
        max_length=6,
        required=True
    )

    def __init__(self, expected_code: str, verified_role: discord.Role):
        super().__init__()
        self.expected_code = expected_code
        self.verified_role = verified_role

    async def on_submit(self, interaction: discord.Interaction):
        entered = self.codigo.value.strip().upper()

        if entered == self.expected_code:
            try:
                await interaction.user.add_roles(self.verified_role, reason="Verificación CAPTCHA exitosa")

                embed = discord.Embed(
                    title="✅ VERIFICACIÓN EXITOSA",
                    description=f"¡Bienvenido/a a **{interaction.guild.name}**! 🎉\nYa tienes acceso a todos los canales.",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="🚀 ¿Qué hacer ahora?",
                    value="• Lee las reglas del servidor\n• Preséntate en el chat\n• ¡Disfruta la comunidad!",
                    inline=False
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

                # Log
                logs = discord.utils.get(interaction.guild.text_channels, name="📜-logs")
                if logs:
                    await logs.send(f"✅ **{interaction.user}** (`{interaction.user.id}`) verificado correctamente.")

                logger.info(f"Usuario verificado: {interaction.user} ({interaction.user.id})")

            except discord.Forbidden:
                await interaction.response.send_message(
                    "❌ No tengo permisos para darte el rol. Contacta a un administrador.", ephemeral=True
                )
        else:
            embed = discord.Embed(
                title="❌ CÓDIGO INCORRECTO",
                description="El código ingresado no coincide.\nUsa `/verificar` nuevamente para intentarlo.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logger.error(f"Error en VerifyModal: {error}")
        await interaction.response.send_message("❌ Ocurrió un error. Intenta de nuevo.", ephemeral=True)


class VerifyView(discord.ui.View):
    """Vista con botón para ingresar el código CAPTCHA."""

    def __init__(self, code: str, verified_role: discord.Role):
        super().__init__(timeout=60)
        self.code = code
        self.verified_role = verified_role

    @discord.ui.button(label="✍️ Ingresar Código", style=discord.ButtonStyle.primary)
    async def ingresar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(VerifyModal(self.code, self.verified_role))
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class Verificar(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="verificar", description="✅ Verifica tu cuenta en el servidor")
    async def verificar(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user

        # Verificar que el rol existe
        verified_role = discord.utils.get(guild.roles, name=VERIFIED_ROLE_NAME)
        if not verified_role:
            await interaction.response.send_message(
                f"❌ El rol `{VERIFIED_ROLE_NAME}` no existe. Contacta a un administrador.", ephemeral=True
            )
            return

        # Verificar si ya tiene el rol
        if verified_role in user.roles:
            await interaction.response.send_message("✅ ¡Ya estás verificado! No necesitas hacerlo de nuevo.", ephemeral=True)
            return

        # Generar CAPTCHA
        code = generate_captcha()

        embed = discord.Embed(
            title="🔐 VERIFICACIÓN DE SEGURIDAD",
            description="Demuestra que no eres un bot ingresando el código de abajo.",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="📋 Tu código CAPTCHA",
            value=f"```\n{code}\n```",
            inline=False
        )
        embed.add_field(
            name="⏰ Tiempo límite",
            value="Tienes **60 segundos** para presionar el botón e ingresar el código.",
            inline=False
        )
        embed.set_footer(text="El código distingue MAYÚSCULAS de minúsculas")

        view = VerifyView(code, verified_role)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="reset_verificacion", description="🔄 Quita el rol Verificado de un usuario (Admin)")
    @app_commands.default_permissions(administrator=True)
    async def reset_verificacion(self, interaction: discord.Interaction, member: discord.Member):
        verified_role = discord.utils.get(interaction.guild.roles, name=VERIFIED_ROLE_NAME)
        if not verified_role:
            await interaction.response.send_message(f"❌ Rol `{VERIFIED_ROLE_NAME}` no encontrado.", ephemeral=True)
            return

        if verified_role not in member.roles:
            await interaction.response.send_message(f"❌ {member.mention} no tiene el rol verificado.", ephemeral=True)
            return

        await member.remove_roles(verified_role, reason=f"Verificación reiniciada por {interaction.user}")
        embed = discord.Embed(
            title="🔄 VERIFICACIÓN REINICIADA",
            description=f"Se removió `{VERIFIED_ROLE_NAME}` de {member.mention}.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

        try:
            await member.send(
                f"🔒 Tu verificación en **{interaction.guild.name}** fue reiniciada. Usa `/verificar` para recuperar el acceso."
            )
        except discord.Forbidden:
            pass

    @app_commands.command(name="stats_verificacion", description="📊 Estadísticas de verificación (Admin)")
    @app_commands.default_permissions(administrator=True)
    async def stats_verificacion(self, interaction: discord.Interaction):
        guild = interaction.guild
        verified_role = discord.utils.get(guild.roles, name=VERIFIED_ROLE_NAME)

        if not verified_role:
            await interaction.response.send_message(f"❌ Rol `{VERIFIED_ROLE_NAME}` no encontrado.", ephemeral=True)
            return

        total = guild.member_count
        verified = len(verified_role.members)
        bots = sum(1 for m in guild.members if m.bot)
        humans = total - bots
        pct = (verified / humans * 100) if humans > 0 else 0

        embed = discord.Embed(title="📊 ESTADÍSTICAS DE VERIFICACIÓN", color=discord.Color.blue(), timestamp=datetime.now())
        embed.add_field(name="👥 Miembros totales", value=f"```{total}```", inline=True)
        embed.add_field(name="✅ Verificados", value=f"```{verified}```", inline=True)
        embed.add_field(name="❌ Sin verificar", value=f"```{humans - verified}```", inline=True)
        embed.add_field(name="🤖 Bots", value=f"```{bots}```", inline=True)
        embed.add_field(name="📈 Porcentaje humanos verificados", value=f"```{pct:.1f}%```", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Verificar(bot))
