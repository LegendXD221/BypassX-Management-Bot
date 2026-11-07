# BypassX Management

A modular Discord.py management bot built around Cogs, Prisma, PostgreSQL, and structured UI responses.

## Section 14 status

This repository currently contains the deployable project foundation:

- Cogs-based package layout
- Environment-variable configuration
- Prisma schema location
- Render Blueprint configuration
- Dynamic feature Cog discovery, with Economy intentionally retained as a disabled placeholder per the project decision to skip Economy
- Prisma database connection and graceful shutdown lifecycle
- Complete PostgreSQL Prisma schema covering all planned feature areas
- Initial committed migration under `db/migrations/0001_init`
- Async query helpers for guilds, moderation, leveling, economy, and tickets
- Components V2 response containers for success, error, warning, permission, cooldown, and action logs
- Shared reason, confirmation, and generic text modals
- Runtime help menu with dropdown navigation and automatic Cog discovery
- `/help` and `?help` commands backed by the same ephemeral/read-only UI
- Database-backed permission tiers with reusable `@require_tier(...)` checks
- Persistent Prisma cooldowns with reusable `@persistent_cooldown(...)` checks
- Member, role, channel, snowflake, and duration converters
- Duration parsing, humanization, Discord timestamps, and structured formatters
- Unified prefix/slash error routing with silent unknown-command handling
- Configuration Cog with prefix, language, permission-tier, view, reset, export, and import commands
- Moderation Cog with member actions, warnings, cases, modlogs, channel controls, massban, nuke, and role management
- Every moderation action records a persistent `ModCase` and uses tier checks
- Logging Cog with `/logs set`, `/logs view`, `/logs disable`, `/logs reset`, and `/logs test`
- Persistent per-event log-channel assignments in the Prisma `LogConfig` model
- Automatic structured audit logging for messages, members, moderation, roles, channels, voice, invites, timeouts, and server boosts
- Every persisted moderation case emits a structured `mod_actions` audit record without making moderation depend on log-channel availability
- Role create/update/delete and timeout/untimeout transitions are detected from Discord member and role events
- Audit delivery failures are isolated from normal bot command and event processing
- AutoMod Cog with enable/disable, anti-spam, anti-raid, filter, caps, links, mentions, account-age, exemption, and view commands
- Persistent AutoMod settings and exemption lists in the Prisma `AutomodConfig` model
- Rolling message-spam and join-raid detection with filtered-content, link, mass-mention, caps, and new-account enforcement
- AutoMod actions delete violating messages, remove raid members, and route structured actions through the configured moderation log channel
- Verification Cog with setup, role, channel, mode, panel, disable, and view commands
- Interactive Components V2 setup wizard for selecting the verified role and panel channel
- Persistent verification panels with button, captcha, and reaction modes
- Member-bound six-character captchas that expire after three minutes, allow three attempts, and are single-use
- Verification reaction panels use the application `bx_check` emoji when Discord accepts it, with a Unicode fallback
- Verification state persisted through the Prisma `VerifyConfig` model and restored on startup
- Leveling Cog with rank, paginated leaderboard, manual XP/level controls, and reset commands
- Persistent level-role rewards with add, remove, and list commands
- XP range, cooldown, announcement message/channel, and channel blacklist configuration
- Message-based XP tracking with a quadratic level curve and automatic reward assignment
- Tickets Cog with panel setup, category, transcript log, support role, and per-user limit configuration
- Persistent ticket creation, ownership, claims, open/closed state, and channel lookup helpers
- Ticket panel and ticket-control Components V2 views restored after restart
- Ticket control-message IDs persisted in Prisma for reliable restart recovery
- Ticket setup redeploys an existing panel instead of creating duplicate panels
- Ticket close flow with channel history transcript export and configured transcript logging
- Ticket member add/remove, rename, claim/unclaim, close, and panel pin commands
- Failed ticket creation cleans up orphaned channels and incomplete database records
- Welcome Cog with welcome channel, message, card, and test commands
- Farewell Cog commands for channel, message, and test previews
- Autorole commands for member roles, bot-only roles, removal, and listing
- Member join/leave listeners with `{user}`, `{username}`, `{server}`, `{membercount}`, and `{id}` expansion
- Persistent WelcomeConfig storage for greeting settings and autorole role lists
- Server Stats Cog with server overview, member profile, and bot diagnostics commands
- Live statistics channel setup, disable, and per-stat channel configuration
- Counter channels for total members, online members, boosts, channels, roles, and bans
- Event-driven statistics refreshes for member, channel, role, guild, boost, and startup changes
- Reaction Roles Cog with `reactions`, `buttons`, and `select` panel modes
- `/reactionrole setup`, `add`, `remove`, `deploy`, `list`, and `disable` commands
- Up to 25 emoji-to-role mappings per panel, persisted through Prisma `ReactionRolePanel` and `ReactionRole` models
- Restart-safe button/select views and raw reaction add/remove listeners
- No authorized-guild allowlist: reaction roles are configured normally for the BypassX server through tiered server commands
- Starboard Cog with configurable destination channel, threshold, emoji, self-star policy, ignored channels, and disable/view commands
- Persistent popular-message mirrors with source links, author, content, attachments, and live star counts
- Engagement Analytics commands for daily message, reaction, join, leave, and active-user-event totals
- Daily engagement aggregation uses one Prisma row per guild/date instead of storing every event, keeping free-tier PostgreSQL usage bounded
- `/starboard setup`, `threshold`, `emoji`, `selfstar`, `ignore`, `view`, and `disable`
- `/analytics overview`, `top`, and owner-level `reset`
- Section 20 Giveaways Cog with `/giveaway start`, `end`, `reroll`, `list`, `delete`, `pause`, `resume`, and `edit`
- Persistent Components V2 entry panels with restart-safe button restoration and duplicate-entry protection
- Restart-safe expiry monitor with paused-state support and cryptographically secure `secrets.choice()` winner selection
- Giveaway entries, end times, pause state, winners, channel IDs, and message IDs persisted in the Prisma `Giveaway` model
- Section 21 Reminders Cog with `/reminder set`, `list`, `cancel`, and `clear`
- Persistent reminder delivery with relative durations up to one year, restart-safe polling, channel delivery, and DM fallback
- Reminder records are marked complete after delivery and remain isolated from normal command processing when a destination is unavailable
- Section 22 Utility Cog with user, server, avatar, banner, role, channel, ping, invite, snipe, editsnipe, poll, embed, and say commands
- In-memory deleted and edited message caches with bounded per-channel history
- Components V2 quick polls and styled panels with permission-tier controls for message-sending tools
- Section 23 Configuration Cog with prefix, language, permission tiers, view, reset, export, and import commands
- Dynamic per-guild prefix resolution with safe database-disconnected fallback
- Full configuration reset cleanup for standalone warnings, moderation cases, giveaways, reminders, and cooldowns
- Configuration imports validate before mutation and reconcile removed permission-tier assignments
- Section 24 production hardening for Render and managed hosting deployments
- Bounded PostgreSQL connection retries with a startup `SELECT 1` health check and gateway-ready database diagnostics
- Strict environment, Discord ID, and log-level validation with actionable startup errors
- Resilient Discord/database shutdown handling and fatal runtime logging
- Automated production-path tests covering settings validation, duration parsing, database retries, and health checks
- Red/black/white visual theme applied to centralized and feature-level response accents
- 20 redesigned custom BypassX emoji assets under `assets/emojis`, using red, orange, yellow, blue, white, and charcoal accents
- Startup synchronization of missing emojis to the Discord application itself, with Unicode fallbacks when the application emoji API is unavailable
- Dynamic Cog discovery and loading from `/cogs`
- Slash-command synchronization globally or to development guilds
- Startup environment validation and structured stdout logging

