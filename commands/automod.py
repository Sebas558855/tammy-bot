import discord
from discord.ext import commands
from discord import app_commands
import re
import json
import os
from datetime import datetime, timedelta
import unicodedata
import logging

logger = logging.getLogger('TammyBot.AutoMod')

# ==================== PALABRAS PROHIBIDAS ====================
BAD_WORDS: set[str] = {
    # Español
    'puta', 'puto', 'mierda', 'coño', 'carajo', 'verga', 'pendejo', 'cabron',
    'hijueputa', 'gonorrea', 'malparido', 'boludo', 'mamahuevo', 'csm', 'ctm',
    'maricon', 'marica', 'joder', 'chinga', 'chingada', 'pinche', 'culero',
    # Inglés
    'fuck', 'shit', 'asshole', 'bastard', 'cunt', 'whore', 'slut',
    'nigger', 'nigga', 'retard', 'faggot',
}

SPAM_PHRASES: list[str] = [
    'free nitro', 'free discord nitro', 'nitro gift', 'free robux',
    'free vbucks', 'gana dinero facil', 'trabajo desde casa',
    'haz clic aquí', 'click here to win',
]

DEFAULT_CONFIG: dict = {
    "filters": {
        "bad_words": True,
        "invites": True,
        "links": False,
        "spam": True,
        "caps": True,
        "mass_mentions": True,
        "zalgo": True,
        "emojis": False
    },
    "actions": {
        "warning_limit": 3,
        "mute_duration": 300,
        "delete_message": True,
        "log_violations": True,
        "dm_warning": True
    },
    "thresholds": {
        "caps_percentage": 70,
        "caps_min_length": 10,
        "spam_repeat": 3,
        "spam_timeframe": 5,
        "max_mentions": 5,
        "max_emojis": 10,
        "zalgo_threshold": 5
    },
    "ignored_roles": [],
    "ignored_channels": [],
    "whitelist_links": [
        "youtube.com", "youtu.be", "twitch.tv", "twitter.com",
        "x.com", "instagram.com", "tiktok.com", "discord.com"
    ]
}


