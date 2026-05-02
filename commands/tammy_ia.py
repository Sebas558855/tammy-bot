import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import json
import asyncio
import re
import random
import os
import logging
from datetime import datetime, timedelta

logger = logging.getLogger('TammyBot.IA')

SYSTEM_PROMPT = """Eres Tammy, una asistente virtual inteligente y amigable que vive en un servidor de Discord.

PERSONALIDAD:
- Nombre: Tammy (pronombres: ella/ella)
- Tono: cálido, amigable, ingenioso y útil
- Idioma principal: ESPAÑOL (siempre responde en español a menos que te hablen en otro idioma)
- Puedes responder sobre: matemáticas, ciencia, programación, historia, cultura, chistes, consejos, etc.

REGLAS DE RESPUESTA:
1. Sé concisa — las respuestas largas se cortan. Máximo 3-4 párrafos.
2. Usa emojis con moderación (1-2 por respuesta máximo)
3. Si no sabes algo, dilo con honestidad
4. No inventes datos ni estadísticas
5. Mantén el historial de conversación para respuestas coherentes
6. Para preguntas de programación, usa bloques de código si es necesario

EJEMPLO DE RESPUESTA BUENA:
Usuario: "¿Cuánto es 15 * 8?"
Tammy: "15 × 8 = 120. ¿Necesitas ayuda con algo más?"

EJEMPLO DE RESPUESTA MALA:
Tammy: "¡Hola! ¡Qué buena pregunta! ¡Me encanta la matemática! Permíteme calcular eso para ti con mucho gusto..."
"""


