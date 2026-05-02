# 🤖 TammyBot — Remasterizado

Bot de Discord completo para comunidades de streamers, con IA, moderación automática, tickets y más.

## 📁 Estructura
```
TammyBot_Remaster/
├── main.py                    # Punto de entrada principal
├── requirements.txt           # Dependencias
├── .env.example               # Plantilla de variables de entorno
├── commands/
│   ├── admin.py               # Moderación (mute, ban, kick, warn, etc.)
│   ├── automod.py             # Automoderación inteligente
│   ├── ticket.py              # Sistema de tickets
│   ├── verificar.py           # Verificación CAPTCHA
│   ├── tammy_ia.py            # IA conversacional (Claude API)
│   └── setup_servidor.py      # Setup completo del servidor
└── (archivos JSON de datos generados automáticamente)
```

## 🚀 Instalación

```bash
pip install -r requirements.txt
cp .env.example .env
# Edita .env y agrega tus tokens
python main.py
```

## ⚙️ Variables de entorno (.env)

| Variable | Descripción | Requerida |
|---|---|---|
| `DISCORD_TOKEN` | Token del bot de Discord | ✅ Sí |
| `ANTHROPIC_API_KEY` | Key de la API de Claude (Anthropic) | ⚠️ Opcional |

## 📋 Comandos

### 🛠️ Moderación (`/admin`)
- `/clear <cantidad> [usuario]` — Borrar mensajes
- `/mute <usuario> <tiempo> [razón]` — Silenciar (ej: `10m`, `2h`, `1d`)
- `/unmute <usuario>` — Desilenciar
- `/kick <usuario>` — Expulsar
- `/ban <usuario>` — Banear
- `/unban <user_id>` — Desbanear
- `/warn <usuario>` — Advertir (auto-mute a 3 y 5 warns)
- `/warnings <usuario>` — Ver advertencias
- `/clearwarns <usuario>` — Limpiar advertencias
- `/slowmode <segundos>` — Modo lento
- `/lock` / `/unlock` — Bloquear/desbloquear canal
- `/userinfo [usuario]` — Info de usuario
- `/serverinfo` — Info del servidor
- `/voice_mute` / `/voice_unmute` — Mute de voz

### 🤖 AutoMod (`/automod`)
- `/automod` — Panel de control
- `/automod_filter <filtro> <true/false>` — Activar/desactivar filtro
- `/automod_threshold <umbral> <valor>` — Ajustar sensibilidad
- `/automod_action <acción> <valor>` — Configurar acciones
- `/automod_ignore <channel/role> <id>` — Ignorar canales/roles
- `/automod_stats` — Estadísticas
- `/automod_reset <usuario>` — Reiniciar infracciones
- `/automod_whitelist <dominio>` — Lista blanca de links

### 🎫 Tickets
- `/ticket_setup` — Configura el sistema de tickets
- `/ticket_close` — Cierra el ticket actual
- `/ticket_stats` — Estadísticas de tickets

### ✅ Verificación
- `/verificar` — Verificación CAPTCHA con Modal
- `/reset_verificacion <usuario>` — Quitar verificación
- `/stats_verificacion` — Estadísticas

### 🧠 Tammy IA
- `/tammy <pregunta>` — Preguntar a Tammy
- `/tammy_reset` — Borrar historial
- `/tammy_status` — Estado de la IA
- `/tammy_config <opción> <valor>` — Configurar

### ⚙️ Setup
- `/setup_servidor` — Reconstruir servidor completo (¡DESTRUCTIVO!)

---

## 🔧 Cambios en la remasterización

### Bugs críticos corregidos:
- `ConfirmBanView` y `unban` estaban dentro de `ConfirmKickView` (fuera del cog) — **corregido**
- `wait_for` en la verificación fallaba con mensajes efímeros — **reemplazado por Modal**
- Vistas persistentes de tickets con `custom_id` duplicados entre archivos — **unificado**
- `clear_until` no funcionaba correctamente — **corregido con `after` en lugar de `before`**

### Mejoras de arquitectura:
- `TammyBot` ahora es una clase propia que hereda de `commands.Bot`
- `setup_hook` carga los cogs antes de conectar (más seguro)
- Logging completo con archivo `bot.log`
- Type hints en todos los métodos
- Manejo de errores granular con `try/except` específicos

### Mejoras de funcionalidad:
- Verificación ahora usa **Modal** de Discord (sin `wait_for` frágil)
- `tammy_ia.py` usa **Claude API** en lugar de Ollama local
- `setup_servidor.py` requiere confirmación antes de ejecutarse
- AutoMod: detección de spam en memoria (sin historial de canal)
- AutoMod: detección de Zalgo mejorada con `unicodedata`
- `admin.py`: `/ban` y `/unban` correctamente dentro del cog
- Todos los comandos usan `app_commands.Range` para validación de rangos
