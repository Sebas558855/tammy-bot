import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
import logging
from datetime import datetime

from database import db

logger = logging.getLogger('TammyBot.Niveles')

XP_POR_MENSAJE_MIN = 10
XP_POR_MENSAJE_MAX = 25
XP_POR_MINUTO      = 2
COOLDOWN_MENSAJE   = 45
NIVEL_MAXIMO       = 100

def xp_para_nivel(nivel: int) -> int:
    return int(100 * (nivel ** 1.6))

def xp_total_para_nivel(nivel: int) -> int:
    return sum(xp_para_nivel(n) for n in range(1, nivel))

def nivel_desde_xp_total(xp_total: int) -> int:
    nivel = 1
    while nivel < NIVEL_MAXIMO and xp_total >= xp_total_para_nivel(nivel + 1):
        nivel += 1
    return nivel

ROLES_NIVEL: list[tuple] = [
    (1,   "🌱 Semilla Perdida",        discord.Color.from_rgb(134, 187, 110), "Un alma recién llegada al mundo."),
    (5,   "🪨 Vagabundo de Piedra",     discord.Color.from_rgb(150, 130, 110), "Empieza a encontrar su camino."),
    (10,  "🌊 Marinero del Caos",       discord.Color.from_rgb(70,  150, 210), "Navega sin brújula pero con valentía."),
    (15,  "🔥 Llama Errante",           discord.Color.from_rgb(220, 100,  40), "Ardiente pero incontrolable."),
    (20,  "⚡ Chispa Arcana",           discord.Color.from_rgb(180, 100, 255), "Un toque de magia empieza a despertar."),
    (28,  "🦅 Cazador de Nubes",        discord.Color.from_rgb(100, 180, 220), "Vuela alto, sin límites conocidos."),
    (36,  "🌙 Viajero Lunar",           discord.Color.from_rgb(160, 140, 255), "Domina la oscuridad con elegancia."),
    (44,  "🐉 Susurrador de Dragones",  discord.Color.from_rgb(200,  50,  50), "Los monstruos lo escuchan y obedecen."),
    (52,  "⚔️ Forjador de Leyendas",    discord.Color.from_rgb(210, 160,  30), "Su nombre empieza a grabarse en piedra."),
    (60,  "🌌 Explorador del Vacío",    discord.Color.from_rgb( 50,  50, 180), "Ha mirado al abismo y sonrió."),
    (68,  "🔮 Oráculo Fragmentado",     discord.Color.from_rgb(180,  60, 200), "Ve hilos del futuro entre la niebla."),
    (76,  "💀 Portador del Último Eco", discord.Color.from_rgb( 80,  80,  80), "Sobrevivió lo que nadie más pudo."),
    (85,  "☀️ Ascendido Solar",         discord.Color.from_rgb(255, 210,  50), "La luz misma lo reconoce como igual."),
    (93,  "🌀 Arquitecto del Tiempo",   discord.Color.from_rgb(  0, 200, 200), "Moldea los momentos a su voluntad."),
    (100, "👁️ Eterno Sin Nombre",       discord.Color.from_rgb(255, 255, 255), "Ha trascendido toda clasificación conocida."),
]

CANAL_NIVEL_UP: str | None = "💬-general"


