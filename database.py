"""
==============================================================
  database.py — Gestor de base de datos para TammyBot
  Motor: PostgreSQL (via asyncpg)
  Compatible con: Railway, Supabase, ElephantSQL, local
==============================================================
"""

import asyncpg
import os
import json
import logging
from datetime import datetime

logger = logging.getLogger('TammyBot.Database')

# La URL de conexión viene de la variable de entorno DATABASE_URL
# Railway la pone automáticamente cuando agregas el plugin de PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL")


class Database:
    """Clase singleton que gestiona todas las operaciones con PostgreSQL."""

    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        """Conecta al pool de PostgreSQL y crea las tablas si no existen."""
        if not DATABASE_URL:
            raise RuntimeError(
                "❌ Variable DATABASE_URL no encontrada.\n"
                "   Agrega el plugin PostgreSQL en Railway o define DATABASE_URL en tu .env"
            )
        try:
            self.pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=2,
                max_size=10,
                command_timeout=30,
                # Railway usa SSL por defecto
                ssl="require" if "railway" in DATABASE_URL else None
            )
            await self._crear_tablas()
            logger.info("✅ Conexión a PostgreSQL establecida")
        except Exception as e:
            logger.critical(f"❌ Error conectando a PostgreSQL: {e}")
            raise

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            logger.info("🔌 Conexión a PostgreSQL cerrada")

    # ==============================================================
    #   CREACIÓN DE TABLAS
    # ==============================================================

    async def _crear_tablas(self):
        """Crea todas las tablas necesarias si no existen."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                -- ── NIVELES ──────────────────────────────────────────
                CREATE TABLE IF NOT EXISTS niveles (
                    user_id         BIGINT      NOT NULL,
                    guild_id        BIGINT      NOT NULL,
                    xp              INTEGER     NOT NULL DEFAULT 0,
                    mensajes        INTEGER     NOT NULL DEFAULT 0,
                    minutos_activo  INTEGER     NOT NULL DEFAULT 0,
                    nombre          TEXT,
                    ultimo_mensaje  TIMESTAMP,
                    PRIMARY KEY (user_id, guild_id)
                );

                -- ── ADVERTENCIAS ─────────────────────────────────────
                CREATE TABLE IF NOT EXISTS advertencias (
                    id              SERIAL      PRIMARY KEY,
                    user_id         BIGINT      NOT NULL,
                    guild_id        BIGINT      NOT NULL,
                    razon           TEXT        NOT NULL,
                    moderador_id    BIGINT      NOT NULL,
                    moderador_nombre TEXT,
                    fecha           TIMESTAMP   NOT NULL DEFAULT NOW()
                );

                -- ── INFRACCIONES AUTOMOD ──────────────────────────────
                CREATE TABLE IF NOT EXISTS automod_infracciones (
                    id              SERIAL      PRIMARY KEY,
                    user_id         BIGINT      NOT NULL,
                    guild_id        BIGINT      NOT NULL,
                    razon           TEXT        NOT NULL,
                    fecha           TIMESTAMP   NOT NULL DEFAULT NOW()
                );

                -- ── TICKETS ──────────────────────────────────────────
                CREATE TABLE IF NOT EXISTS tickets (
                    id              SERIAL      PRIMARY KEY,
                    canal_nombre    TEXT        NOT NULL,
                    guild_id        BIGINT      NOT NULL,
                    user_id         BIGINT      NOT NULL,
                    cerrado_por_id  BIGINT,
                    cerrado_por     TEXT,
                    cerrado_en      TIMESTAMP,
                    transcripcion   JSONB,
                    abierto         BOOLEAN     NOT NULL DEFAULT TRUE
                );

                -- ── CONFIGURACIÓN POR SERVIDOR ────────────────────────
                CREATE TABLE IF NOT EXISTS config_servidor (
                    guild_id        BIGINT      PRIMARY KEY,
                    config          JSONB       NOT NULL DEFAULT '{}'
                );

                -- ── ÍNDICES para búsquedas rápidas ───────────────────
                CREATE INDEX IF NOT EXISTS idx_niveles_guild    ON niveles (guild_id);
                CREATE INDEX IF NOT EXISTS idx_niveles_xp       ON niveles (xp DESC);
                CREATE INDEX IF NOT EXISTS idx_advertencias_user ON advertencias (user_id, guild_id);
                CREATE INDEX IF NOT EXISTS idx_automod_user     ON automod_infracciones (user_id, guild_id);
            """)
        logger.info("✅ Tablas verificadas/creadas correctamente")

    # ==============================================================
    #   NIVELES
    # ==============================================================

    async def get_usuario_nivel(self, user_id: int, guild_id: int) -> dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM niveles WHERE user_id=$1 AND guild_id=$2",
                user_id, guild_id
            )
            if row:
                return dict(row)
            return {
                "user_id": user_id, "guild_id": guild_id,
                "xp": 0, "mensajes": 0, "minutos_activo": 0,
                "nombre": None, "ultimo_mensaje": None
            }

    async def upsert_usuario_nivel(
        self, user_id: int, guild_id: int,
        xp: int, mensajes: int, minutos_activo: int,
        nombre: str, ultimo_mensaje: datetime | None = None
    ):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO niveles (user_id, guild_id, xp, mensajes, minutos_activo, nombre, ultimo_mensaje)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (user_id, guild_id) DO UPDATE SET
                    xp             = EXCLUDED.xp,
                    mensajes       = EXCLUDED.mensajes,
                    minutos_activo = EXCLUDED.minutos_activo,
                    nombre         = EXCLUDED.nombre,
                    ultimo_mensaje = EXCLUDED.ultimo_mensaje
            """, user_id, guild_id, xp, mensajes, minutos_activo, nombre, ultimo_mensaje)

    async def sumar_xp(self, user_id: int, guild_id: int, xp_ganada: int, nombre: str) -> int:
        """Suma XP directamente en la BD y retorna la XP total nueva."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO niveles (user_id, guild_id, xp, mensajes, nombre, ultimo_mensaje)
                VALUES ($1, $2, $3, 1, $4, NOW())
                ON CONFLICT (user_id, guild_id) DO UPDATE SET
                    xp             = niveles.xp + $3,
                    mensajes       = niveles.mensajes + 1,
                    nombre         = $4,
                    ultimo_mensaje = NOW()
                RETURNING xp
            """, user_id, guild_id, xp_ganada, nombre)
            return row["xp"]

    async def sumar_minutos(self, user_id: int, guild_id: int, nombre: str, xp_pasiva: int):
        """Suma minutos de actividad y XP pasiva."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO niveles (user_id, guild_id, xp, minutos_activo, nombre)
                VALUES ($1, $2, $3, 1, $4)
                ON CONFLICT (user_id, guild_id) DO UPDATE SET
                    xp             = niveles.xp + $3,
                    minutos_activo = niveles.minutos_activo + 1,
                    nombre         = $4
            """, user_id, guild_id, xp_pasiva, nombre)

    async def get_ranking(self, guild_id: int, limite: int = 10) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT user_id, xp, mensajes, minutos_activo, nombre
                FROM niveles
                WHERE guild_id = $1
                ORDER BY xp DESC
                LIMIT $2
            """, guild_id, limite)
            return [dict(r) for r in rows]

    async def set_xp(self, user_id: int, guild_id: int, xp: int):
        """Fija la XP de un usuario (para dar/quitar XP como admin)."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO niveles (user_id, guild_id, xp)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, guild_id) DO UPDATE SET xp = $3
            """, user_id, guild_id, max(0, xp))

    async def reset_usuario_nivel(self, user_id: int, guild_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE niveles SET xp=0, mensajes=0, minutos_activo=0
                WHERE user_id=$1 AND guild_id=$2
            """, user_id, guild_id)

    # ==============================================================
    #   ADVERTENCIAS
    # ==============================================================

    async def add_advertencia(self, user_id: int, guild_id: int, razon: str,
                               moderador_id: int, moderador_nombre: str) -> int:
        """Agrega advertencia y retorna el total de advertencias del usuario."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO advertencias (user_id, guild_id, razon, moderador_id, moderador_nombre)
                VALUES ($1, $2, $3, $4, $5)
            """, user_id, guild_id, razon, moderador_id, moderador_nombre)
            row = await conn.fetchrow(
                "SELECT COUNT(*) as total FROM advertencias WHERE user_id=$1 AND guild_id=$2",
                user_id, guild_id
            )
            return row["total"]

    async def get_advertencias(self, user_id: int, guild_id: int) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM advertencias
                WHERE user_id=$1 AND guild_id=$2
                ORDER BY fecha ASC
            """, user_id, guild_id)
            return [dict(r) for r in rows]

    async def clear_advertencias(self, user_id: int, guild_id: int) -> int:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM advertencias WHERE user_id=$1 AND guild_id=$2",
                user_id, guild_id
            )
            return int(result.split()[-1])

    # ==============================================================
    #   AUTOMOD INFRACCIONES
    # ==============================================================

    async def add_infraccion_automod(self, user_id: int, guild_id: int, razon: str) -> int:
        """Agrega infracción y retorna el conteo actual."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO automod_infracciones (user_id, guild_id, razon)
                VALUES ($1, $2, $3)
            """, user_id, guild_id, razon)
            row = await conn.fetchrow("""
                SELECT COUNT(*) as total FROM automod_infracciones
                WHERE user_id=$1 AND guild_id=$2
            """, user_id, guild_id)
            return row["total"]

    async def reset_infracciones_automod(self, user_id: int, guild_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM automod_infracciones WHERE user_id=$1 AND guild_id=$2",
                user_id, guild_id
            )

    async def get_infracciones_automod(self, user_id: int, guild_id: int) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT COUNT(*) as total FROM automod_infracciones
                WHERE user_id=$1 AND guild_id=$2
            """, user_id, guild_id)
            return row["total"]

    async def get_top_infractores(self, guild_id: int, limite: int = 5) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT user_id, COUNT(*) as total
                FROM automod_infracciones
                WHERE guild_id=$1
                GROUP BY user_id
                ORDER BY total DESC
                LIMIT $2
            """, guild_id, limite)
            return [dict(r) for r in rows]

    # ==============================================================
    #   TICKETS
    # ==============================================================

    async def crear_ticket(self, canal_nombre: str, guild_id: int, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO tickets (canal_nombre, guild_id, user_id)
                VALUES ($1, $2, $3)
                RETURNING id
            """, canal_nombre, guild_id, user_id)
            return row["id"]

    async def cerrar_ticket(self, canal_nombre: str, guild_id: int,
                             cerrado_por_id: int, cerrado_por: str, transcripcion: list):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE tickets SET
                    abierto       = FALSE,
                    cerrado_por_id = $3,
                    cerrado_por   = $4,
                    cerrado_en    = NOW(),
                    transcripcion = $5::jsonb
                WHERE canal_nombre=$1 AND guild_id=$2 AND abierto=TRUE
            """, canal_nombre, guild_id, cerrado_por_id, cerrado_por,
                json.dumps(transcripcion, ensure_ascii=False))

    async def get_tickets_cerrados(self, guild_id: int, limite: int = 50) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, canal_nombre, user_id, cerrado_por, cerrado_en
                FROM tickets
                WHERE guild_id=$1 AND abierto=FALSE
                ORDER BY cerrado_en DESC
                LIMIT $2
            """, guild_id, limite)
            return [dict(r) for r in rows]

    async def count_tickets(self, guild_id: int) -> dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    COUNT(*) FILTER (WHERE abierto=TRUE)  AS abiertos,
                    COUNT(*) FILTER (WHERE abierto=FALSE) AS cerrados
                FROM tickets WHERE guild_id=$1
            """, guild_id)
            return dict(row)

    # ==============================================================
    #   CONFIGURACIÓN DEL SERVIDOR
    # ==============================================================

    async def get_config(self, guild_id: int) -> dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT config FROM config_servidor WHERE guild_id=$1", guild_id
            )
            return json.loads(row["config"]) if row else {}

    async def set_config(self, guild_id: int, config: dict):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO config_servidor (guild_id, config) VALUES ($1, $2::jsonb)
                ON CONFLICT (guild_id) DO UPDATE SET config = $2::jsonb
            """, guild_id, json.dumps(config, ensure_ascii=False))


# Instancia global — se importa desde cualquier cog
db = Database()
