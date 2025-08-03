import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from datetime import datetime
import json
import os
import asyncio
from dotenv import load_dotenv
import pytz

load_dotenv()
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
CONFIG_FILE = "like_channels.json"

class LikeCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_host = "https://likes.ffgarena.cloud/api/v2"
        self.config_data = self.load_config()
        self.cooldowns = {}
        self.session = aiohttp.ClientSession()

        self.headers = {}
        if RAPIDAPI_KEY:
            self.headers = {
                'x-rapidapi-key': RAPIDAPI_KEY,
                'x-rapidapi-host': "likes.ffgarena.cloud"
            }

    def load_config(self):
        default_config = { "servers": {} }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    loaded_config = json.load(f)
                    loaded_config.setdefault("servers", {})
                    return loaded_config
            except json.JSONDecodeError:
                print(f"WARNING: Configuration file '{CONFIG_FILE}' is corrupt. Resetting to default.")
        self.save_config(default_config)
        return default_config

    def save_config(self, config_to_save=None):
        data_to_save = config_to_save if config_to_save else self.config_data
        temp_file = CONFIG_FILE + ".tmp"
        with open(temp_file, 'w') as f:
            json.dump(data_to_save, f, indent=4)
        os.replace(temp_file, CONFIG_FILE)

    async def check_channel(self, ctx):
        if ctx.guild is None:
            return True
        guild_id = str(ctx.guild.id)
        like_channels = self.config_data["servers"].get(guild_id, {}).get("like_channels", [])
        return not like_channels or str(ctx.channel.id) in like_channels

    @commands.hybrid_command(name="like", description="Sends likes to a Free Fire player")
    @app_commands.describe(uid="Player UID (numbers only)")
    async def like_command(self, ctx: commands.Context, uid: str):
        is_slash = ctx.interaction is not None

        if not await self.check_channel(ctx):
            msg = "COMANDO NÃO ESTÁ DISPONÍVEL NESSE CANAL."
            if is_slash:
                await ctx.response.send_message(msg, ephemeral=True)
            else:
                await ctx.reply(msg, mention_author=False)
            return

        user_id = ctx.author.id
        cooldown = 30
        if user_id in self.cooldowns:
            last_used = self.cooldowns[user_id]
            remaining = cooldown - (datetime.now() - last_used).seconds
            if remaining > 0:
                msg = f"aguarde {remaining} segundos antes de tentar novamente."
                if is_slash:
                    await ctx.response.send_message(msg, ephemeral=True)
                else:
                    await ctx.send(msg)
                return
        self.cooldowns[user_id] = datetime.now()

        if not uid.isdigit() or len(uid) < 6:
            msg = "ID inválido."
            if is_slash:
                await ctx.response.send_message(msg, ephemeral=True)
            else:
                await ctx.reply(msg, mention_author=False)
            return

        try:
            async with ctx.typing():
                url_primary = f"{self.api_host}/likes?uid={uid}&amount_of_likes=100&auth=vortex&region=br"
                url_ind = f"{self.api_host}/likes?uid={uid}&amount_of_likes=100&auth=vortex&region=ind"

                async with self.session.get(url_primary, headers=self.headers) as response:
                    data = await response.json()
                    if response.status == 404 or (data.get("status") == 404 and data.get("error") == "PLAYER_NOT_FOUND"):
                        async with self.session.get(url_ind, headers=self.headers) as resp2:
                            data2 = await resp2.json()
                            if resp2.status == 404 or (data2.get("status") == 404 and data2.get("error") == "PLAYER_NOT_FOUND"):
                                await self._send_player_not_found(ctx, uid)
                                return
                            elif resp2.status != 200:
                                await self._send_api_error(ctx)
                                return
                            else:
                                data = data2
                    elif response.status == 429:
                        await self._send_api_limit_reached(ctx)
                        return
                    elif response.status != 200:
                        await self._send_api_error(ctx)
                        return

                success = data.get("status") == 200
                sent_likes = data.get('sent', '0 likes')

                if success and sent_likes.startswith("0"):
                    embed = discord.Embed(
                        title="🚫 Likes esgotados!",
                        description=f"O jogador **{data.get('nickname', 'Desconhecido')}** (ID: `{uid}`) já recebeu todos os likes permitidos hoje.\nVolte amanhã para tentar novamente.",
                        color=0xE74C3C
                    )
                    embed.set_image(url="https://cdn.discordapp.com/attachments/1359752132579950685/1401313741345259591/f3fcf1b8bc493f13d38e0451ae6d2f78.gif")
                    tz = pytz.timezone('America/Sao_Paulo')
                    hora_local = datetime.now(tz).strftime('%H:%M')
                    embed.set_footer(text=f"Hoje às {hora_local}")
                    await ctx.send(embed=embed, ephemeral=True)
                    return

                embed = discord.Embed(color=0x2ECC71)
                embed.description = (
                    f"👍 **Likes Enviados**\n\n"
                    f"🧑‍💻 **Nickname**\n{data.get('nickname', 'Unknown')}\n"
                    f"🌐 **Região**\n{data.get('region', 'N/A')}\n"
                    f"⭐ **Nível**\n{data.get('level', 'N/A')}\n"
                    f"📊 **EXP**\n{data.get('exp', 'N/A')}\n"
                    f"❤️ **Likes Antes**\n{data.get('likes_antes', 'N/A')}\n"
                    f"❤️ **Likes Depois**\n{data.get('likes_depois', 'N/A')}\n"
                    f"📩 **Resultado**\n{sent_likes}\n"
                )
                embed.set_image(url="https://cdn.discordapp.com/attachments/1359752132579950685/1401313741345259591/f3fcf1b8bc493f13d38e0451ae6d2f78.gif")
                tz = pytz.timezone('America/Sao_Paulo')
                hora_local = datetime.now(tz).strftime('%H:%M')
                embed.set_footer(text=f"Hoje às {hora_local}")
                await ctx.send(embed=embed, mention_author=True, ephemeral=is_slash)

        except asyncio.TimeoutError:
            await self._send_error_embed(ctx, "Timeout", "O servidor demorou para responder.", ephemeral=is_slash)
        except Exception as e:
            print(f"Erro inesperado: {e}")
            await self._send_error_embed(ctx, "Erro crítico", "Ocorreu um erro inesperado. Tente novamente mais tarde.", ephemeral=is_slash)

    async def _send_player_not_found(self, ctx, uid):
        embed = discord.Embed(title="❌ Usuário não encontrado", description=f"O ID {uid} não existe ou está inacessível.", color=0xE74C3C)
        embed.add_field(name="Dicas", value="- Verifique se o ID está correto\n- O jogador não está privado", inline=False)
        await ctx.send(embed=embed, ephemeral=True)

    async def _send_api_limit_reached(self, ctx):
        embed = discord.Embed(
            title="⚠️ Limite de Requisições",
            description="Você atingiu o limite máximo de requisições permitido pela API.",
            color=0xF1C40F
        )
        embed.add_field(name="Dica", value="Tente novamente em alguns minutos.", inline=False)
        await ctx.send(embed=embed, ephemeral=True)

    async def _send_api_error(self, ctx):
        embed = discord.Embed(title="⚠️ Serviço Indisponível", description="A API do Free Fire não está respondendo no momento.", color=0xF39C12)
        embed.add_field(name="Solução", value="Tente novamente mais tarde.", inline=False)
        await ctx.send(embed=embed, ephemeral=True)

    async def _send_error_embed(self, ctx, title, description, ephemeral=True):
        embed = discord.Embed(title=f"❌ {title}", description=description, color=discord.Color.red(), timestamp=datetime.now())
        embed.set_footer(text="Ocorreu um erro.")
        await ctx.send(embed=embed, ephemeral=ephemeral)

    async def cog_unload(self):
        await self.session.close()

async def setup(bot):
    await bot.add_cog(LikeCommands(bot))
