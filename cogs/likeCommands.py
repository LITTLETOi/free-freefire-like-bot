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
from discord.ui import View, Button

load_dotenv()
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
CONFIG_FILE = "like_channels.json"

def get_dev_button():
    view = View()
    view.add_item(Button(
        label="👑 DESENVOLVEDOR",
        url="https://discord.gg/RH8uBXWsvN",
        style=discord.ButtonStyle.link
    ))
    return view

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
        default_config = {"servers": {}}
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

    @commands.hybrid_command(name="like", description="Sends likes to a Free Fire player")
    @app_commands.describe(uid="Player UID (numbers only, minimum 6 characters)")
    async def like_command(self, ctx: commands.Context, uid: str):
        is_slash = ctx.interaction is not None

        if not await self.check_channel(ctx):
            msg = "COMANDO NÃO ESTÁ DISPONÍVEL NESSE CANAL."
            if is_slash:
                await ctx.response.send_message(msg, ephemeral=True, view=get_dev_button())
            else:
                await ctx.reply(msg, mention_author=False, view=get_dev_button())
            return

        user_id = ctx.author.id
        cooldown = 30
        now = datetime.now()
        if user_id in self.cooldowns:
            last_used = self.cooldowns[user_id]
            remaining = cooldown - int((now - last_used).total_seconds())
            if remaining > 0:
                if is_slash:
                    await ctx.response.send_message(f"⏳ Aguarde {remaining} segundos antes de tentar novamente.", ephemeral=True, view=get_dev_button())
                else:
                    await ctx.send(f"⏳ Aguarde {remaining} segundos antes de tentar novamente.", view=get_dev_button())
                return
        self.cooldowns[user_id] = now

        if not uid.isdigit() or len(uid) < 6:
            if is_slash:
                await ctx.response.send_message("❌ ID inválido", ephemeral=True, view=get_dev_button())
            else:
                await ctx.reply("❌ ID inválido", mention_author=False, view=get_dev_button())
            return

        try:
            if is_slash:
                await ctx.response.defer(thinking=True)
            else:
                await ctx.typing()

            url_primary = f"{self.api_host}/likes?uid={uid}&amount_of_likes=100&auth=vortex&region=br"
            url_ind = f"{self.api_host}/likes?uid={uid}&amount_of_likes=100&auth=vortex&region=ind"

            async with self.session.get(url_primary, headers=self.headers) as response:
                data = await response.json()
                if response.status == 404 or (data.get("status") == 404 and data.get("error") == "PLAYER_NOT_FOUND"):
                    async with self.session.get(url_ind, headers=self.headers) as resp2:
                        data2 = await resp2.json()
                        if resp2.status == 404 or (data2.get("status") == 404 and data2.get("error") == "PLAYER_NOT_FOUND"):
                            await self._send_player_not_found(ctx, uid, is_slash)
                            return
                        elif resp2.status != 200:
                            await self._send_api_error(ctx, is_slash)
                            return
                        else:
                            data = data2
                elif response.status == 429:
                    await self._send_api_limit_reached(ctx, is_slash)
                    return
                elif response.status != 200:
                    await self._send_api_error(ctx, is_slash)
                    return

            success = data.get("status") == 200
            sent_likes = data.get('sent', '0 likes')

            if success and str(sent_likes).startswith("0"):
                embed = discord.Embed(
                    title="🚫 Likes esgotados!",
                    description=f"O jogador **{data.get('nickname', 'Desconhecido')}** (ID: `{uid}`) já recebeu todos os likes permitidos hoje.",
                    color=0xE74C3C
                )
                embed.set_image(url="https://cdn.discordapp.com/attachments/1359752132579950685/1401313741345259591/f3fcf1b8bc493f13d38e0451ae6d2f78.gif")
                tz = pytz.timezone('America/Sao_Paulo')
                embed.set_footer(text=f"Hoje às {datetime.now(tz).strftime('%H:%M')}")
                if is_slash:
                    await ctx.followup.send(embed=embed, ephemeral=True, view=get_dev_button())
                else:
                    await ctx.send(embed=embed, view=get_dev_button())
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
                f"📩 **Resultado**\n{sent_likes} \n"
            )
            embed.set_image(url="https://cdn.discordapp.com/attachments/1359752132579950685/1401313741345259591/f3fcf1b8bc493f13d38e0451ae6d2f78.gif")
            embed.set_footer(text=f"Hoje às {datetime.now(pytz.timezone('America/Sao_Paulo')).strftime('%H:%M')}")

            if is_slash:
                await ctx.followup.send(embed=embed, ephemeral=True, view=get_dev_button())
            else:
                await ctx.send(embed=embed, mention_author=True, view=get_dev_button())

        except asyncio.TimeoutError:
            await self._send_error_embed(ctx, "Timeout", "O servidor demorou muito para responder.", is_slash)
        except Exception as e:
            print(f"Erro inesperado no comando like: {e}")
            await self._send_error_embed(ctx, "⚡ Erro crítico", "Ocorreu um erro inesperado. Tente novamente mais tarde.", is_slash)

    async def _send_player_not_found(self, ctx, uid, is_slash):
        embed = discord.Embed(title="❌ Usuário não encontrado", description=f"O ID {uid} NÃO EXISTE OU ESTÁ INACESSÍVEL.", color=0xE74C3C)
        embed.add_field(name="Dica", value="TENHA CERTEZA DE:\n- O ID ESTÁ CORRETO\n- O JOGADOR NÃO ESTÁ PRIVADO", inline=False)
        if is_slash:
            await ctx.response.send_message(embed=embed, ephemeral=True, view=get_dev_button())
        else:
            await ctx.send(embed=embed, view=get_dev_button())

    async def _send_api_limit_reached(self, ctx, is_slash):
        embed = discord.Embed(
            title="⚠️ Limite de requisições atingido",
            description="Você atingiu o limite máximo de requisições permitidas pela API.",
            color=0xF1C40F
        )
        if is_slash:
            await ctx.response.send_message(embed=embed, ephemeral=True, view=get_dev_button())
        else:
            await ctx.send(embed=embed, view=get_dev_button())

    async def _send_api_error(self, ctx, is_slash):
        embed = discord.Embed(title="⚠️ Serviço indisponível", description="A API do Free Fire não está respondendo no momento.", color=0xF39C12)
        if is_slash:
            await ctx.response.send_message(embed=embed, ephemeral=True, view=get_dev_button())
        else:
            await ctx.send(embed=embed, view=get_dev_button())

    async def _send_error_embed(self, ctx, title, description, is_slash):
        embed = discord.Embed(title=f"❌ {title}", description=description, color=discord.Color.red())
        embed.set_footer(text="Ocorreu um erro.")
        if is_slash:
            await ctx.response.send_message(embed=embed, ephemeral=True, view=get_dev_button())
        else:
            await ctx.send(embed=embed, view=get_dev_button())

    async def cog_unload(self):
        await self.session.close()


async def setup(bot):
    await bot.add_cog(LikeCommands(bot))