Remaining feature Cogs and command-specific behavior will be implemented in subsequent sections.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill BOT_TOKEN and DATABASE_URL in .env
# Optional: set DEV_GUILD_IDS=123456789012345678 for instant local slash-command sync
prisma generate
prisma migrate deploy
python main.py
```

Run the production-readiness checks locally with:

```bash
pytest -q
```

For a local PostgreSQL database, update `DATABASE_URL` in `.env` before starting the bot.

## Render deployment

1. Push this repository to GitHub or another Git provider.
2. In Render, create a Blueprint and select the repository containing `render.yaml`.
3. Set the secret values for `BOT_TOKEN` and `BOT_OWNER_ID` when prompted.
4. Render provisions the PostgreSQL database and injects `DATABASE_URL` into the worker.
5. The build runs `prisma generate`; the start command applies committed migrations and then starts the bot.

At startup the bot validates `BOT_TOKEN` and `DATABASE_URL`, connects Prisma,
loads every `.py` file in `/cogs`, and synchronizes application commands. If
`DEV_GUILD_IDS` is set, commands are synchronized to those guilds; otherwise
they are synchronized globally. After the first gateway-ready event, the bot
also creates any missing `bx_*` application emojis from `assets/emojis` and
updates the shared emoji registry used by Components V2 responses. Application
emojis belong to the Discord application rather than an individual guild, so
the same emoji markup can be used wherever the application is installed. If
the token cannot access application emoji management, the bot keeps working
with Unicode fallbacks and logs the synchronization warning.

Never commit `.env`, a Discord token, or a database password. Use Render environment variables and the hosting panel's secret/environment-variable interface instead.

## Hosting panel deployment

Use the same commands in the panel's build/start configuration:

```text
Build: pip install -r requirements.txt && prisma generate
Start: prisma migrate deploy && python main.py
```

The current emoji artwork is stored directly in `assets/emojis` and is synchronized to the Discord application on startup.

## Database workflow

The canonical schema is `db/schema.prisma`. After changing it locally:

```bash
prisma migrate dev --name describe_the_change
prisma generate
```

Commit the generated migration directory. Production and Render use
`prisma migrate deploy`, which applies committed migrations without modifying
the schema interactively.

Upload or configure the environment variables from `.env.example` through the panel. Do not upload the actual `.env` file unless the panel explicitly requires it and stores it outside the public web root.
