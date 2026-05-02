import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger('TammyBot.Setup')

# Importar las vistas del sistema de tickets
from commands.ticket import TicketView, CloseTicketView


class SetupServidor(commands.Cog):
    """Comando para configurar la estructura completa del servidor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="setup_servidor",
        description="⚙️ Elimina todo y reconstruye la estructura completa del servidor (¡DESTRUCTIVO!)"
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_servidor(self, interaction: discord.Interaction):
        # Confirmación de seguridad
        embed_warn = discord.Embed(
            title="⚠️ ADVERTENCIA — OPERACIÓN DESTRUCTIVA",
            description=(
                "Este comando **ELIMINARÁ** todos los canales, categorías y roles del servidor.\n\n"
                "Escribe `CONFIRMAR` en el chat en los próximos 20 segundos para continuar."
            ),
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed_warn, ephemeral=False)

        def check(m: discord.Message):
            return m.author == interaction.user and m.channel == interaction.channel and m.content == "CONFIRMAR"

        try:
            confirm_msg = await self.bot.wait_for("message", timeout=20.0, check=check)
            await confirm_msg.delete()
        except asyncio.TimeoutError:
            await interaction.followup.send("❌ Configuración cancelada por tiempo de espera.", ephemeral=True)
            return

        await interaction.followup.send("🔄 Iniciando configuración... esto puede tardar un minuto.", ephemeral=True)
        guild = interaction.guild

        # ============================================================
        # PASO 1: Limpiar servidor
        # ============================================================
        logger.info(f"[Setup] Eliminando canales de {guild.name}...")
        for channel in list(guild.channels):
            try:
                await channel.delete()
                await asyncio.sleep(0.15)
            except Exception:
                pass

        logger.info("[Setup] Eliminando roles...")
        for role in list(guild.roles):
            if role.name != "@everyone" and not role.managed:
                try:
                    await role.delete()
                    await asyncio.sleep(0.15)
                except Exception:
                    pass

        await asyncio.sleep(1)

        # ============================================================
        # PASO 2: Crear roles
        # ============================================================
        logger.info("[Setup] Creando roles...")
        r_owner = await guild.create_role(name="👑 Owner", color=discord.Color.gold(), hoist=True, mentionable=False)
        r_admin = await guild.create_role(name="⚜️ Admin", color=discord.Color.red(), hoist=True, mentionable=True)
        r_mod = await guild.create_role(name="🛡️ Moderador", color=discord.Color.green(), hoist=True, mentionable=True)
        r_helper = await guild.create_role(name="🤝 Helper", color=discord.Color.teal(), hoist=True, mentionable=True)
        r_verified = await guild.create_role(name="✅ Verificado", color=discord.Color.from_rgb(50, 205, 50))
        r_miembro = await guild.create_role(name="🎮 Miembro", color=discord.Color.dark_gray())
        r_vip = await guild.create_role(name="💎 VIP", color=discord.Color.purple())
        r_subs = await guild.create_role(name="🔴 Suscriptor", color=discord.Color.red())
        r_niv1 = await guild.create_role(name="⭐ Nivel 1", color=discord.Color.light_gray())
        r_niv2 = await guild.create_role(name="⭐⭐ Nivel 2", color=discord.Color.green())
        r_niv3 = await guild.create_role(name="⭐⭐⭐ Nivel 3", color=discord.Color.blue())
        r_notif = await guild.create_role(name="📣 Notificaciones", color=discord.Color.orange())

        # Ordenar roles por jerarquía
        ordered = [r_owner, r_admin, r_mod, r_helper, r_verified,
                   r_subs, r_vip, r_niv3, r_niv2, r_niv1, r_miembro, r_notif]
        for i, role in enumerate(ordered):
            try:
                await role.edit(position=max(1, len(ordered) - i))
                await asyncio.sleep(0.2)
            except Exception as e:
                logger.warning(f"No se pudo ordenar rol {role.name}: {e}")

        # ============================================================
        # PASO 3: Crear categorías y canales
        # ============================================================
        logger.info("[Setup] Creando categorías y canales...")

        # Shortcut para permisos
        no_access = discord.PermissionOverwrite(read_messages=False)
        view_only = discord.PermissionOverwrite(read_messages=True, send_messages=False)
        full_access = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        voice_access = discord.PermissionOverwrite(read_messages=True, connect=True, speak=True)
        staff_perm = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)

        # -- BIENVENIDA --
        cat_bienvenida = await guild.create_category("🏠 BIENVENIDA", overwrites={
            guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False)
        })
        ch_verif = await guild.create_text_channel("✅-verificacion", category=cat_bienvenida, overwrites={
            guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            r_verified: view_only
        })
        ch_bienvenida = await guild.create_text_channel("👋-bienvenida", category=cat_bienvenida, overwrites={
            guild.default_role: view_only
        })
        ch_despedida = await guild.create_text_channel("👋-despedida", category=cat_bienvenida, overwrites={
            guild.default_role: view_only
        })

        # -- INFORMACIÓN --
        cat_info = await guild.create_category("📜 INFORMACIÓN", overwrites={
            guild.default_role: no_access,
            r_verified: view_only
        })
        ch_reglas = await guild.create_text_channel("📜-reglas", category=cat_info)
        ch_info_roles = await guild.create_text_channel("📌-info-roles", category=cat_info)
        ch_canjear = await guild.create_text_channel("🎭-canjear-roles", category=cat_info, overwrites={
            guild.default_role: no_access,
            r_verified: full_access
        })

        # -- STAFF --
        cat_staff = await guild.create_category("👔 STAFF", overwrites={
            guild.default_role: no_access,
            r_verified: no_access,
            r_mod: staff_perm,
            r_admin: staff_perm,
            r_owner: staff_perm
        })
        ch_staff_chat = await guild.create_text_channel("🔒-staff-chat", category=cat_staff)
        ch_reportes = await guild.create_text_channel("📋-reportes", category=cat_staff)
        ch_logs = await guild.create_text_channel("📜-logs", category=cat_staff, overwrites={
            guild.default_role: no_access,
            r_mod: discord.PermissionOverwrite(read_messages=True, send_messages=False),
            r_admin: staff_perm,
            r_owner: staff_perm
        })

        # -- COMUNIDAD --
        cat_comunidad = await guild.create_category("💬 COMUNIDAD", overwrites={
            guild.default_role: no_access,
            r_verified: full_access
        })
        ch_general = await guild.create_text_channel("💬-general", category=cat_comunidad)
        ch_memes = await guild.create_text_channel("😂-memes", category=cat_comunidad)
        ch_media = await guild.create_text_channel("🖼️-media", category=cat_comunidad)
        ch_sugerencias = await guild.create_text_channel("💡-sugerencias", category=cat_comunidad)

        # -- STREAMER --
        cat_streamer = await guild.create_category("📺 STREAMER", overwrites={
            guild.default_role: no_access,
            r_verified: view_only
        })
        ch_anuncios = await guild.create_text_channel("📢-anuncios", category=cat_streamer, overwrites={
            guild.default_role: no_access,
            r_verified: view_only,
            r_notif: view_only,
            r_admin: staff_perm,
            r_owner: staff_perm
        })
        ch_contenido = await guild.create_text_channel("📹-contenido", category=cat_streamer, overwrites={
            guild.default_role: no_access,
            r_verified: view_only,
            r_owner: full_access
        })
        ch_ideas = await guild.create_text_channel("💡-ideas-contenido", category=cat_streamer, overwrites={
            guild.default_role: no_access,
            r_verified: full_access
        })

        # -- EVENTOS --
        cat_eventos = await guild.create_category("🎉 EVENTOS", overwrites={
            guild.default_role: no_access,
            r_verified: view_only
        })
        ch_sorteos = await guild.create_text_channel("🎁-sorteos", category=cat_eventos)
        ch_eventos = await guild.create_text_channel("📅-eventos", category=cat_eventos)

        # -- TICKETS --
        cat_tickets = await guild.create_category("🎫 TICKETS", overwrites={
            guild.default_role: no_access,
            r_verified: no_access,
            r_mod: staff_perm,
            r_admin: staff_perm,
            r_owner: staff_perm
        })
        ch_ticket = await guild.create_text_channel("🎫-abrir-ticket", category=cat_tickets, overwrites={
            guild.default_role: no_access,
            r_verified: view_only
        })

        # -- VOZ --
        cat_voz = await guild.create_category("🎤 CANALES DE VOZ", overwrites={
            guild.default_role: no_access,
            r_verified: voice_access
        })
        vc_general = await guild.create_voice_channel("🔊 General", category=cat_voz)
        vc_gaming = await guild.create_voice_channel("🎮 Gaming", category=cat_voz)
        vc_afk = await guild.create_voice_channel("💤 AFK", category=cat_voz, overwrites={
            guild.default_role: no_access,
            r_verified: discord.PermissionOverwrite(connect=True, speak=False)
        })

        # ============================================================
        # PASO 4: Publicar contenido inicial
        # ============================================================
        logger.info("[Setup] Publicando mensajes iniciales...")

        # Verificación
        e_verif = discord.Embed(
            title="✅ SISTEMA DE VERIFICACIÓN",
            description="**Para acceder al servidor completo, debes verificar que no eres un bot.**",
            color=discord.Color.blue()
        )
        e_verif.add_field(
            name="🔹 ¿Cómo?",
            value="Escribe `/verificar` aquí mismo.\nAparece un código → ingresalo → ¡listo!",
            inline=False
        )
        e_verif.add_field(name="⚠️ Tiempo límite", value="60 segundos por intento.", inline=True)
        e_verif.set_footer(text="Solo necesitas verificarte una vez")
        await ch_verif.send(embed=e_verif)

        await ch_bienvenida.send(
            f"👋 **¡Bienvenido a {guild.name}!**\n\n"
            f"> Verifica en {ch_verif.mention} para ver todos los canales.\n"
            f"> ¡Disfruta tu estadía! 🎉"
        )
        await ch_despedida.send(f"👋 **¡Hasta pronto! Te extrañaremos.**\n\n> Si tienes feedback, déjalo en {ch_sugerencias.mention}")

        # Reglas
        e_reglas = discord.Embed(title="📜 REGLAS DEL SERVIDOR", color=discord.Color.red())
        e_reglas.add_field(name="1️⃣ RESPETO", value="Trata a todos con respeto. Sin insultos ni acoso.", inline=False)
        e_reglas.add_field(name="2️⃣ SPAM", value="No spam, flood ni publicidad no autorizada.", inline=False)
        e_reglas.add_field(name="3️⃣ CONTENIDO", value="Nada de NSFW, gore ni contenido ilegal.", inline=False)
        e_reglas.add_field(name="4️⃣ STREAMER", value="Respeta al streamer y a su equipo.", inline=False)
        e_reglas.add_field(name="⚖️ SANCIONES", value="1ra: Advertencia · 2da: Mute · 3ra: Expulsión", inline=False)
        await ch_reglas.send(embed=e_reglas)

        # Info roles
        e_roles = discord.Embed(title="📌 ROLES DEL SERVIDOR", color=discord.Color.purple())
        e_roles.add_field(name="👔 Staff", value="```👑 Owner · ⚜️ Admin · 🛡️ Moderador · 🤝 Helper```", inline=False)
        e_roles.add_field(
            name="🎮 Roles canjeables",
            value=f"Visita {ch_canjear.mention} y usa:\n`/rol Miembro` · `/rol VIP` · `/rol Suscriptor` · `/rol Notificaciones`",
            inline=False
        )
        await ch_info_roles.send(embed=e_roles)

        # Canjear roles
        e_canjear = discord.Embed(title="🎭 SISTEMA DE ROLES", color=discord.Color.blue())
        e_canjear.add_field(name="📝 Comandos", value="```\n/rol Miembro\n/rol VIP\n/rol Suscriptor\n/rol Notificaciones\n```", inline=False)
        await ch_canjear.send(embed=e_canjear)

        # Canales de comunidad
        await ch_general.send("💬 **Chat general** — habla de lo que quieras con respeto.")
        await ch_memes.send("😂 **Memes** — sin contenido NSFW.")
        await ch_media.send("🖼️ **Media** — comparte capturas, clips y arte.")
        await ch_sugerencias.send("💡 **Sugerencias** — ayúdanos a mejorar el servidor.")

        # Streamer
        e_anuncios = discord.Embed(title="📢 ANUNCIOS", description="Aquí se publican todos los anuncios importantes.", color=discord.Color.gold())
        await ch_anuncios.send(embed=e_anuncios)
        e_contenido = discord.Embed(title="📹 CONTENIDO", description="El streamer publicará aquí su contenido.", color=discord.Color.red())
        await ch_contenido.send(embed=e_contenido)
        e_ideas = discord.Embed(title="💡 IDEAS DE CONTENIDO", description="Sugiere ideas al streamer aquí.", color=discord.Color.purple())
        await ch_ideas.send(embed=e_ideas)

        # Tickets
        e_tickets = discord.Embed(title="🎫 SISTEMA DE TICKETS", description="**¿Necesitas ayuda? ¡Abre un ticket!**", color=discord.Color.blue())
        e_tickets.add_field(name="📝 Para qué sirve", value="• Reportar problemas\n• Consultas al staff\n• Reportar usuarios\n• Sugerencias privadas", inline=False)
        e_tickets.add_field(name="⚙️ Cómo funciona", value="Presiona el botón de abajo. Se creará un canal privado donde el staff te atenderá.", inline=False)
        e_tickets.set_footer(text="El staff verá todos los tickets")
        await ch_ticket.send(embed=e_tickets, view=TicketView(self.bot))

        # Eventos
        e_sorteos = discord.Embed(title="🎁 SORTEOS", description="¡Participa y gana premios!", color=discord.Color.gold())
        await ch_sorteos.send(embed=e_sorteos)
        e_eventos = discord.Embed(title="📅 EVENTOS", description="Calendario de eventos de la comunidad.", color=discord.Color.purple())
        await ch_eventos.send(embed=e_eventos)

        # Staff
        await ch_staff_chat.send("🔒 **Chat del staff** — coordinación interna.")
        await ch_reportes.send("📋 **Reportes** — guarda aquí evidencias de infracciones.")
        await ch_logs.send("📜 **Logs** — el bot registrará automáticamente las acciones aquí.")

        # ============================================================
        # PASO 5: Resumen final
        # ============================================================
        e_final = discord.Embed(
            title="✅ SERVIDOR CONFIGURADO",
            description=f"Estructura creada por **{interaction.user.display_name}**\n`{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}`",
            color=discord.Color.green()
        )
        e_final.add_field(name="🎭 Roles creados", value=f"`{len(ordered)}` roles", inline=True)
        e_final.add_field(name="📁 Categorías", value="8 categorías", inline=True)
        e_final.add_field(name="📝 Canales", value="Texto + Voz configurados", inline=True)
        e_final.add_field(
            name="📝 Próximos pasos",
            value=(
                "1. Asigna el rol `👑 Owner` a ti mismo\n"
                "2. El bot necesita estar arriba en la jerarquía de roles\n"
                "3. Usa `/ticket_setup` si el sistema de tickets no arrancó\n"
                "4. Configura el bot de bienvenida/despedida si tienes uno"
            ),
            inline=False
        )
        await interaction.followup.send(embed=e_final, ephemeral=True)
        logger.info(f"[Setup] Configuración completada para {guild.name}")


async def setup(bot: commands.Bot):
    await bot.add_cog(SetupServidor(bot))
