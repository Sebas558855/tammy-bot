import asyncio
import discord
from discord.ext import commands
from TikTokLive import TikTokLiveClient
from TikTokLive.events import LiveIntroEvent, DisconnectEvent
from TikTokApi import TikTokApi

class TikTokNotifier:
    """
    Notifica nuevos directos y vídeos de TikTok, cada uno en un canal distinto.
    """

    def __init__(
        self,
        bot: commands.Bot,
        live_channel_id: int,
        video_channel_id: int,
        tiktok_username: str,
        video_check_interval: int = 300
    ):
        self.bot = bot
        self.live_channel_id = live_channel_id
        self.video_channel_id = video_channel_id
        self.tiktok_username = tiktok_username
        self.video_check_interval = video_check_interval

        # ── LIVE ──
        self.tiktok_live_client = None
        self.is_live = False
        self._live_task = None

        # ── VÍDEOS ──
        self.last_video_id = None
        self._video_task = None

    # ──────────────────────────────────────────
    #  LIVE
    # ──────────────────────────────────────────
    async def _send_live_notification(self):
        try:
            channel = await self.bot.fetch_channel(self.live_channel_id)
            if channel:
                await channel.send(
                    f"🔴 **¡{self.tiktok_username} está en directo en TikTok!**\n"
                    f"https://www.tiktok.com/@{self.tiktok_username}/live"
                )
                print(f"📢 Aviso de directo enviado para {self.tiktok_username}")
        except Exception as e:
            print(f"Error al enviar aviso de directo: {e}")

    async def _connect_tiktok_live(self):
        self.tiktok_live_client = TikTokLiveClient(unique_id=self.tiktok_username)

        @self.tiktok_live_client.on(LiveIntroEvent)
        async def on_live_intro(event: LiveIntroEvent):
            if not self.is_live:
                self.is_live = True
                print(f"🔴 {self.tiktok_username} está en directo!")
                await self._send_live_notification()

        @self.tiktok_live_client.on(DisconnectEvent)
        async def on_disconnect(event: DisconnectEvent):
            print(f"🔌 Desconectado del live de {self.tiktok_username}. Reconectando en 10 s...")
            self.is_live = False
            await asyncio.sleep(10)
            self._live_task = asyncio.create_task(self._connect_tiktok_live())

        try:
            print(f"🔍 Intentando conectar al live de TikTok: {self.tiktok_username}...")
            await self.tiktok_live_client.start()
        except Exception as e:
            print(f"❌ Error en conexión del live ({self.tiktok_username}): {e}")
            await asyncio.sleep(15)
            self._live_task = asyncio.create_task(self._connect_tiktok_live())

    # ──────────────────────────────────────────
    #  VÍDEOS (canal propio)
    # ──────────────────────────────────────────
    async def _send_video_notification(self, video):
        video_url = f"https://www.tiktok.com/@{self.tiktok_username}/video/{video.id}"
        try:
            channel = await self.bot.fetch_channel(self.video_channel_id)
            if channel:
                await channel.send(
                    f"🎬 **¡Nuevo vídeo de {self.tiktok_username}!**\n{video_url}"
                )
                print(f"📢 Aviso de nuevo vídeo enviado: {video.id}")
        except Exception as e:
            print(f"Error al enviar aviso de vídeo: {e}")

    async def _check_new_videos(self):
        try:
            async with TikTokApi() as api:
                user = api.user(self.tiktok_username)
                async for video in user.videos(count=1):
                    if video.id != self.last_video_id:
                        if self.last_video_id is not None:
                            await self._send_video_notification(video)
                        self.last_video_id = video.id
                    break
        except Exception as e:
            print(f"Error al comprobar nuevos vídeos de {self.tiktok_username}: {e}")

    async def _video_check_loop(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(10)
        print(f"🎬 Chequeo de vídeos activado cada {self.video_check_interval} segundos")
        while not self.bot.is_closed():
            await self._check_new_videos()
            await asyncio.sleep(self.video_check_interval)

    # ──────────────────────────────────────────
    #  ARRANQUE Y PARADA
    # ──────────────────────────────────────────
    async def start(self):
        self._live_task = asyncio.create_task(self._connect_tiktok_live())
        self._video_task = asyncio.create_task(self._video_check_loop())

        print("✅ TikTokNotifier: sistema iniciado correctamente.")
        print(f"   🟢 Live → canal {self.live_channel_id}")
        print(f"   🎞️  Vídeos → canal {self.video_channel_id} cada {self.video_check_interval}s")

    async def stop(self):
        if self.tiktok_live_client:
            await self.tiktok_live_client.close()
        print("🛑 TikTokNotifier detenido.")