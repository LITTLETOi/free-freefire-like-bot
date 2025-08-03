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
        default_config = {
            "servers": {}
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    loaded_config = json.load(f)
                    loaded_config.setdefault("servers", {})
                    return loaded_config
            except json.JSONDecodeError:
                print(f"WARNING: The configuration file '{CONFIG_FILE}' is corrupt or empty. Resetting to default configuration.")
        self.save_config(default_config)
        return default_config

    def save_config(self, config_to_save=None):
        data_to_save = config_to_save if config_to_save is not None else self.config_data
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

    async def cog_load(self):
        pass

    @commands.hybrid_command(name="setlikechannel", description="Sets the channels where the /like command is allowed.")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(channel="The channel to allow/disallow the /like command in.")
    async def set_like_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        if ctx.guild is None:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        guild_id = str(ctx.guild.id)
        server_config = self.config_data["servers"].setdefault(guild_id, {})
        like_channels = server_config.setdefault("like_channels", [])

        channel_id_str = str(channel.id)

        if channel_id_str in like_channels:
            like_channels.remove(channel_id_str)
            self.save_config()
            await ctx.send(f"✅ Channel {channel.mention} has been **removed** from allowed channels for /like commands. The command is now **disallowed** there.", ephemeral=True)
        else:
            like_channels.append(channel_id_str)
            self.save_config()
            await ctx.send(f"✅ Channel {channel.mention} is now **allowed** for /like commands. The command will **only** work in specified channels if any are set.", ephemeral=True)

    @commands.hybrid_command(name="like", description="Sends likes to a Free Fire player")
    @app_commands.describe(uid="Player UID (numbers only, minimum 6 characters)")
    async def like_command(self, ctx: commands.Context, uid: str):
        is_slash = ctx.interaction is not None

        if not await self.check_channel(ctx):
            msg = "COMANDO NÃO ESTA DISPONÍVEL NESSE CANAL."
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
                if is_slash:
                    await ctx.response.send_message(f"aguarde {remaining} segundos antes de tentar novamente.", ephemeral=True)
                else:
                    await ctx.send(f"aguarde {remaining} segundos antes de tentar novamente.")
                return
        self.cooldowns[user_id] = datetime.now()

        if not uid.isdigit() or len(uid) < 6:
            if is_slash:
                await ctx.response.send_message("id inválido", ephemeral=True)
            else:
                await ctx.reply("id inválido", mention_author=False)
            return

        try:
            async with ctx.typing():
                url_primary = f"{self.api_host}/likes?uid={uid}&amount_of_likes=100&auth=vortex&region=br"
                url_ind = f"{self.api_host}/likes?uid={uid}&amount_of_likes=100&auth=vortex&region=ind"

                async with self.session.get(url_primary, headers=self.headers) as response:
                    data = await response.json()
                    if response.status == 404 or (data.get("status") == 404 and data.get("error") == "PLAYER_NOT_FOUND"):
                        # Tenta a URL alternativa com region=ind
                        async with self.session.get(url_ind, headers=self.headers) as resp2:
                            data2 = await resp2.json()
                            if resp2.status == 404 or (data2.get("status") == 404 and data2.get("error") == "PLAYER_NOT_FOUND"):
                                await self._send_player_not_found(ctx, uid)
                                return
                            elif resp2.status != 200:
                                print(f"API Error (alt): {resp2.status} - {await resp2.text()}")
                                await self._send_api_error(ctx)
                                return
                            else:
                                data = data2  # usa os dados da resposta alternativa
                    elif response.status == 429:
                        await self._send_api_limit_reached(ctx)
                        return
                    elif response.status != 200:
                        print(f"API Error: {response.status} - {await response.text()}")
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
                    embed.set_image(url="https://cdn.discordapp.com/attachments/1359752132579950685/1401313741345259591/f3fcf1b8bc493f13d38e0451ae6d2f78.gif?ex=688fd29f&is=688e811f&hm=567e73ae15c89ed241a500a823a5cfb739799360dd8418ba83ee95ad4bd75a6a&")

                    tz = pytz.timezone('America/Sao_Paulo')
                    hora_local = datetime.now(tz).strftime('%H:%M')
                    embed.set_footer(text=f"Hoje às {hora_local}")

                    await ctx.send(embed=embed, ephemeral=is_slash)
                    return

                embed = discord.Embed(
                    color=0x2ECC71
                )

                embed.description = (
                    f"👍 **Likes Enviados**\n\n"
                    f"🧑‍💻 **Nickname**\n{data.get('nickname', 'Unknown')}\n"
                    f"🌐 **Região**\n{data.get('region', 'N/A')}\n"
                    f"⭐ **Nível**\n{data.get('level', 'N/A')}\n"
                    f"📊 **EXP**\n{data.get('exp', 'N/A')}\n"
                    f"❤️ **Likes Antes**\n{data.get('likes_antes', 'N/A')}\n"
                    f"❤️ **Likes Depois**\n{data.get('likes_depois', 'N/A')}\n"
                    f"📩 **Resultado**\n{sent_likes} \n"
                )

                embed.set_image(url="https://cdn.discordapp.com/attachments/1359752132579950685/1401313741345259591/f3fcf1b8bc493f13d38e0451ae6d2f78.gif?ex=688fd29f&is=688e811f&hm=567e73ae15c89ed241a500a823a5cfb739799360dd8418ba83ee95ad4bd75a6a&")

                tz = pytz.timezone('America/Sao_Paulo')
                hora_local = datetime.now(tz).strftime('%H:%M')
                embed.set_footer(text=f"Hoje às {hora_local}")

                await ctx.send(embed=embed, mention_author=True, ephemeral=is_slash)

        except asyncio.TimeoutError:
            await self._send_error_embed(ctx, "Timeout", "The server took too long to respond.", ephemeral=is_slash)
        except Exception as e:
            print(f"Unexpected error in like_command: {e}")
            await self._send_error_embed(ctx, "⚡ Critical Error", "An unexpected error occurred. Please try again later.", ephemeral=is_slash)

    async def _send_player_not_found(self, ctx, uid):
        embed = discord.Embed(title="❌ Usuário não encontrado", description=f"O ID {uid} NÃO EXISTE OU ESTÁ INACESSÍVEL.", color=0xE74C3C)
        embed.add_field(name="Tip", value="TENHA CERTEZA DE:\n- O ID ESTÁ CORRETO\n- O JOGADOR NÃO ESTÁ PRIVADO", inline=False)
        await ctx.send(embed=embed, ephemeral=True)

    async def _send_api_limit_reached(self, ctx):
        embed = discord.Embed(
            title="⚠️ API Rate Limit Reached",
            description="You have reached the maximum number of requests allowed by the API.",
            color=0xF1C40F
        )
        embed.add_field(
            name="Tip",
            value=(
                "- Wait a few minutes before trying again\n"
                "- Consider upgrading your API plan if this happens often\n"
                "- Avoid sending too many requests in a short time"
            ),
            inline=False
        )
        await ctx.send(embed=embed, ephemeral=True)

    async def _send_api_error(self, ctx):
        embed = discord.Embed(title="⚠️ Service Unavailable", description="The Free Fire API is not responding at the moment.", color=0xF39C12)
        embed.add_field(name="Solution", value="Try again in a few minutes.", inline=False)
        await ctx.send(embed=embed, ephemeral=True)

    async def _send_error_embed(self, ctx, title, description, ephemeral=True):
        embed = discord.Embed(title=f"❌ {title}", description=description, color=discord.Color.red(), timestamp=datetime.now())
        embed.set_footer(text="An error occurred.")
        await ctx.send(embed=embed, ephemeral=ephemeral)

    async def cog_unload(self):
        await self.session.close()

async def setup(bot):
    await bot.add_cog(LikeCommands(bot))
