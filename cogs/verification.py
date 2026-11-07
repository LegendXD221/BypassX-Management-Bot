"""Verification Cog.

Category    : Verification
Emoji       : bx_check
Color       : #57F287
Description : Member verification setup and panel deployment.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from core.checks import require_tier
from config.emojis import E
from db.queries.verification import get_verify_config, upsert_verify_config
from ui.containers import error, information, success

logger = logging.getLogger(__name__)

_MODE_CHOICES = [
    app_commands.Choice(name="Button", value="button"),
    app_commands.Choice(name="Captcha", value="captcha"),
    app_commands.Choice(name="Reaction", value="reaction"),
]

_CAPTCHA_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CAPTCHA_TTL = timedelta(minutes=3)
_CAPTCHA_MAX_ATTEMPTS = 3


@dataclass(slots=True)
class CaptchaChallenge:
    """A short-lived captcha bound to one member and one guild."""

    guild_id: int
    user_id: int
    code: str
    expires_at: datetime
    attempts: int = 0


class VerificationCaptchaModal(discord.ui.Modal):
    """Simple challenge modal used by captcha-mode verification panels."""

    def __init__(self, cog: "VerificationCog", challenge: CaptchaChallenge) -> None:
        super().__init__(title=f"Verification code: {challenge.code}", timeout=180)
        self.cog = cog
        self.challenge = challenge
        self.answer = discord.ui.TextInput(
            custom_id="verification_code",
            label="Enter the 6-character code shown above",
            placeholder="Enter code",
            min_length=6,
            max_length=6,
            required=True,
        )
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.challenge.user_id:
            await interaction.response.send_message(**error("This captcha belongs to another member."), ephemeral=True)
            return
        if interaction.guild is None or interaction.guild.id != self.challenge.guild_id:
            await interaction.response.send_message(**error("This captcha belongs to another server."), ephemeral=True)
            return
        now = datetime.now(timezone.utc)
        if now >= self.challenge.expires_at:
            self.cog.discard_captcha(self.challenge)
            await interaction.response.send_message(**error("This captcha expired. Start verification again."), ephemeral=True)
            return
        if str(self.answer.value).strip().upper() != self.challenge.code:
            self.challenge.attempts += 1
            remaining = _CAPTCHA_MAX_ATTEMPTS - self.challenge.attempts
            if remaining <= 0:
                self.cog.discard_captcha(self.challenge)
                await interaction.response.send_message(**error("Too many incorrect attempts. Start verification again."), ephemeral=True)
            else:
                await interaction.response.send_message(**error(f"Incorrect verification code. Attempts remaining: `{remaining}`."), ephemeral=True)
            return
        self.cog.discard_captcha(self.challenge)
        await self.cog.verify_member(interaction, self.challenge.guild_id)


class VerificationPanel(discord.ui.LayoutView):
    """Persistent Components V2 verification panel."""

    def __init__(self, cog: "VerificationCog", guild_id: int, mode: str) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.mode = mode
        description = {
            "button": "Press the button below to receive the verified role.",
            "captcha": "Press the button below and enter the verification code.",
            "reaction": f"React to this panel with {E.bx_check} to receive the verified role.",
        }.get(mode, "Complete verification to receive the verified role.")
        children: list[discord.ui.Item[discord.ui.LayoutView]] = [
            discord.ui.TextDisplay(f"{E.bx_check}  **Server Verification**"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(description),
        ]
        if mode in {"button", "captcha"}:
            button = discord.ui.Button(
                style=discord.ButtonStyle.success,
                label="Verify" if mode == "button" else "Start verification",
                custom_id=f"bypassx:verify:{guild_id}",
            )
            button.callback = self._button_callback
            children.append(discord.ui.ActionRow(button))
        self.add_item(discord.ui.Container(*children, accent_color=0xFFFFFF))

    async def _button_callback(self, interaction: discord.Interaction) -> None:
        if self.mode == "captcha":
            await self.cog.start_captcha(interaction, self.guild_id)
            return
        await self.cog.verify_member(interaction, self.guild_id)


class VerificationSetupView(discord.ui.LayoutView):
    """One-message setup wizard for selecting the verification role and channel."""

    def __init__(self, cog: "VerificationCog", guild_id: int) -> None:
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.selected_role: discord.Role | None = None
        self.selected_channel: discord.TextChannel | None = None

        role_select = discord.ui.RoleSelect(
            custom_id=f"bypassx:verify-setup-role:{guild_id}",
            placeholder="Select the verified role",
        )
        channel_select = discord.ui.ChannelSelect(
            custom_id=f"bypassx:verify-setup-channel:{guild_id}",
            channel_types=[discord.ChannelType.text],
            placeholder="Select the panel channel",
        )
        save = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label="Save setup",
            custom_id=f"bypassx:verify-setup-save:{guild_id}",
        )
        role_select.callback = self._role_selected
        channel_select.callback = self._channel_selected
        save.callback = self._save
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"{E.bx_check}  **Verification Setup**"),
                discord.ui.Separator(),
                discord.ui.TextDisplay("Select the role and channel, then save the setup."),
                discord.ui.ActionRow(role_select),
                discord.ui.ActionRow(channel_select),
                discord.ui.ActionRow(save),
                accent_color=0xFFFFFF,
            )
        )

    async def _role_selected(self, interaction: discord.Interaction) -> None:
        values = getattr(interaction, "data", {}).get("values", [])
        if values and interaction.guild is not None:
            self.selected_role = interaction.guild.get_role(int(values[0]))
        await interaction.response.defer()

    async def _channel_selected(self, interaction: discord.Interaction) -> None:
        values = getattr(interaction, "data", {}).get("values", [])
        if values and interaction.guild is not None:
            channel = interaction.guild.get_channel(int(values[0]))
            if isinstance(channel, discord.TextChannel):
                self.selected_channel = channel
        await interaction.response.defer()

    async def _save(self, interaction: discord.Interaction) -> None:
        if self.selected_role is None or self.selected_channel is None:
            await interaction.response.send_message(**error("Select both a verified role and a panel channel first."), ephemeral=True)
            return
        await upsert_verify_config(
            self.cog.db,
            str(self.guild_id),
            enabled=True,
            mode="button",
            roleId=str(self.selected_role.id),
            channelId=str(self.selected_channel.id),
            messageId=None,
        )
        self.stop()
        await interaction.response.send_message(
            **success(f"Verification setup saved. Deploy the panel in {self.selected_channel.mention} with `/verify panel`."),
            ephemeral=True,
        )


class VerificationCog(commands.Cog):
    """Configure verification roles, channels, modes, and panels."""

    verify = app_commands.Group(name="verify", description="Configure server verification.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db = bot.db
        self._captchas: dict[tuple[int, int], CaptchaChallenge] = {}

    def discard_captcha(self, challenge: CaptchaChallenge) -> None:
        """Remove a completed, expired, or exhausted captcha challenge."""
        self._captchas.pop((challenge.guild_id, challenge.user_id), None)

    async def start_captcha(self, interaction: discord.Interaction, guild_id: int) -> None:
        """Create a member-bound challenge and open its modal."""
        if interaction.guild is None or interaction.guild.id != guild_id:
            await interaction.response.send_message(**error("This verification panel belongs to another server."), ephemeral=True)
            return
        config = await get_verify_config(self.db, str(guild_id))
        if config is None or not config.enabled or config.mode != "captcha":
            await interaction.response.send_message(**error("Captcha verification is not enabled on this server."), ephemeral=True)
            return
        key = (guild_id, interaction.user.id)
        old = self._captchas.get(key)
        now = datetime.now(timezone.utc)
        if old is not None and old.expires_at > now:
            await interaction.response.send_message(**information("Captcha already open", "Complete the existing captcha modal before starting another."), ephemeral=True)
            return
        code = "".join(secrets.choice(_CAPTCHA_ALPHABET) for _ in range(6))
        challenge = CaptchaChallenge(guild_id, interaction.user.id, code, now + _CAPTCHA_TTL)
        self._captchas[key] = challenge
        await interaction.response.send_modal(VerificationCaptchaModal(self, challenge))

    async def cog_load(self) -> None:
        """Re-register persistent button and captcha panels after startup."""
        try:
            configs = await self.db.verifyconfig.find_many(where={"enabled": True})
        except Exception:
            logger.exception("Could not restore verification panels")
            return
        for config in configs:
            if config.messageId and config.mode in {"button", "captcha"}:
                try:
                    self.bot.add_view(
                        VerificationPanel(self, int(config.guildId), config.mode),
                        message_id=int(config.messageId),
                    )
                except (TypeError, ValueError):
                    logger.warning("Could not restore verification panel %s", config.messageId)

    async def verify_member(self, interaction: discord.Interaction, guild_id: int) -> None:
        """Assign the configured role to the interacting guild member."""
        if interaction.guild is None or interaction.guild.id != guild_id:
            await interaction.response.send_message(**error("This verification panel belongs to another server."), ephemeral=True)
            return
        config = await get_verify_config(self.db, str(guild_id))
        if config is None or not config.enabled or not config.roleId:
            await interaction.response.send_message(**error("Verification is not configured on this server."), ephemeral=True)
            return
        role = interaction.guild.get_role(int(config.roleId))
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if role is None or member is None:
            await interaction.response.send_message(**error("The configured verification role is unavailable."), ephemeral=True)
            return
        if role in member.roles:
            await interaction.response.send_message(**information("Already verified", "You already have the verified role.", accent=0xFFFFFF), ephemeral=True)
            return
        try:
            await member.add_roles(role, reason="Verification completed")
        except discord.Forbidden:
            await interaction.response.send_message(**error("The bot cannot assign the configured role. Move it below the bot's highest role."), ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.response.send_message(**error("Discord rejected the role assignment. Try again shortly."), ephemeral=True)
            return
        await interaction.response.send_message(**success("Verification complete. You now have access to the server."), ephemeral=True)

    @verify.command(name="setup", description="Open the interactive verification setup wizard.")
    @require_tier(2)
    async def setup_wizard(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        await interaction.response.send_message(view=VerificationSetupView(self, interaction.guild.id), ephemeral=True)

    @verify.command(name="role", description="Set the role granted on verification.")
    @app_commands.describe(role="Role granted to verified members.")
    @require_tier(2)
    async def role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        await upsert_verify_config(self.db, str(interaction.guild.id), roleId=str(role.id))
        await interaction.response.send_message(**success(f"Verification role set to {role.mention}."), ephemeral=True)

    @verify.command(name="channel", description="Set the channel for the verification panel.")
    @app_commands.describe(channel="Text channel where the panel will be deployed.")
    @require_tier(2)
    async def channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        await upsert_verify_config(self.db, str(interaction.guild.id), channelId=str(channel.id))
        await interaction.response.send_message(**success(f"Verification panel channel set to {channel.mention}."), ephemeral=True)

    @verify.command(name="mode", description="Set the verification mode.")
    @app_commands.describe(mode="Button, captcha, or reaction verification.")
    @app_commands.choices(mode=_MODE_CHOICES)
    @require_tier(2)
    async def mode(self, interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        await upsert_verify_config(self.db, str(interaction.guild.id), mode=mode.value)
        await interaction.response.send_message(**success(f"Verification mode set to `{mode.name}`. Redeploy the panel to apply it."), ephemeral=True)

    @verify.command(name="panel", description="Deploy or redeploy the verification panel.")
    @require_tier(2)
    async def panel(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        config = await get_verify_config(self.db, str(interaction.guild.id))
        if config is None or not config.roleId or not config.channelId:
            await interaction.response.send_message(**error("Set both a verification role and channel first."), ephemeral=True)
            return
        if config.mode not in {"button", "captcha", "reaction"}:
            await interaction.response.send_message(**error("Unsupported verification mode."), ephemeral=True)
            return
        channel = interaction.guild.get_channel(int(config.channelId))
        role = interaction.guild.get_role(int(config.roleId))
        if not isinstance(channel, discord.TextChannel) or role is None:
            await interaction.response.send_message(**error("The configured role or channel is unavailable."), ephemeral=True)
            return
        bot_member = interaction.guild.me
        if bot_member is not None and role >= bot_member.top_role:
            await interaction.response.send_message(**error("Move the verification role below the bot's highest role."), ephemeral=True)
            return
        try:
            panel_message = await channel.send(view=VerificationPanel(self, interaction.guild.id, config.mode))
            if config.mode == "reaction":
                reaction = discord.PartialEmoji.from_str(E.bx_check) if E.bx_check.startswith("<:") else "✅"
                try:
                    await panel_message.add_reaction(reaction)
                except discord.HTTPException:
                    await panel_message.add_reaction("✅")
        except discord.Forbidden:
            await interaction.response.send_message(**error("The bot cannot send the verification panel in that channel."), ephemeral=True)
            return
        await upsert_verify_config(
            self.db,
            str(interaction.guild.id),
            enabled=True,
            messageId=str(panel_message.id),
        )
        await interaction.response.send_message(**success(f"Verification panel deployed in {channel.mention}."), ephemeral=True)

    @verify.command(name="disable", description="Disable the verification system.")
    @require_tier(2)
    async def disable(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        await upsert_verify_config(self.db, str(interaction.guild.id), enabled=False)
        await interaction.response.send_message(**success("Verification disabled. Existing panel buttons will no longer assign roles."), ephemeral=True)

    @verify.command(name="view", description="View current verification configuration.")
    @require_tier(2)
    async def view(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(**error("This command requires a server."), ephemeral=True)
            return
        config = await get_verify_config(self.db, str(interaction.guild.id))
        if config is None:
            await interaction.response.send_message(**information("Verification Configuration", "Verification has not been configured.", accent=0xFFFFFF), ephemeral=True)
            return
        role = f"<@&{config.roleId}>" if config.roleId else "not set"
        channel = f"<#{config.channelId}>" if config.channelId else "not set"
        body = f"**Status**  {'enabled' if config.enabled else 'disabled'}\n**Mode**  `{config.mode}`\n**Role**  {role}\n**Channel**  {channel}\n**Panel message**  `{config.messageId or 'not deployed'}`"
        await interaction.response.send_message(**information("Verification Configuration", body, accent=0xFFFFFF), ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Handle reaction-mode verification panels."""
        if payload.guild_id is None:
            return
        if self.bot.user is not None and payload.user_id == self.bot.user.id:
            return
        configured_reaction = discord.PartialEmoji.from_str(E.bx_check) if E.bx_check.startswith("<:") else None
        is_configured_reaction = configured_reaction is not None and payload.emoji.id == configured_reaction.id
        if not is_configured_reaction and str(payload.emoji) != "✅":
            return
        config = await get_verify_config(self.db, str(payload.guild_id))
        if config is None or not config.enabled or config.mode != "reaction" or str(payload.message_id) != str(config.messageId):
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        member = guild.get_member(payload.user_id)
        if member is None:
            try:
                member = await guild.fetch_member(payload.user_id)
            except discord.HTTPException:
                return
        role = guild.get_role(int(config.roleId)) if config.roleId else None
        if role is None:
            return
        try:
            await member.add_roles(role, reason="Reaction verification completed")
        except discord.HTTPException:
            return
        channel = guild.get_channel(payload.channel_id)
        if channel is not None:
            try:
                message = await channel.fetch_message(payload.message_id)
                await message.remove_reaction(payload.emoji, member)
            except discord.HTTPException:
                pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VerificationCog(bot))