class Niveles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cooldowns: dict[int, datetime] = {}
        self.task_xp_pasiva = self.bot.loop.create_task(self._loop_xp_pasiva())

    def cog_unload(self):
        self.task_xp_pasiva.cancel()

    def get_rol_actual(self, nivel: int) -> tuple | None:
        actual = None
        for entry in ROLES_NIVEL:
            if nivel >= entry[0]:
                actual = entry
        return actual

    def get_proximo_rol(self, nivel: int) -> tuple | None:
        for entry in ROLES_NIVEL:
            if nivel < entry[0]:
                return entry
        return None

    def en_cooldown(self, user_id: int) -> bool:
        ahora = datetime.now()
        ultimo = self.cooldowns.get(user_id)
        if ultimo and (ahora - ultimo).total_seconds() < COOLDOWN_MENSAJE:
            return True
        self.cooldowns[user_id] = ahora
        return False

    async def actualizar_rol(self, member: discord.Member, nivel: int):
        guild = member.guild
        todos = [discord.utils.get(guild.roles, name=e[1]) for e in ROLES_NIVEL]
        todos = [r for r in todos if r]
        objetivo_entry = self.get_rol_actual(nivel)
        if not objetivo_entry:
            return
        objetivo = discord.utils.get(guild.roles, name=objetivo_entry[1])
        quitar = [r for r in todos if r in member.roles and r != objetivo]
        if quitar:
            await member.remove_roles(*quitar, reason="Sistema de niveles")
        if objetivo and objetivo not in member.roles:
            await member.add_roles(objetivo, reason=f"Nivel {nivel} alcanzado")

    async def _anunciar_nivel(self, member: discord.Member, nivel: int, canal_origen):
        canal = discord.utils.get(member.guild.text_channels, name=CANAL_NIVEL_UP) if CANAL_NIVEL_UP else canal_origen
        if not canal:
            canal = canal_origen
        if not canal:
            return
        rol_entry = self.get_rol_actual(nivel)
        proximo   = self.get_proximo_rol(nivel)
        embed = discord.Embed(
            title="🎉 ¡SUBIDA DE NIVEL!",
            color=rol_entry[2] if rol_entry else discord.Color.gold(),
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="👤 Usuario", value=member.mention, inline=True)
        embed.add_field(name="⭐ Nivel",   value=f"**{nivel}** / {NIVEL_MAXIMO}", inline=True)
        if rol_entry and nivel == rol_entry[0]:
            embed.add_field(name="🎭 Nuevo rol", value=f"**{rol_entry[1]}**\n*{rol_entry[3]}*", inline=False)
        if proximo:
            embed.add_field(name="🎯 Próximo rol", value=f"`{proximo[1]}` — faltan **{proximo[0] - nivel}** nivel(es)", inline=False)
        else:
            embed.add_field(name="👑 ¡LEYENDA!", value="Has alcanzado el nivel máximo.", inline=False)
        try:
            await canal.send(embed=embed)
        except discord.Forbidden:
            pass

    async def procesar_xp_mensaje(self, member: discord.Member, canal):
        xp_ganada = random.randint(XP_POR_MENSAJE_MIN, XP_POR_MENSAJE_MAX)
        datos     = await db.get_usuario_nivel(member.id, member.guild.id)
        xp_antes  = datos["xp"]
        xp_nueva  = await db.sumar_xp(member.id, member.guild.id, xp_ganada, member.display_name)
        nivel_antes = nivel_desde_xp_total(xp_antes)
        nivel_nuevo = nivel_desde_xp_total(xp_nueva)
        if nivel_nuevo > nivel_antes:
            await self.actualizar_rol(member, nivel_nuevo)
            await self._anunciar_nivel(member, nivel_nuevo, canal)

    async def _loop_xp_pasiva(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(60)
            for guild in self.bot.guilds:
                for member in guild.members:
                    if member.bot or member.status == discord.Status.offline:
                        continue
                    datos    = await db.get_usuario_nivel(member.id, guild.id)
                    xp_antes = datos["xp"]
                    await db.sumar_minutos(member.id, guild.id, member.display_name, XP_POR_MINUTO)
                    xp_nueva    = xp_antes + XP_POR_MINUTO
                    nivel_antes = nivel_desde_xp_total(xp_antes)
                    nivel_nuevo = nivel_desde_xp_total(xp_nueva)
                    if nivel_nuevo > nivel_antes:
                        try:
                            await self.actualizar_rol(member, nivel_nuevo)
                            await self._anunciar_nivel(member, nivel_nuevo, None)
                        except Exception as e:
                            logger.error(f"XP pasiva error {member}: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or len(message.content) < 3:
            return
        if self.en_cooldown(message.author.id):
            return
        await self.procesar_xp_mensaje(message.author, message.channel)

    @app_commands.command(name="nivel", description="📊 Muestra tu nivel o el de otro usuario")
    async def nivel_cmd(self, interaction: discord.Interaction, usuario: discord.Member | None = None):
        member = usuario or interaction.user
        datos  = await db.get_usuario_nivel(member.id, interaction.guild.id)
        xp     = datos["xp"]
        nivel  = nivel_desde_xp_total(xp)
        rol_entry = self.get_rol_actual(nivel)
        proximo   = self.get_proximo_rol(nivel)
        xp_inicio    = xp_total_para_nivel(nivel)
        xp_fin       = xp_total_para_nivel(nivel + 1) if nivel < NIVEL_MAXIMO else xp_inicio + 1
        xp_en_nivel  = xp - xp_inicio
        xp_necesaria = xp_fin - xp_inicio
        porcentaje   = min(100, int((xp_en_nivel / xp_necesaria) * 100)) if xp_necesaria > 0 else 100
        barra        = "█" * (porcentaje // 10) + "░" * (10 - porcentaje // 10)
        embed = discord.Embed(title=f"📊 {member.display_name}",
                              color=rol_entry[2] if rol_entry else discord.Color.blurple(),
                              timestamp=datetime.now())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="⭐ Nivel",       value=f"**{nivel}** / {NIVEL_MAXIMO}",        inline=True)
        embed.add_field(name="✨ XP Total",    value=f"`{xp:,}`",                             inline=True)
        embed.add_field(name="💬 Mensajes",    value=f"`{datos.get('mensajes', 0):,}`",       inline=True)
        embed.add_field(name="⏱️ Min. activo",value=f"`{datos.get('minutos_activo', 0):,}`", inline=True)
        if rol_entry:
            embed.add_field(name="🎭 Rango", value=f"{rol_entry[1]}\n*{rol_entry[3]}*", inline=False)
        embed.add_field(
            name=f"📈 Progreso al nivel {nivel + 1}" if nivel < NIVEL_MAXIMO else "👑 Nivel máximo",
            value=f"`{barra}` {porcentaje}%\n`{xp_en_nivel:,}` / `{xp_necesaria:,}` XP",
            inline=False
        )
        if proximo:
            embed.add_field(name="🎯 Próximo rol", value=f"`{proximo[1]}` al nivel **{proximo[0]}**", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ranking", description="🏆 Top 10 del servidor")
    async def ranking(self, interaction: discord.Interaction):
        await interaction.response.defer()
        top = await db.get_ranking(interaction.guild.id, 10)
        medallas = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
        embed = discord.Embed(title="🏆 RANKING DE NIVELES", color=discord.Color.gold(), timestamp=datetime.now())
        lineas = []
        for i, row in enumerate(top):
            member = interaction.guild.get_member(row["user_id"])
            nombre = member.display_name if member else row.get("nombre", f"ID {row['user_id']}")
            nivel  = nivel_desde_xp_total(row["xp"])
            rol    = self.get_rol_actual(nivel)
            lineas.append(f"{medallas[i]} **{nombre}** — Lv.`{nivel}` · {rol[1] if rol else '?'} · `{row['xp']:,}` XP")
        embed.description = "\n".join(lineas) or "Aún no hay datos."
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="roles_niveles", description="📋 Lista de roles y niveles requeridos")
    async def roles_niveles(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🎭 ROLES POR NIVEL",
                              description="Escribe y sé activo para desbloquearlos.",
                              color=discord.Color.blurple())
        for nivel_req, nombre, color, desc in ROLES_NIVEL:
            rol = discord.utils.get(interaction.guild.roles, name=nombre)
            embed.add_field(
                name=f"Nivel {nivel_req} → {nombre}",
                value=f"{rol.mention if rol else f'`{nombre}`'}\n*{desc}*",
                inline=False
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="niveles_setup", description="⚙️ Crea los 15 roles del sistema (Admin)")
    @app_commands.default_permissions(administrator=True)
    async def niveles_setup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        creados, existentes = 0, 0
        for _, nombre, color, _ in ROLES_NIVEL:
            if discord.utils.get(interaction.guild.roles, name=nombre):
                existentes += 1
                continue
            try:
                await interaction.guild.create_role(name=nombre, color=color, reason="Setup niveles")
                creados += 1
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Error creando rol {nombre}: {e}")
        embed = discord.Embed(title="✅ SISTEMA DE NIVELES LISTO", color=discord.Color.green())
        embed.add_field(name="✨ Roles creados", value=f"`{creados}`",    inline=True)
        embed.add_field(name="⚠️ Ya existían",  value=f"`{existentes}`", inline=True)
        embed.add_field(
            name="📝 Cómo funciona",
            value=(
                f"• **{XP_POR_MENSAJE_MIN}–{XP_POR_MENSAJE_MAX} XP** por mensaje (cooldown {COOLDOWN_MENSAJE}s)\n"
                f"• **{XP_POR_MINUTO} XP** por minuto conectado\n"
                f"• Nivel máximo: **{NIVEL_MAXIMO}**\n"
                f"• **{len(ROLES_NIVEL)} roles** desbloqueables\n"
                f"• Datos guardados en **PostgreSQL** ✅"
            ),
            inline=False
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="dar_xp", description="🎁 Da XP a un usuario (Admin)")
    @app_commands.default_permissions(administrator=True)
    async def dar_xp_cmd(self, interaction: discord.Interaction, usuario: discord.Member, cantidad: int):
        if cantidad <= 0:
            await interaction.response.send_message("❌ Cantidad debe ser positiva.", ephemeral=True)
            return
        datos    = await db.get_usuario_nivel(usuario.id, interaction.guild.id)
        nueva_xp = datos["xp"] + cantidad
        await db.set_xp(usuario.id, interaction.guild.id, nueva_xp)
        nivel = nivel_desde_xp_total(nueva_xp)
        await self.actualizar_rol(usuario, nivel)
        await interaction.response.send_message(f"✅ +**{cantidad:,} XP** a {usuario.mention} · Nivel: **{nivel}**", ephemeral=True)

    @app_commands.command(name="quitar_xp", description="🗑️ Quita XP a un usuario (Admin)")
    @app_commands.default_permissions(administrator=True)
    async def quitar_xp(self, interaction: discord.Interaction, usuario: discord.Member, cantidad: int):
        if cantidad <= 0:
            await interaction.response.send_message("❌ Cantidad debe ser positiva.", ephemeral=True)
            return
        datos    = await db.get_usuario_nivel(usuario.id, interaction.guild.id)
        nueva_xp = max(0, datos["xp"] - cantidad)
        await db.set_xp(usuario.id, interaction.guild.id, nueva_xp)
        nivel = nivel_desde_xp_total(nueva_xp)
        await self.actualizar_rol(usuario, nivel)
        await interaction.response.send_message(f"✅ -**{cantidad:,} XP** a {usuario.mention} · Nivel: **{nivel}**", ephemeral=True)

    @app_commands.command(name="reset_nivel", description="🔄 Reinicia nivel de un usuario (Admin)")
    @app_commands.default_permissions(administrator=True)
    async def reset_nivel(self, interaction: discord.Interaction, usuario: discord.Member):
        await db.reset_usuario_nivel(usuario.id, interaction.guild.id)
        roles_sistema = [discord.utils.get(interaction.guild.roles, name=e[1]) for e in ROLES_NIVEL]
        quitar = [r for r in roles_sistema if r and r in usuario.roles]
        if quitar:
            await usuario.remove_roles(*quitar, reason="Reset de nivel")
        await interaction.response.send_message(f"✅ Nivel de {usuario.mention} reiniciado.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Niveles(bot))
