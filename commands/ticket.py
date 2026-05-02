import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime
import json
import os
import logging

logger = logging.getLogger('TammyBot.Tickets')

STAFF_ROLES = ["👑 Owner", "⚜️ Admin", "🛡️ Moderador", "🤝 Helper"]
BACKUP_FILE = "backup_tickets.json"


def is_staff(member: discord.Member) -> bool:
    """Verifica si un miembro es parte del staff."""
    if member.guild_permissions.administrator:
        return True
    return any(r.name in STAFF_ROLES for r in member.roles)


def get_ticket_user_id(channel: discord.TextChannel) -> int | None:
    """Extrae el user ID del topic del canal de ticket."""
    if channel.topic and channel.topic.isdigit():
        return int(channel.topic)
    return None


# ==================== VISTA: ABRIR TICKET ====================

class TicketView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="📩 Abrir Ticket",
        style=discord.ButtonStyle.primary,
        custom_id="tammy:open_ticket"
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user

        category = discord.utils.get(guild.categories, name="🎫 TICKETS")
        if not category:
            await interaction.response.send_message(
                "❌ Categoría de tickets no encontrada. Contacta a un administrador.", ephemeral=True
            )
            return

        # Verificar ticket existente
        ticket_name = f"ticket-{user.name.lower().replace(' ', '-')}"
        existing = discord.utils.get(category.text_channels, name=ticket_name)
        if existing:
            await interaction.response.send_message(
                f"❌ Ya tienes un ticket abierto: {existing.mention}", ephemeral=True
            )
            return

        # Configurar permisos
        overwrites: dict = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(
                read_messages=True, send_messages=True,
                attach_files=True, embed_links=True
            ),
        }
        for role_name in STAFF_ROLES:
            role = discord.utils.get(guild.roles, name=role_name)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        try:
            ticket_ch = await guild.create_text_channel(
                name=ticket_name,
                category=category,
                overwrites=overwrites,
                topic=str(user.id)
            )

            embed = discord.Embed(
                title="🎫 TICKET DE SOPORTE",
                description=(
                    f"**Usuario:** {user.mention}\n"
                    f"**ID:** `{user.id}`\n"
                    f"**Creado:** {discord.utils.format_dt(datetime.now(), 'F')}"
                ),
                color=discord.Color.blue()
            )
            embed.add_field(
                name="📝 Instrucciones",
                value="• Describe tu problema con detalle\n• Adjunta capturas si es necesario\n• No hagas spam",
                inline=False
            )
            embed.set_footer(text="El staff te atenderá pronto · Usa el botón para cerrar el ticket")

            await ticket_ch.send(embed=embed, view=CloseTicketView())
            await ticket_ch.send(f"{user.mention} ¡Ticket creado! El staff te atenderá lo antes posible.")

            # Notificar al staff
            staff_ch = discord.utils.get(guild.text_channels, name="🔒-staff-chat")
            if staff_ch:
                await staff_ch.send(
                    f"📩 **Nuevo ticket** de {user.mention} → {ticket_ch.mention}"
                )

            # Log
            logs = discord.utils.get(guild.text_channels, name="📜-logs")
            if logs:
                await logs.send(f"📩 Ticket abierto por **{user}** (`{user.id}`) → {ticket_ch.mention}")

            await interaction.response.send_message(
                f"✅ Ticket creado: {ticket_ch.mention}", ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ No tengo permisos para crear canales. Contacta a un administrador.", ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error creando ticket: {e}")
            await interaction.response.send_message(f"❌ Error inesperado: {e}", ephemeral=True)


# ==================== VISTA: CERRAR TICKET ====================

class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔒 Cerrar Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="tammy:close_ticket"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel

        # Verificar permisos: solo staff o el creador del ticket puede cerrar
        owner_id = get_ticket_user_id(channel)
        if not is_staff(interaction.user) and interaction.user.id != owner_id:
            await interaction.response.send_message("❌ No tienes permiso para cerrar este ticket.", ephemeral=True)
            return

        embed = discord.Embed(
            title="⚠️ ¿CERRAR ESTE TICKET?",
            description="Se guardará una transcripción y el canal se eliminará.\n¿Confirmas?",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, view=ConfirmCloseView(), ephemeral=True)


class ConfirmCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)

    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.send_message("🔒 Cerrando ticket...", ephemeral=True)
        await _close_ticket(interaction)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.send_message("❌ Cierre cancelado.", ephemeral=True)


