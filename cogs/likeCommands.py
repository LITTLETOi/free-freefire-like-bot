import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from datetime import datetime
import json
import os
import asyncio
from dotenv import load_dotenv

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
            if ctx.interaction:
                await ctx.response.send_message("This command can only be used in a server.", ephemeral=True)
            else:
                await ctx.send("This command can only be used in a server.")
            return

        guild_id = str(ctx.guild.id)
        server_config = self.config_data["servers"].setdefault(guild_id, {})
        like_channels = server_config.setdefault("like_channels", [])

        channel_id_str = str(channel.id)

        if channel_id_str in like_channels:
            like_channels.remove(channel_id_str)
            self.save_config()
            msg = f"✅ Channel {channel.mention} has been **removed** from allowed channels for /like commands. The command is now **disallowed** there."
        else:
            like_channels.append(channel_id_str)
            self.save_config()
            msg = f"✅ Channel {channel.mention} is now **allowed** for /like commands. The command will **only** work in specified channels if any are set."

        if ctx.interaction:
            await ctx.response.send_message(msg, ephemeral=True)
        else:
            await ctx.send(msg)

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
                async with self.session.get(f"{self.api_host}/likes?uid={uid}&amount_of_likes=100&auth=vortex", headers=self.headers) as response:
                    if response.status == 404:
                        await self._send_player_not_found(ctx, uid)
                        return
                    if response.status == 429:
                        await self._send_api_limit_reached(ctx)
                        return
                    if response.status != 200:
                        print(f"API Error: {response.status} - {await response.text()}")
                        await self._send_api_error(ctx)
                        return

                    data = await response.json()
                    success = data.get("status") == 200
                    sent_likes = data.get('sent', '0 likes')

                    embed = discord.Embed(
                        title="VorteX Likes",
                        color=0x2ECC71 if success else 0xE74C3C,
                        timestamp=datetime.now()
                    )

                    # Correção: garantir que sent_likes seja string para usar startswith, ou converter para str
                    sent_likes_str = str(sent_likes)

                    if success:
                        if sent_likes_str.startswith("0"):
                            embed.description = "\n┌ERRO\n└─Este usuário já recebeu o máximo de likes hoje.\n"
                        else:
                            embed.description = (
                                f"\n"
                                f"┌  SUCESSO\n"
                                f"├─ USUÁRIO: {data.get('nickname', 'Unknown')}\n"
                                f"├─ UID: {uid}\n"
                                f"├─ SERVIDOR: {data.get('region', 'Desconhecido')}\n"
                                f"└─ RESULTADO:\n"
                                f"   ├─ ADICIONADO: +{sent_likes_str}\n"
                                f"   ├─ ANTES: {data.get('likes_antes', 'N/A')}\n"
                                f"   └─ DEPOIS: {data.get('likes_depois', 'N/A')}\n"
                            )
                    else:
                        embed.description = "\n┌ERRO\n└─Este usuário já recebeu o máximo de likes hoje.\n"

                    embed.set_footer(text="VorteX System")
                    embed.description += "\n🔗 ENTRE : https://discord.gg/RH8uBXWsvN"

                    if is_slash:
                        await ctx.response.send_message(embed=embed, ephemeral=True)
                    else:
                        await ctx.send(embed=embed, mention_author=True)

        except asyncio.TimeoutError:
            if is_slash:
                await self._send_error_embed(ctx, "Timeout", "The server took too long to respond.", ephemeral=True)
            else:
                await self._send_error_embed(ctx, "Timeout", "The server took too long to respond.", ephemeral=False)
        except Exception as e:
            print(f"Unexpected error in like_command: {e}")
            if is_slash:
                await self._send_error_embed(ctx, "⚡ Critical Error", "An unexpected error occurred. Please try again later.", ephemeral=True)
            else:
                await self._send_error_embed(ctx, "⚡ Critical Error", "An unexpected error occurred. Please try again later.", ephemeral=False)

    async def _send_player_not_found(self, ctx, uid):
        embed = discord.Embed(title="❌ Usuário não encontrado", description=f"O ID {uid} NÃO EXISTE OU ESTÁ INACESSÍVEL.", color=0xE74C3C)
        embed.add_field(name="Tip", value="TENHA CERTEZA DE:\n- O ID ESTÁ CORRETO\n- O JOGADOR NÃO ESTÁ PRIVADO", inline=False)
        if ctx.interaction:
            await ctx.response.send_message(embed=embed, ephemeral=True)
        else:
            await ctx.send(embed=embed)

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
        if ctx.interaction:
            await ctx.response.send_message(embed=embed, ephemeral=True)
        else:
            await ctx.send(embed=embed)

    async def _send_api_error(self, ctx):
        embed = discord.Embed(title="⚠️ Service Unavailable", description="The Free Fire API is not responding at the moment.", color=0xF39C12)
        embed.add_field(name="Solution", value="Try again in a few minutes.", inline=False)
        if ctx.interaction:
            await ctx.response.send_message(embed=embed, ephemeral=True)
        else:
            await ctx.send(embed=embed)

    async def _send_error_embed(self, ctx, title, description, ephemeral=True):
        embed = discord.Embed(title=f"❌ {title}", description=description, color=discord.Color.red(), timestamp=datetime.now())
        embed.set_footer(text="An error occurred.")
        if ephemeral and ctx.interaction:
            await ctx.response.send_message(embed=embed, ephemeral=True)
        else:
            await ctx.send(embed=embed)

    async def cog_unload(self):
        await self.session.close()

async def setup(bot):
    await bot.add_cog(LikeCommands(bot))