class AutoMod(commands.Cog):
    """Sistema de automoderación inteligente."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = "automod_config.json"
        self.infractions_file = "automod_infractions.json"
        self.config: dict = {}
        self.infractions: dict = {}
        self._recent_messages: dict[int, list] = {}  # user_id -> [(content, timestamp)]

        self.load_config()
        self.load_infractions()

        # Patrones compilados
        self.invite_re = re.compile(r'discord\.(?:gg|io|me|li|com/invite)/[a-zA-Z0-9]+', re.I)
        self.link_re = re.compile(r'https?://\S+', re.I)
        self.emoji_re = re.compile(
            r'<a?:[a-zA-Z0-9_]+:\d+>|'
            r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF'
            r'\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF'
            r'\U00002702-\U000027B0\U000024C2-\U0001F251]+'
        )

    # ==================== PERSISTENCIA ====================

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                # Merge con defaults para asegurar todas las claves
                self.config = DEFAULT_CONFIG.copy()
                for key in DEFAULT_CONFIG:
                    if key in loaded:
                        self.config[key] = {**DEFAULT_CONFIG[key], **loaded[key]} if isinstance(DEFAULT_CONFIG[key], dict) else loaded[key]
                return
            except json.JSONDecodeError:
                logger.error("automod_config.json corrupto, usando defaults.")
        self.config = {k: v.copy() if isinstance(v, dict) else v for k, v in DEFAULT_CONFIG.items()}
        self.save_config()

    def save_config(self):
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    def load_infractions(self):
        if os.path.exists(self.infractions_file):
            try:
                with open(self.infractions_file, "r", encoding="utf-8") as f:
                    self.infractions = json.load(f)
                return
            except json.JSONDecodeError:
                logger.error("automod_infractions.json corrupto.")
        self.infractions = {}
        self.save_infractions()

    def save_infractions(self):
        with open(self.infractions_file, "w", encoding="utf-8") as f:
            json.dump(self.infractions, f, indent=2, ensure_ascii=False)

    # ==================== LÓGICA CENTRAL ====================

    def should_ignore(self, message: discord.Message) -> bool:
        if message.author.bot:
            return True
        if message.guild is None:
            return True
        if message.author.guild_permissions.manage_messages:
            return True
        if message.channel.id in self.config["ignored_channels"]:
            return True
        member_role_ids = {r.id for r in message.author.roles}
        if any(rid in member_role_ids for rid in self.config["ignored_roles"]):
            return True
        return False

    def add_infraction(self, user_id: int, reason: str) -> bool:
        """Agrega infracción. Retorna True si debe ser muteado."""
        uid = str(user_id)
        if uid not in self.infractions:
            self.infractions[uid] = []
        self.infractions[uid].append({
            "reason": reason,
            "date": datetime.now().isoformat()
        })
        self.save_infractions()
        return len(self.infractions[uid]) >= self.config["actions"]["warning_limit"]

    def check_spam(self, message: discord.Message) -> bool:
        """Detecta spam de mensajes repetidos en poco tiempo."""
        uid = message.author.id
        now = datetime.now()
        timeframe = self.config["thresholds"]["spam_timeframe"]

        # Limpiar mensajes viejos
        self._recent_messages.setdefault(uid, [])
        self._recent_messages[uid] = [
            (c, t) for c, t in self._recent_messages[uid]
            if (now - t).total_seconds() < timeframe
        ]

        # Contar repeticiones del mismo contenido
        same = sum(1 for c, _ in self._recent_messages[uid] if c == message.content)
        self._recent_messages[uid].append((message.content, now))

        return same >= self.config["thresholds"]["spam_repeat"] - 1

    def is_zalgo(self, text: str) -> bool:
        """Detecta caracteres de texto Zalgo (diacríticos apilados)."""
        count = sum(
            1 for ch in text
            if unicodedata.category(ch) in ('Mn', 'Me', 'Mc')
        )
        return count > self.config["thresholds"]["zalgo_threshold"]

    def is_whitelisted_link(self, link: str) -> bool:
        link_lower = link.lower()
        return any(w in link_lower for w in self.config["whitelist_links"])

    async def take_action(self, message: discord.Message, reason: str):
        """Aplica la acción correcta ante una violación."""
        # Eliminar mensaje
        if self.config["actions"]["delete_message"]:
            try:
                await message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

        should_mute = self.add_infraction(message.author.id, reason)
        uid = str(message.author.id)
        infraction_count = len(self.infractions.get(uid, []))

        # DM de advertencia
        if self.config["actions"]["dm_warning"]:
            try:
                embed = discord.Embed(
                    title="⚠️ ADVERTENCIA AUTOMÁTICA",
                    description=f"Has violado las normas en **{message.guild.name}**",
                    color=discord.Color.orange()
                )
                embed.add_field(name="📝 Razón", value=reason, inline=False)
                embed.add_field(name="⚠️ Infracciones", value=f"{infraction_count}/{self.config['actions']['warning_limit']}", inline=True)
                await message.author.send(embed=embed)
            except discord.Forbidden:
                pass

        # Mute automático
        if should_mute:
            duration = self.config["actions"]["mute_duration"]
            try:
                await message.author.timeout(timedelta(seconds=duration), reason=f"AutoMod: {reason}")
                embed = discord.Embed(
                    title="🔇 MUTE AUTOMÁTICO",
                    description=f"{message.author.mention} fue muteado automáticamente.",
                    color=discord.Color.red()
                )
                embed.add_field(name="📝 Razón", value=reason, inline=False)
                embed.add_field(name="⏰ Duración", value=f"{duration}s", inline=True)
                try:
                    await message.channel.send(embed=embed, delete_after=10)
                except discord.Forbidden:
                    pass
                # Limpiar infracciones tras mute
                self.infractions[uid] = []
                self.save_infractions()
            except (discord.Forbidden, discord.HTTPException) as e:
                logger.error(f"No se pudo mutear a {message.author}: {e}")

        # Log en canal
        if self.config["actions"]["log_violations"]:
            logs = discord.utils.get(message.guild.text_channels, name="📜-logs")
            if logs:
                embed = discord.Embed(
                    title="🤖 AUTOMOD — VIOLACIÓN DETECTADA",
                    color=discord.Color.orange(),
                    timestamp=datetime.now()
                )
                embed.add_field(name="👤 Usuario", value=f"{message.author.mention} (`{message.author}`)", inline=True)
                embed.add_field(name="📍 Canal", value=message.channel.mention, inline=True)
                embed.add_field(name="📝 Razón", value=reason, inline=False)
                content_preview = message.content[:300] + ("..." if len(message.content) > 300 else "")
                embed.add_field(name="💬 Contenido", value=f"```{content_preview or '[vacío]'}```", inline=False)
                embed.add_field(name="⚠️ Infracciones", value=f"{infraction_count}", inline=True)
                try:
                    await logs.send(embed=embed)
                except discord.Forbidden:
                    pass

    # ==================== LISTENER PRINCIPAL ====================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if self.should_ignore(message):
            return

        content = message.content
        content_lower = content.lower()
        f = self.config["filters"]
        t = self.config["thresholds"]

        # 1. Palabras prohibidas
        if f["bad_words"]:
            for word in BAD_WORDS:
                if re.search(rf'\b{re.escape(word)}\b', content_lower):
                    await self.take_action(message, f"Palabra prohibida detectada")
                    return

        # 2. Invitaciones de Discord
        if f["invites"] and self.invite_re.search(content):
            await self.take_action(message, "Invitación a servidor externo")
            return

        # 3. Links no permitidos
        if f["links"]:
            links = self.link_re.findall(content)
            if links and not all(self.is_whitelisted_link(l) for l in links):
                await self.take_action(message, "Enlace no permitido")
                return

        # 4. Spam de mensajes repetidos
        if f["spam"] and content.strip():
            if self.check_spam(message):
                await self.take_action(message, "Spam detectado (mensajes repetidos)")
                return

        # 5. Mayúsculas excesivas
        if f["caps"] and len(content) >= t["caps_min_length"]:
            letters = [c for c in content if c.isalpha()]
            if letters:
                caps_pct = sum(1 for c in letters if c.isupper()) / len(letters) * 100
                if caps_pct >= t["caps_percentage"]:
                    await self.take_action(message, f"Mayúsculas excesivas ({caps_pct:.0f}%)")
                    return

        # 6. Menciones masivas
        if f["mass_mentions"] and len(message.mentions) >= t["max_mentions"]:
            await self.take_action(message, f"Menciones masivas ({len(message.mentions)})")
            return

        # 7. Texto Zalgo
        if f["zalgo"] and self.is_zalgo(content):
            await self.take_action(message, "Texto Zalgo / caracteres abusivos")
            return

        # 8. Emojis excesivos
        if f["emojis"]:
            count = len(self.emoji_re.findall(content))
            if count > t["max_emojis"]:
                await self.take_action(message, f"Emojis excesivos ({count})")
                return

        # 9. Frases de spam/estafa
        for phrase in SPAM_PHRASES:
            if phrase in content_lower:
                await self.take_action(message, f"Contenido spam/estafa detectado")
                return

    # ==================== COMANDOS ====================

    @app_commands.command(name="automod", description="🤖 Panel de configuración del AutoMod")
    @app_commands.default_permissions(administrator=True)
    async def automod(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🤖 AUTOMOD — PANEL DE CONFIGURACIÓN",
                              color=discord.Color.blue())
        f_text = "\n".join(
            f"{'✅' if v else '❌'} {k.replace('_', ' ').title()}"
            for k, v in self.config["filters"].items()
        )
        embed.add_field(name="🔍 Filtros", value=f_text, inline=True)
        a_text = "\n".join(
            f"{'✅' if v else '❌'} {k.replace('_', ' ').title()}" if isinstance(v, bool)
            else f"⚙️ {k.replace('_', ' ').title()}: `{v}`"
            for k, v in self.config["actions"].items()
        )
        embed.add_field(name="⚙️ Acciones", value=a_text, inline=True)
        t_text = "\n".join(f"• {k.replace('_', ' ').title()}: `{v}`" for k, v in self.config["thresholds"].items())
        embed.add_field(name="📊 Umbrales", value=t_text, inline=False)
        ignored_roles = len(self.config["ignored_roles"])
        ignored_ch = len(self.config["ignored_channels"])
        embed.add_field(name="🚫 Ignorados", value=f"{ignored_roles} roles · {ignored_ch} canales", inline=True)
        embed.set_footer(text="Usa /automod_filter, /automod_threshold, /automod_action para configurar")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="automod_filter", description="🔍 Activa/desactiva un filtro específico")
    @app_commands.default_permissions(administrator=True)
    async def automod_filter(self, interaction: discord.Interaction, filtro: str, estado: bool):
        if filtro not in self.config["filters"]:
            opts = ', '.join(self.config["filters"])
            await interaction.response.send_message(f"❌ Filtro inválido. Opciones: `{opts}`", ephemeral=True)
            return
        self.config["filters"][filtro] = estado
        self.save_config()
        word = "activado" if estado else "desactivado"
        await interaction.response.send_message(f"✅ Filtro `{filtro}` **{word}**.", ephemeral=True)

    @app_commands.command(name="automod_threshold", description="📊 Configura un umbral de detección")
    @app_commands.default_permissions(administrator=True)
    async def automod_threshold(self, interaction: discord.Interaction, umbral: str, valor: int):
        if umbral not in self.config["thresholds"]:
            opts = ', '.join(self.config["thresholds"])
            await interaction.response.send_message(f"❌ Umbral inválido. Opciones: `{opts}`", ephemeral=True)
            return
        self.config["thresholds"][umbral] = valor
        self.save_config()
        await interaction.response.send_message(f"✅ Umbral `{umbral}` → `{valor}`", ephemeral=True)

    @app_commands.command(name="automod_action", description="⚙️ Configura una acción automática")
    @app_commands.default_permissions(administrator=True)
    async def automod_action(self, interaction: discord.Interaction, accion: str, valor: str):
        if accion not in self.config["actions"]:
            opts = ', '.join(self.config["actions"])
            await interaction.response.send_message(f"❌ Acción inválida. Opciones: `{opts}`", ephemeral=True)
            return
        current = self.config["actions"][accion]
        if isinstance(current, bool):
            self.config["actions"][accion] = valor.lower() in ("true", "1", "sí", "si", "yes")
        else:
            try:
                self.config["actions"][accion] = int(valor)
            except ValueError:
                await interaction.response.send_message("❌ El valor debe ser un número entero.", ephemeral=True)
                return
        self.save_config()
        await interaction.response.send_message(f"✅ Acción `{accion}` → `{self.config['actions'][accion]}`", ephemeral=True)

    @app_commands.command(name="automod_ignore", description="🚫 Ignorar o des-ignorar canal/rol del automod")
    @app_commands.default_permissions(administrator=True)
    async def automod_ignore(self, interaction: discord.Interaction, tipo: str, id_objeto: str):
        tipo = tipo.lower()
        if tipo not in ("channel", "role"):
            await interaction.response.send_message("❌ Tipo inválido. Usa `channel` o `role`.", ephemeral=True)
            return
        try:
            obj_id = int(id_objeto)
        except ValueError:
            await interaction.response.send_message("❌ ID inválido.", ephemeral=True)
            return

        key = "ignored_channels" if tipo == "channel" else "ignored_roles"
        label = f"<#{obj_id}>" if tipo == "channel" else f"<@&{obj_id}>"

        if obj_id in self.config[key]:
            self.config[key].remove(obj_id)
            msg = f"✅ {label} ya **no** ignora el automod."
        else:
            self.config[key].append(obj_id)
            msg = f"✅ {label} ahora **ignora** el automod."

        self.save_config()
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="automod_stats", description="📊 Estadísticas del AutoMod")
    @app_commands.default_permissions(moderate_members=True)
    async def automod_stats(self, interaction: discord.Interaction):
        total = sum(len(v) for v in self.infractions.values())
        users = len(self.infractions)

        top = sorted(self.infractions.items(), key=lambda x: len(x[1]), reverse=True)[:5]

        embed = discord.Embed(title="📊 ESTADÍSTICAS DE AUTOMOD", color=discord.Color.blue(), timestamp=datetime.now())
        embed.add_field(name="⚠️ Total infracciones", value=f"```{total}```", inline=True)
        embed.add_field(name="👥 Usuarios", value=f"```{users}```", inline=True)

        if top:
            lines = []
            for uid, infs in top:
                m = interaction.guild.get_member(int(uid))
                name = m.display_name if m else f"ID {uid}"
                lines.append(f"• **{name}**: {len(infs)}")
            embed.add_field(name="🏆 Top infractores", value="\n".join(lines), inline=False)

        active = [k for k, v in self.config["filters"].items() if v]
        embed.add_field(name="✅ Filtros activos", value="`" + "`, `".join(active) + "`" if active else "Ninguno", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="automod_reset", description="🔄 Reinicia las infracciones de un usuario")
    @app_commands.default_permissions(administrator=True)
    async def automod_reset(self, interaction: discord.Interaction, member: discord.Member):
        uid = str(member.id)
        if uid in self.infractions:
            count = len(self.infractions[uid])
            del self.infractions[uid]
            self.save_infractions()
            await interaction.response.send_message(f"✅ **{count}** infracciones de {member.mention} eliminadas.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {member.mention} no tiene infracciones.", ephemeral=True)

    @app_commands.command(name="automod_whitelist", description="📝 Agrega/quita un dominio de la lista blanca de links")
    @app_commands.default_permissions(administrator=True)
    async def automod_whitelist(self, interaction: discord.Interaction, dominio: str):
        if dominio in self.config["whitelist_links"]:
            self.config["whitelist_links"].remove(dominio)
            msg = f"✅ `{dominio}` eliminado de la lista blanca."
        else:
            self.config["whitelist_links"].append(dominio)
            msg = f"✅ `{dominio}` agregado a la lista blanca."
        self.save_config()
        await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
