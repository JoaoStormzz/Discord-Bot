import discord
import yt_dlp as youtube_dl
from discord.ext import commands
from collections import deque
import logging
import asyncio

from apikey import *

intents = discord.Intents.default()
intents.message_content = True

client = commands.Bot(command_prefix='!', intents=intents)

# Configuração de Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@client.event
async def on_ready():
    logger.info('O bot está em execução')

# Configurações do yt-dlp
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': True,
    'quiet': False,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or client.loop
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        except Exception as e:
            logger.error(f"Erro ao baixar o vídeo: {e}")
            return None

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        logger.info(f"Baixando/Reproduzindo: {data['title']} - URL: {data['url']}")
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

    @classmethod
    async def from_search(cls, query, *, loop=None, stream=False):
        loop = loop or client.loop
        search_url = f"ytsearch:{query}"
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search_url, download=not stream))
        except Exception as e:
            logger.error(f"Erro ao buscar o vídeo: {e}")
            return None

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        logger.info(f"Buscando/Reproduzindo: {data['title']} - URL: {data['url']}")
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

# Fila de reprodução usando deque
playlist = deque()
loop = False
current_song = None
loop_task = None

async def play_next(ctx):
    global current_song, loop_task
    if playlist:
        current_song = playlist.popleft()
        ctx.voice_client.play(current_song, after=lambda e: client.loop.create_task(on_song_end(ctx, e)))
        await ctx.send(f"Tocando: {current_song.title}")
    elif loop and current_song:
        # Recomeça a música atual se o loop estiver ativado
        if loop_task is not None:
            loop_task.cancel()
        loop_task = client.loop.create_task(repeat_current_song(ctx))
        await ctx.send(f"Repetindo: {current_song.title}")

async def repeat_current_song(ctx):
    global current_song
    if current_song:
        ctx.voice_client.play(current_song, after=lambda e: client.loop.create_task(on_song_end(ctx, e)))
        await ctx.send(f"Repetindo: {current_song.title}")

async def on_song_end(ctx, error):
    if error:
        logger.error(f'Erro: {error}')
    await play_next(ctx)

#Funciona perfeitamente!
@client.command(name='play', help='Toca música do YouTube ou por nome')
async def play(ctx, *, query):
    if not ctx.message.author.voice:
        await ctx.send("Você precisa estar em um canal de voz para tocar música.")
        return

    channel = ctx.message.author.voice.channel

    if not ctx.voice_client:
        await channel.connect()

    async with ctx.typing():
        player = None
        if 'http' in query:
            player = await YTDLSource.from_url(query, loop=client.loop, stream=True)
        else:
            player = await YTDLSource.from_search(query, loop=client.loop, stream=True)

        if player is None:
            await ctx.send("Erro ao tentar baixar ou reproduzir a música.")
            return

        playlist.append(player)

        if not ctx.voice_client.is_playing():
            await play_next(ctx)
        else:
            await ctx.send(f"Adicionado à lista de reprodução: {player.title}")

#Funciona perfeitamente!
@client.command(name='pause', help='Pausa a música')
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("Música pausada.")
    else:
        await ctx.send("Nenhuma música está sendo reproduzida.")

#Funciona perfeitamente!
@client.command(name='resume', help='Retoma a música')
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Música retomada.")
    else:
        await ctx.send("A música não está pausada.")

#Funciona perfeitamente!
@client.command(name='stop', help='Para a música e desconecta')
async def stop(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        playlist.clear()
        global current_song
        current_song = None
        if loop_task is not None:
            loop_task.cancel()
        await ctx.send("Música parada e desconectado do canal de voz.")

#Funciona perfeitamente!
@client.command(name='queue', help='Mostra a lista de reprodução')
async def queue(ctx):
    if playlist:
        queue_list = "\n".join(f"{i+1}. {song.title}" for i, song in enumerate(playlist))
        await ctx.send(f"Lista de Reprodução:\n{queue_list}")
    else:
        await ctx.send("A lista de reprodução está vazia.")
        
#Funciona perfeitamente!
@client.command(name='playskip', help='Pula a música atual e toca a nova música especificada')
async def playskip(ctx, *, query):
    if not ctx.message.author.voice:
        await ctx.send("Você precisa estar em um canal de voz para usar este comando.")
        return

    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()

    async with ctx.typing():
        player = None
        if 'http' in query:
            player = await YTDLSource.from_url(query, loop=client.loop, stream=True)
        else:
            player = await YTDLSource.from_search(query, loop=client.loop, stream=True)

        if player is None:
            await ctx.send("Erro ao tentar baixar ou reproduzir a música.")
            return

        playlist.appendleft(player)
        if not ctx.voice_client.is_playing():
            await play_next(ctx)

        await ctx.send(f"Pulado para: {player.title}")

#função não funciona corretamente, não ultilizar por enquanto!
@client.command(name='loop', help='**BETA Bugado: Ativa ou desativa o loop da música atual')
async def loop_command(ctx):
    global loop
    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await ctx.send("Nenhuma música está sendo reproduzida.")
        return

    loop = not loop
    status = "ativado" if loop else "desativado"
    await ctx.send(f"Loop {status}.")

    if loop:  # Only start loop task if loop is enabled
        loop_task = client.loop.create_task(repeat_current_song(ctx))

#Funciona perfeitamente!
@client.command(name='select', help='Seleciona uma música da lista de reprodução pelo número')
async def select(ctx, number: int):
    if not ctx.voice_client:
        await ctx.send("O bot não está conectado a um canal de voz.")
        return

    if number < 1 or number > len(playlist):
        await ctx.send("Número inválido. Por favor, escolha um número na lista de reprodução.")
        return

    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()

    song = list(playlist)[number - 1]  # Convertendo deque para lista para acessar o índice
    global current_song
    current_song = song
    ctx.voice_client.play(song, after=lambda e: client.loop.create_task(on_song_end(ctx, e)))
    await ctx.send(f"Tocando: {song.title}")

client.run(bot_token)