async def _close_ticket(interaction: discord.Interaction):
    """Lógica real de cierre y archivado del ticket."""
    channel = interaction.channel
    guild = interaction.guild

    # Guardar transcripción
    transcript: list[str] = []
    try:
        async for msg in channel.history(limit=500, oldest_first=True):
            ts = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
            content = msg.content or "[Embed/Archivo adjunto]"
            transcript.append(f"[{ts}] {msg.author}: {content}")
    except Exception as e:
        logger.error(f"Error leyendo historial: {e}")

    # Guardar en JSON de respaldo
    ticket_data = {
        "channel": channel.name,
        "guild_id": guild.id,
        "guild_name": guild.name,
        "closed_by": str(interaction.user),
        "closed_by_id": interaction.user.id,
        "closed_at": datetime.now().isoformat(),
        "transcript": transcript
    }

    try:
        existing: list = []
        if os.path.exists(BACKUP_FILE):
            with open(BACKUP_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        existing.append(ticket_data)
        with open(BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error guardando backup: {e}")

    # Enviar transcripción al canal de logs
    logs = discord.utils.get(guild.text_channels, name="📜-logs")
    if logs and transcript:
        tmp_filename = f"transcript_{channel.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        try:
            with open(tmp_filename, "w", encoding="utf-8") as f:
                f.write(f"TRANSCRIPCIÓN: {channel.name}\n")
                f.write(f"Servidor: {guild.name}\n")
                f.write(f"Cerrado por: {interaction.user}\n")
                f.write(f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
                f.write("=" * 60 + "\n\n")
                f.write("\n".join(transcript))

            embed = discord.Embed(
                title="📄 TRANSCRIPCIÓN DE TICKET",
                description=f"Canal: `{channel.name}`\nCerrado por: {interaction.user.mention}",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            await logs.send(embed=embed, file=discord.File(tmp_filename))
        except Exception as e:
            logger.error(f"Error enviando transcripción: {e}")
        finally:
            if os.path.exists(tmp_filename):
                os.remove(tmp_filename)

    # Esperar un momento antes de eliminar
    await asyncio.sleep(3)
    try:
        await channel.delete(reason=f"Ticket cerrado por {interaction.user}")
    except discord.NotFound:
        pass
    except Exception as e:
        logger.error(f"Error eliminando canal de ticket: {e}")


# ==================== COG TICKETS ====================

class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Registrar vistas persistentes para sobrevivir reinicios
        self.bot.add_view(TicketView(self.bot))
        self.bot.add_view(CloseTicketView())
        logger.info("✅ Vistas persistentes de tickets registradas")

    @app_commands.command(name="ticket_setup", description="🎫 Configura el sistema de tickets (Admin)")
    @app_commands.default_permissions(administrator=True)
    async def ticket_setup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        # Crear/encontrar categoría
        category = discord.utils.get(guild.categories, name="🎫 TICKETS")
        if not category:
            category = await guild.create_category("🎫 TICKETS")
            await interaction.followup.send("✅ Categoría `🎫 TICKETS` creada.", ephemeral=True)

        # Crear/encontrar canal
        ticket_ch = discord.utils.get(guild.text_channels, name="🎫-abrir-ticket")
        if not ticket_ch:
            ticket_ch = await guild.create_text_channel("🎫-abrir-ticket", category=category)

            # Permisos
            await ticket_ch.set_permissions(guild.default_role, read_messages=False, send_messages=False)
            verified = discord.utils.get(guild.roles, name="✅ Verificado")
            if verified:
                await ticket_ch.set_permissions(verified, read_messages=True, send_messages=False)

        # Limpiar y enviar embed
        await ticket_ch.purge(limit=10)
        embed = discord.Embed(
            title="🎫 SISTEMA DE TICKETS",
            description="**¿Necesitas ayuda del staff? ¡Abre un ticket!**",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="📝 ¿Para qué sirve?",
            value="• Reportar problemas técnicos\n• Consultas al staff\n• Reportar usuarios\n• Sugerencias privadas",
            inline=False
        )
        embed.add_field(
            name="⚙️ ¿Cómo funciona?",
            value="1. Presiona **📩 Abrir Ticket**\n2. Explica tu problema\n3. El staff te responde\n4. Cierra el ticket cuando termines",
            inline=False
        )
        embed.set_footer(text="Los tickets son privados y quedan registrados")
        await ticket_ch.send(embed=embed, view=TicketView(self.bot))
        await interaction.followup.send(f"✅ Sistema de tickets configurado: {ticket_ch.mention}", ephemeral=True)

    @app_commands.command(name="ticket_close", description="🔒 Cierra el ticket actual (Staff o creador)")
    async def ticket_close(self, interaction: discord.Interaction):
        if not interaction.channel.name.startswith("ticket-"):
            await interaction.response.send_message("❌ Este comando solo funciona dentro de un ticket.", ephemeral=True)
            return
        owner_id = get_ticket_user_id(interaction.channel)
        if not is_staff(interaction.user) and interaction.user.id != owner_id:
            await interaction.response.send_message("❌ No tienes permiso para cerrar este ticket.", ephemeral=True)
            return
        await interaction.response.send_message("🔒 Cerrando ticket...", ephemeral=True)
        await _close_ticket(interaction)

    @app_commands.command(name="ticket_stats", description="📊 Estadísticas del sistema de tickets (Admin)")
    @app_commands.default_permissions(administrator=True)
    async def ticket_stats(self, interaction: discord.Interaction):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="🎫 TICKETS")
        open_count = 0
        if category:
            open_count = sum(1 for ch in category.text_channels if ch.name.startswith("ticket-"))

        backup_count = 0
        if os.path.exists(BACKUP_FILE):
            try:
                with open(BACKUP_FILE, "r") as f:
                    backup_count = len(json.load(f))
            except Exception:
                pass

        embed = discord.Embed(title="📊 ESTADÍSTICAS DE TICKETS", color=discord.Color.blue(), timestamp=datetime.now())
        embed.add_field(name="🎫 Tickets abiertos", value=f"```{open_count}```", inline=True)
        embed.add_field(name="📁 Tickets cerrados (historial)", value=f"```{backup_count}```", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
