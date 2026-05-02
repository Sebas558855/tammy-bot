import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timedelta
import json
import os
import logging

logger = logging.getLogger('TammyBot.Admin')

# ==================== VISTAS DE CONFIRMACIÓN ====================

class ConfirmKickView(discord.ui.View):
    def __init__(self, member: discord.Member, reason: str, cog):
        super().__init__(timeout=30)
        self.member = member
        self.reason = reason
        self.cog = cog

    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        try:
            await self.member.kick(reason=self.reason)
            embed = discord.Embed(
                title="👢 USUARIO EXPULSADO",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            embed.add_field(name="👤 Usuario", value=f"{self.member} ({self.member.id})", inline=True)
            embed.add_field(name="📝 Razón", value=self.reason, inline=False)
            embed.add_field(name="👮 Moderador", value=interaction.user.mention, inline=True)
            await interaction.response.edit_message(embed=embed, view=None)
            await self.cog.log_action(interaction.guild, "👢 KICK", interaction.user, self.member, self.reason)
        except discord.Forbidden:
            await interaction.response.edit_message(content="❌ No tengo permisos para expulsar a este usuario.", embed=None, view=None)
        except Exception as e:
            await interaction.response.edit_message(content=f"❌ Error: {e}", embed=None, view=None)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="❌ Expulsión cancelada.", embed=None, view=None)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class ConfirmBanView(discord.ui.View):
    def __init__(self, member: discord.Member, reason: str, delete_days: int, cog):
        super().__init__(timeout=30)
        self.member = member
        self.reason = reason
        self.delete_days = delete_days
        self.cog = cog

    @discord.ui.button(label="✅ Confirmar Ban", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        try:
            await self.member.ban(reason=self.reason, delete_message_days=self.delete_days)
            embed = discord.Embed(
                title="🔨 USUARIO BANEADO",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            embed.add_field(name="👤 Usuario", value=f"{self.member} ({self.member.id})", inline=True)
            embed.add_field(name="📝 Razón", value=self.reason, inline=False)
            embed.add_field(name="🗑️ Días eliminados", value=str(self.delete_days), inline=True)
            embed.add_field(name="👮 Moderador", value=interaction.user.mention, inline=True)
            await interaction.response.edit_message(embed=embed, view=None)
            await self.cog.log_action(interaction.guild, "🔨 BAN", interaction.user, self.member, self.reason)
        except discord.Forbidden:
            await interaction.response.edit_message(content="❌ No tengo permisos para banear a este usuario.", embed=None, view=None)
        except Exception as e:
            await interaction.response.edit_message(content=f"❌ Error: {e}", embed=None, view=None)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="❌ Baneo cancelado.", embed=None, view=None)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


# ==================== COG ADMIN ====================

class Admin(commands.Cog):
    """Comandos de administración y moderación del servidor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.warnings_file = "warnings.json"
        self.warnings: dict = {}
        self.load_warnings()

    # ---------- Persistencia de advertencias ----------

    def load_warnings(self):
        if os.path.exists(self.warnings_file):
            try:
                with open(self.warnings_file, "r", encoding="utf-8") as f:
                    self.warnings = json.load(f)
            except json.JSONDecodeError:
                logger.error("warnings.json corrupto, iniciando vacío.")
                self.warnings = {}
        else:
            self.warnings = {}

    def save_warnings(self):
        with open(self.warnings_file, "w", encoding="utf-8") as f:
            json.dump(self.warnings, f, indent=2, ensure_ascii=False)

    # ---------- Utilidades ----------

    def get_logs_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        return discord.utils.get(guild.text_channels, name="📜-logs")

    async def log_action(self, guild: discord.Guild, action: str, moderator: discord.Member,
                         target, reason: str, duration: str | None = None):
        logs = self.get_logs_channel(guild)
        if not logs:
            return
        embed = discord.Embed(
            title=f"🔨 {action}",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        embed.add_field(name="👮 Moderador", value=moderator.mention, inline=True)
        embed.add_field(name="👤 Objetivo", value=target.mention if hasattr(target, 'mention') else str(target), inline=True)
        embed.add_field(name="📝 Razón", value=reason, inline=False)
        if duration:
            embed.add_field(name="⏰ Duración", value=duration, inline=True)
        embed.set_footer(text=f"ID: {target.id if hasattr(target, 'id') else 'N/A'}")
        try:
            await logs.send(embed=embed)
        except Exception as e:
            logger.error(f"Error enviando log: {e}")

    def _parse_time(self, tiempo: str) -> int | None:
        """Convierte una cadena de tiempo (ej: 10m, 2h, 1d) a segundos. Retorna None si inválido."""
        units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        if not tiempo or tiempo[-1] not in units:
            return None
        try:
            return int(tiempo[:-1]) * units[tiempo[-1]]
        except ValueError:
            return None

    def _check_hierarchy(self, moderator: discord.Member, target: discord.Member) -> bool:
        """True si el moderador puede actuar sobre el objetivo."""
        return moderator.guild.owner == moderator or moderator.top_role > target.top_role

    # ==================== LIMPIEZA ====================

    @app_commands.command(name="clear", description="🧹 Elimina mensajes del canal (1-100)")
    @app_commands.default_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, cantidad: app_commands.Range[int, 1, 100],
                    usuario: discord.Member | None = None):
        await interaction.response.defer(ephemeral=True)
        check = (lambda m: m.author == usuario) if usuario else (lambda m: True)
        deleted = await interaction.channel.purge(limit=cantidad, check=check)
        suffix = f" de **{usuario.display_name}**" if usuario else ""
        await interaction.followup.send(f"✅ Se eliminaron **{len(deleted)}** mensajes{suffix}.", ephemeral=True)
        await self.log_action(interaction.guild, "🧹 CLEAR", interaction.user,
                              usuario or interaction.user, f"{len(deleted)} mensajes eliminados{suffix}")

    @app_commands.command(name="clear_until", description="🗑️ Elimina mensajes hasta un ID específico")
    @app_commands.default_permissions(manage_messages=True)
    async def clear_until(self, interaction: discord.Interaction, message_id: str):
        await interaction.response.defer(ephemeral=True)
        try:
            target = await interaction.channel.fetch_message(int(message_id))
            deleted = await interaction.channel.purge(limit=500, after=target)
            await interaction.followup.send(f"✅ Se eliminaron **{len(deleted)}** mensajes.", ephemeral=True)
        except discord.NotFound:
            await interaction.followup.send("❌ Mensaje no encontrado.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("❌ ID de mensaje inválido.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    # ==================== MUTE / UNMUTE ====================

    @app_commands.command(name="mute", description="🔇 Silencia a un usuario (ej: tiempo = 10m, 1h, 2d)")
    @app_commands.default_permissions(moderate_members=True)
    async def mute(self, interaction: discord.Interaction, member: discord.Member,
                   tiempo: str, razon: str = "No especificada"):
        if not self._check_hierarchy(interaction.user, member):
            await interaction.response.send_message("❌ No puedes silenciar a alguien con un rol igual o superior al tuyo.", ephemeral=True)
            return

        duration = self._parse_time(tiempo)
        if duration is None:
            await interaction.response.send_message("❌ Formato inválido. Usa: `10s`, `5m`, `2h`, `1d`", ephemeral=True)
            return
        if duration > 2_419_200:
            await interaction.response.send_message("❌ El mute no puede superar 28 días.", ephemeral=True)
            return

        try:
            await member.timeout(timedelta(seconds=duration), reason=razon)
            embed = discord.Embed(title="🔇 USUARIO SILENCIADO", color=discord.Color.red(), timestamp=datetime.now())
            embed.add_field(name="👤 Usuario", value=member.mention, inline=True)
            embed.add_field(name="⏰ Duración", value=tiempo, inline=True)
            embed.add_field(name="📝 Razón", value=razon, inline=False)
            embed.add_field(name="👮 Moderador", value=interaction.user.mention, inline=True)
            await interaction.response.send_message(embed=embed)
            try:
                await member.send(f"🔇 Has sido silenciado en **{interaction.guild.name}**\n📝 Razón: {razon}\n⏰ Duración: {tiempo}")
            except discord.Forbidden:
                pass
            await self.log_action(interaction.guild, "🔇 MUTE", interaction.user, member, razon, tiempo)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Sin permisos para silenciar este usuario.", ephemeral=True)

    @app_commands.command(name="unmute", description="🔊 Quita el silencio a un usuario")
    @app_commands.default_permissions(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, member: discord.Member, razon: str = "No especificada"):
        if member.timed_out_until is None:
            await interaction.response.send_message("❌ Este usuario no está silenciado.", ephemeral=True)
            return
        try:
            await member.timeout(None, reason=razon)
            embed = discord.Embed(title="🔊 USUARIO DESILENCIADO", color=discord.Color.green(), timestamp=datetime.now())
            embed.add_field(name="👤 Usuario", value=member.mention, inline=True)
            embed.add_field(name="📝 Razón", value=razon, inline=False)
            embed.add_field(name="👮 Moderador", value=interaction.user.mention, inline=True)
            await interaction.response.send_message(embed=embed)
            try:
                await member.send(f"🔊 Has sido desilenciado en **{interaction.guild.name}**\n📝 Razón: {razon}")
            except discord.Forbidden:
                pass
            await self.log_action(interaction.guild, "🔊 UNMUTE", interaction.user, member, razon)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Sin permisos para desilenciar este usuario.", ephemeral=True)

    # ==================== KICK ====================

    @app_commands.command(name="kick", description="👢 Expulsa a un usuario del servidor")
    @app_commands.default_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, razon: str = "No especificada"):
        if member == interaction.user:
            await interaction.response.send_message("❌ No puedes expulsarte a ti mismo.", ephemeral=True)
            return
        if not self._check_hierarchy(interaction.user, member):
            await interaction.response.send_message("❌ No puedes expulsar a alguien con un rol igual o superior.", ephemeral=True)
            return

        embed = discord.Embed(
            title="⚠️ CONFIRMAR EXPULSIÓN",
            description=f"¿Expulsar a {member.mention}?\n**Razón:** {razon}",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, view=ConfirmKickView(member, razon, self), ephemeral=True)

    # ==================== BAN / UNBAN ====================

    @app_commands.command(name="ban", description="🔨 Banea a un usuario del servidor")
    @app_commands.default_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member,
                  razon: str = "No especificada", delete_days: app_commands.Range[int, 0, 7] = 0):
        if member == interaction.user:
            await interaction.response.send_message("❌ No puedes banearte a ti mismo.", ephemeral=True)
            return
        if not self._check_hierarchy(interaction.user, member):
            await interaction.response.send_message("❌ No puedes banear a alguien con un rol igual o superior.", ephemeral=True)
            return

        embed = discord.Embed(
            title="⚠️ CONFIRMAR BANEO",
            description=f"¿Banear a {member.mention}?\n**Razón:** {razon}\n**Días a eliminar:** {delete_days}",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, view=ConfirmBanView(member, razon, delete_days, self), ephemeral=True)

    @app_commands.command(name="unban", description="🔓 Desbanea a un usuario por ID")
    @app_commands.default_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, razon: str = "No especificada"):
        try:
            uid = int(user_id)
        except ValueError:
            await interaction.response.send_message("❌ ID inválido. Debe ser un número.", ephemeral=True)
            return
        try:
            user = await self.bot.fetch_user(uid)
            await interaction.guild.unban(user, reason=razon)
            embed = discord.Embed(title="🔓 USUARIO DESBANEADO", color=discord.Color.green(), timestamp=datetime.now())
            embed.add_field(name="👤 Usuario", value=f"{user} ({user.id})", inline=True)
            embed.add_field(name="📝 Razón", value=razon, inline=False)
            embed.add_field(name="👮 Moderador", value=interaction.user.mention, inline=True)
            await interaction.response.send_message(embed=embed)
            await self.log_action(interaction.guild, "🔓 UNBAN", interaction.user, user, razon)
        except discord.NotFound:
            await interaction.response.send_message("❌ Usuario no encontrado o no está baneado.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    # ==================== ADVERTENCIAS ====================

    @app_commands.command(name="warn", description="⚠️ Advierte a un usuario")
    @app_commands.default_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, razon: str = "No especificada"):
        if not self._check_hierarchy(interaction.user, member):
            await interaction.response.send_message("❌ No puedes advertir a alguien con un rol igual o superior.", ephemeral=True)
            return

        uid = str(member.id)
        if uid not in self.warnings:
            self.warnings[uid] = []

        self.warnings[uid].append({
            "id": len(self.warnings[uid]) + 1,
            "reason": razon,
            "moderator_id": interaction.user.id,
            "moderator_name": str(interaction.user),
            "date": datetime.now().isoformat()
        })
        self.save_warnings()

        total = len(self.warnings[uid])
        embed = discord.Embed(title="⚠️ USUARIO ADVERTIDO", color=discord.Color.orange(), timestamp=datetime.now())
        embed.add_field(name="👤 Usuario", value=member.mention, inline=True)
        embed.add_field(name="⚠️ Advertencias", value=f"{total}/5", inline=True)
        embed.add_field(name="📝 Razón", value=razon, inline=False)
        embed.add_field(name="👮 Moderador", value=interaction.user.mention, inline=True)
        await interaction.response.send_message(embed=embed)

        try:
            await member.send(f"⚠️ Has recibido una advertencia en **{interaction.guild.name}**\n📝 Razón: {razon}\n⚠️ Total: {total}/5")
        except discord.Forbidden:
            pass

        await self.log_action(interaction.guild, "⚠️ WARN", interaction.user, member, razon)

        # Escalado automático de sanciones
        if total == 3:
            await member.timeout(timedelta(hours=1), reason="3 advertencias")
            await interaction.followup.send(f"🔇 {member.mention} fue silenciado 1h por acumular 3 advertencias.", ephemeral=True)
        elif total == 5:
            await member.timeout(timedelta(days=1), reason="5 advertencias")
            await interaction.followup.send(f"🔇 {member.mention} fue silenciado 24h por acumular 5 advertencias.", ephemeral=True)

    @app_commands.command(name="warnings", description="📋 Muestra las advertencias de un usuario")
    @app_commands.default_permissions(moderate_members=True)
    async def warnings_cmd(self, interaction: discord.Interaction, member: discord.Member):
        uid = str(member.id)
        member_warns = self.warnings.get(uid, [])

        if not member_warns:
            await interaction.response.send_message(f"✅ {member.mention} no tiene advertencias.", ephemeral=True)
            return

        embed = discord.Embed(title=f"📋 ADVERTENCIAS — {member.display_name}",
                              color=discord.Color.orange(), timestamp=datetime.now())
        desc = ""
        for w in member_warns:
            date_str = datetime.fromisoformat(w["date"]).strftime("%d/%m/%Y %H:%M")
            desc += f"**#{w['id']}** `{date_str}`\n📝 {w['reason']}\n👮 {w.get('moderator_name', 'Desconocido')}\n\n"

        embed.description = desc[:4000]
        embed.set_footer(text=f"Total: {len(member_warns)} advertencias")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="clearwarns", description="🗑️ Limpia todas las advertencias de un usuario")
    @app_commands.default_permissions(administrator=True)
    async def clearwarns(self, interaction: discord.Interaction, member: discord.Member):
        uid = str(member.id)
        if uid in self.warnings:
            count = len(self.warnings[uid])
            del self.warnings[uid]
            self.save_warnings()
            await interaction.response.send_message(f"✅ Se eliminaron **{count}** advertencias de {member.mention}.", ephemeral=True)
            await self.log_action(interaction.guild, "🗑️ CLEARWARNS", interaction.user, member, "Advertencias limpiadas")
        else:
            await interaction.response.send_message(f"❌ {member.mention} no tiene advertencias.", ephemeral=True)

    # ==================== CANAL ====================

    @app_commands.command(name="slowmode", description="🐌 Configura el modo lento del canal (0 para desactivar)")
    @app_commands.default_permissions(manage_channels=True)
    async def slowmode(self, interaction: discord.Interaction, segundos: app_commands.Range[int, 0, 21600]):
        await interaction.channel.edit(slowmode_delay=segundos)
        if segundos == 0:
            msg = "✅ Modo lento **desactivado**."
        else:
            mins = segundos // 60
            msg = f"✅ Modo lento: **{mins}m** ({segundos}s)." if mins else f"✅ Modo lento: **{segundos}s**."
        await interaction.response.send_message(msg)
        await self.log_action(interaction.guild, "🐌 SLOWMODE", interaction.user, interaction.user, f"{segundos}s en #{interaction.channel.name}")

    @app_commands.command(name="lock", description="🔒 Bloquea el canal para usuarios normales")
    @app_commands.default_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction):
        verified = discord.utils.get(interaction.guild.roles, name="✅ Verificado")
        miembro = discord.utils.get(interaction.guild.roles, name="🎮 Miembro")
        for role in filter(None, [verified, miembro]):
            await interaction.channel.set_permissions(role, send_messages=False)
        embed = discord.Embed(title="🔒 CANAL BLOQUEADO",
                              description="Solo el staff puede hablar aquí.",
                              color=discord.Color.red(), timestamp=datetime.now())
        embed.set_footer(text=f"Bloqueado por {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)
        await self.log_action(interaction.guild, "🔒 LOCK", interaction.user, interaction.user, f"#{interaction.channel.name}")

    @app_commands.command(name="unlock", description="🔓 Desbloquea el canal")
    @app_commands.default_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction):
        verified = discord.utils.get(interaction.guild.roles, name="✅ Verificado")
        miembro = discord.utils.get(interaction.guild.roles, name="🎮 Miembro")
        for role in filter(None, [verified, miembro]):
            await interaction.channel.set_permissions(role, send_messages=None)
        embed = discord.Embed(title="🔓 CANAL DESBLOQUEADO",
                              description="¡Ya pueden volver a hablar!",
                              color=discord.Color.green(), timestamp=datetime.now())
        embed.set_footer(text=f"Desbloqueado por {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)
        await self.log_action(interaction.guild, "🔓 UNLOCK", interaction.user, interaction.user, f"#{interaction.channel.name}")

    # ==================== INFO ====================

    @app_commands.command(name="userinfo", description="📊 Muestra información de un usuario")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member | None = None):
        member = member or interaction.user
        embed = discord.Embed(
            title=f"📊 {member.display_name}",
            color=member.color if member.color.value else discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="🏷️ Tag", value=str(member), inline=True)
        embed.add_field(name="🆔 ID", value=member.id, inline=True)
        embed.add_field(name="🤖 Bot", value="Sí" if member.bot else "No", inline=True)
        embed.add_field(name="📅 Cuenta creada", value=discord.utils.format_dt(member.created_at, 'D'), inline=True)
        embed.add_field(name="📥 Entró al servidor", value=discord.utils.format_dt(member.joined_at, 'D'), inline=True)
        warn_count = len(self.warnings.get(str(member.id), []))
        embed.add_field(name="⚠️ Advertencias", value=str(warn_count), inline=True)
        roles = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
        embed.add_field(name=f"🎭 Roles ({len(roles)})", value=", ".join(roles[:10]) or "Ninguno", inline=False)
        embed.set_footer(text=f"Solicitado por {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="🌐 Muestra información del servidor")
    async def serverinfo(self, interaction: discord.Interaction):
        g = interaction.guild
        humans = sum(1 for m in g.members if not m.bot)
        embed = discord.Embed(title=f"🌐 {g.name}", color=discord.Color.blue(), timestamp=datetime.now())
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        embed.add_field(name="🆔 ID", value=g.id, inline=True)
        embed.add_field(name="👑 Owner", value=g.owner.mention if g.owner else "?", inline=True)
        embed.add_field(name="📅 Creado", value=discord.utils.format_dt(g.created_at, 'D'), inline=True)
        embed.add_field(name="👥 Miembros", value=f"Total: {g.member_count}\n👤 {humans} humanos\n🤖 {g.member_count - humans} bots", inline=True)
        embed.add_field(name="📊 Canales", value=f"📝 {len(g.text_channels)} texto\n🔊 {len(g.voice_channels)} voz", inline=True)
        embed.add_field(name="🎭 Roles", value=len(g.roles), inline=True)
        if g.premium_subscription_count:
            embed.add_field(name="✨ Boost", value=f"Nivel {g.premium_tier} · {g.premium_subscription_count} boosts", inline=True)
        embed.set_footer(text=f"Solicitado por {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

    # ==================== VOZ ====================

    @app_commands.command(name="voice_mute", description="🔇 Silencia a un usuario en canales de voz")
    @app_commands.default_permissions(mute_members=True)
    async def voice_mute(self, interaction: discord.Interaction, member: discord.Member, razon: str = "No especificada"):
        if not member.voice:
            await interaction.response.send_message("❌ El usuario no está en un canal de voz.", ephemeral=True)
            return
        await member.edit(mute=True, reason=razon)
        await interaction.response.send_message(f"🔇 {member.mention} silenciado en voz.\n📝 Razón: {razon}")
        await self.log_action(interaction.guild, "🔇 VOICE MUTE", interaction.user, member, razon)

    @app_commands.command(name="voice_unmute", description="🔊 Quita el silencio de voz a un usuario")
    @app_commands.default_permissions(mute_members=True)
    async def voice_unmute(self, interaction: discord.Interaction, member: discord.Member, razon: str = "No especificada"):
        await member.edit(mute=False, reason=razon)
        await interaction.response.send_message(f"🔊 {member.mention} desilenciado en voz.\n📝 Razón: {razon}")
        await self.log_action(interaction.guild, "🔊 VOICE UNMUTE", interaction.user, member, razon)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