class TammyIA(commands.Cog):
    """IA conversacional potenciada por Claude API."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conversations: dict[int, list[dict]] = {}  # user_id -> historial
        self.cooldowns: dict[int, datetime] = {}
        self.config = {
            "max_history": 15,
            "cooldown_seconds": 3,
            "typing_effect": True,
            "max_response_length": 1800,
        }
        self.load_config()

    # ==================== CONFIGURACIÓN ====================

    def load_config(self):
        try:
            with open("tammy_config.json", "r", encoding="utf-8") as f:
                self.config.update(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            self.save_config()

    def save_config(self):
        with open("tammy_config.json", "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)

    # ==================== LÓGICA DE IA ====================

    async def ask_claude(self, user_message: str, user_name: str, history: list[dict]) -> str | None:
        """Consulta la API de Anthropic (Claude)."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return None

        # Construir mensajes con historial
        messages = []
        for entry in history[-self.config["max_history"]:]:
            messages.append({"role": entry["role"], "content": entry["content"]})
        messages.append({"role": "user", "content": f"{user_name}: {user_message}"})

        payload = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 400,
            "system": SYSTEM_PROMPT,
            "messages": messages
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["content"][0]["text"].strip()
                    else:
                        err = await resp.text()
                        logger.error(f"Error API Claude ({resp.status}): {err[:200]}")
                        return None
        except asyncio.TimeoutError:
            logger.warning("Timeout consultando API de Claude")
            return None
        except Exception as e:
            logger.error(f"Error en ask_claude: {e}")
            return None

    def get_fallback_response(self, message: str, user_name: str) -> str:
        """Respuestas de emergencia cuando la API no está disponible."""
        msg = message.lower()

        # Matemáticas básicas inline
        nums = re.findall(r'\d+(?:\.\d+)?', msg)
        if len(nums) >= 2:
            a, b = float(nums[0]), float(nums[1])
            if any(op in msg for op in ['+', 'más', 'suma']):
                return f"{a} + {b} = **{a + b}**"
            elif any(op in msg for op in ['-', 'menos', 'resta']):
                return f"{a} - {b} = **{a - b}**"
            elif any(op in msg for op in ['*', 'x', '×', 'por', 'multiplica']):
                return f"{a} × {b} = **{a * b}**"
            elif any(op in msg for op in ['/', '÷', 'dividido', 'divide']):
                if b != 0:
                    return f"{a} ÷ {b} = **{a / b:.4g}**"

        if any(w in msg for w in ['hola', 'hey', 'buenas', 'saludos']):
            return f"¡Hola {user_name}! 👋 ¿En qué te puedo ayudar hoy?"

        if 'chiste' in msg or 'broma' in msg:
            chistes = [
                "¿Por qué los programadores prefieren el modo oscuro? ¡Porque la luz atrae a los bugs! 🐛",
                "Un SQL entra a un bar y le pregunta al camarero: '¿Me traes una cerveza?'\nEl camarero: 'Error: columna cerveza no encontrada.'",
                "¿Cómo se llama el primo de Batman que trabaja en soporte técnico? ¡Restartman!"
            ]
            return random.choice(chistes)

        if any(w in msg for w in ['gracias', 'thank', 'grax']):
            return f"¡De nada, {user_name}! 😊 ¿Hay algo más en lo que pueda ayudarte?"

        if any(w in msg for w in ['adios', 'adiós', 'chao', 'bye', 'hasta luego']):
            return f"¡Hasta luego, {user_name}! Fue un gusto hablar contigo. 👋"

        return f"Interesante pregunta, {user_name}. En este momento estoy teniendo problemas para conectarme. ¿Podrías intentarlo de nuevo en un momento?"

    async def get_response(self, user_message: str, user_name: str, user_id: int) -> str:
        history = self.conversations.get(user_id, [])
        response = await self.ask_claude(user_message, user_name, history)
        if not response:
            response = self.get_fallback_response(user_message, user_name)

        # Limitar longitud
        if len(response) > self.config["max_response_length"]:
            response = response[:self.config["max_response_length"]] + "…"
        return response

    def update_history(self, user_id: int, role: str, content: str):
        if user_id not in self.conversations:
            self.conversations[user_id] = []
        self.conversations[user_id].append({"role": role, "content": content})
        # Mantener solo los últimos N mensajes (por pares)
        max_msgs = self.config["max_history"] * 2
        if len(self.conversations[user_id]) > max_msgs:
            self.conversations[user_id] = self.conversations[user_id][-max_msgs:]

    def is_on_cooldown(self, user_id: int) -> int:
        """Retorna segundos restantes de cooldown, o 0 si puede hablar."""
        if user_id in self.cooldowns:
            elapsed = (datetime.now() - self.cooldowns[user_id]).total_seconds()
            remaining = self.config["cooldown_seconds"] - elapsed
            if remaining > 0:
                return int(remaining) + 1
        self.cooldowns[user_id] = datetime.now()
        return 0

    # ==================== LISTENER ====================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Solo responde cuando la mencionan
        if message.author.bot:
            return
        if message.guild is None:
            return
        if self.bot.user not in message.mentions:
            return

        # Cooldown
        wait = self.is_on_cooldown(message.author.id)
        if wait > 0:
            await message.reply(f"⏳ Espera **{wait}s** antes de preguntarme de nuevo.", mention_author=False)
            return

        # Limpiar mención del mensaje
        clean = re.sub(rf'<@!?{self.bot.user.id}>', '', message.content).strip()
        if not clean:
            await message.reply(
                f"¡Hola {message.author.display_name}! 👋 Soy **Tammy**. Pregúntame lo que quieras — matemáticas, programación, chistes, o cualquier cosa.",
                mention_author=False
            )
            return

        # Efecto de escritura
        if self.config["typing_effect"]:
            async with message.channel.typing():
                response = await self.get_response(clean, message.author.display_name, message.author.id)
        else:
            response = await self.get_response(clean, message.author.display_name, message.author.id)

        self.update_history(message.author.id, "user", clean)
        self.update_history(message.author.id, "assistant", response)

        await message.reply(response, mention_author=False)

    # ==================== COMANDOS ====================

    @app_commands.command(name="tammy", description="💬 Pregúntale algo a Tammy (IA)")
    async def tammy_chat(self, interaction: discord.Interaction, pregunta: str):
        await interaction.response.defer()

        if self.config["typing_effect"]:
            async with interaction.channel.typing():
                response = await self.get_response(pregunta, interaction.user.display_name, interaction.user.id)
        else:
            response = await self.get_response(pregunta, interaction.user.display_name, interaction.user.id)

        self.update_history(interaction.user.id, "user", pregunta)
        self.update_history(interaction.user.id, "assistant", response)

        embed = discord.Embed(
            title="🤖 Tammy",
            description=response,
            color=discord.Color.magenta(),
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"Preguntado por {interaction.user.display_name}")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="tammy_reset", description="🔄 Borra el historial de conversación con Tammy")
    async def tammy_reset(self, interaction: discord.Interaction):
        if interaction.user.id in self.conversations:
            del self.conversations[interaction.user.id]
            await interaction.response.send_message("✅ Historial borrado. ¡Empecemos de cero!", ephemeral=True)
        else:
            await interaction.response.send_message("✨ No tienes historial guardado.", ephemeral=True)

    @app_commands.command(name="tammy_status", description="📊 Estado y estadísticas de Tammy")
    async def tammy_status(self, interaction: discord.Interaction):
        has_api = bool(os.getenv("ANTHROPIC_API_KEY"))
        embed = discord.Embed(title="📊 ESTADO DE TAMMY", color=discord.Color.purple(), timestamp=datetime.now())
        embed.add_field(name="🤖 Proveedor IA", value=f"```{'Claude API (Anthropic)' if has_api else 'Modo fallback (sin API key)'}```", inline=False)
        embed.add_field(name="🟢 Estado", value=f"```{'Conectada' if has_api else 'Parcial (sin ANTHROPIC_API_KEY)'}```", inline=True)
        embed.add_field(name="💬 Conversaciones activas", value=f"```{len(self.conversations)}```", inline=True)
        embed.add_field(name="⏰ Cooldown", value=f"```{self.config['cooldown_seconds']}s```", inline=True)
        embed.add_field(name="📝 Historial por usuario", value=f"```{self.config['max_history']} mensajes```", inline=True)
        if not has_api:
            embed.add_field(
                name="⚠️ Para activar Claude IA",
                value="Agrega `ANTHROPIC_API_KEY=tu_key` al archivo `.env`",
                inline=False
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="tammy_config", description="⚙️ Configura Tammy (Admin)")
    @app_commands.default_permissions(administrator=True)
    async def tammy_config(self, interaction: discord.Interaction, opcion: str, valor: str):
        """
        Opciones disponibles:
        - cooldown: segundos entre respuestas (1-60)
        - history: mensajes de historial por usuario (5-30)
        - typing: efecto de escritura (true/false)
        """
        if opcion == "cooldown":
            try:
                v = max(1, min(60, int(valor)))
                self.config["cooldown_seconds"] = v
                await interaction.response.send_message(f"✅ Cooldown → `{v}s`", ephemeral=True)
            except ValueError:
                await interaction.response.send_message("❌ Valor debe ser un número entre 1 y 60.", ephemeral=True)
                return

        elif opcion == "history":
            try:
                v = max(5, min(30, int(valor)))
                self.config["max_history"] = v
                await interaction.response.send_message(f"✅ Historial → `{v} mensajes`", ephemeral=True)
            except ValueError:
                await interaction.response.send_message("❌ Valor debe ser entre 5 y 30.", ephemeral=True)
                return

        elif opcion == "typing":
            self.config["typing_effect"] = valor.lower() in ("true", "1", "sí", "si", "yes")
            await interaction.response.send_message(f"✅ Efecto de escritura → `{self.config['typing_effect']}`", ephemeral=True)

        else:
            await interaction.response.send_message(
                "❌ Opción inválida. Usa: `cooldown`, `history`, `typing`", ephemeral=True
            )
            return

        self.save_config()


async def setup(bot: commands.Bot):
    await bot.add_cog(TammyIA(bot))
