-- CreateTable
CREATE TABLE "Guild" (
    "id" TEXT NOT NULL,
    "prefix" TEXT NOT NULL DEFAULT '?',
    "language" TEXT NOT NULL DEFAULT 'en',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Guild_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "ModConfig" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    CONSTRAINT "ModConfig_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "ModConfig_guildId_key" ON "ModConfig"("guildId");

CREATE TABLE "ModTier" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "roleId" TEXT NOT NULL,
    "tier" INTEGER NOT NULL,
    CONSTRAINT "ModTier_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "ModTier_guildId_roleId_key" ON "ModTier"("guildId", "roleId");
CREATE INDEX "ModTier_guildId_tier_idx" ON "ModTier"("guildId", "tier");

CREATE TABLE "ModCase" (
    "id" SERIAL NOT NULL,
    "guildId" TEXT NOT NULL,
    "targetId" TEXT NOT NULL,
    "moderatorId" TEXT NOT NULL,
    "action" TEXT NOT NULL,
    "reason" TEXT,
    "duration" INTEGER,
    "active" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "ModCase_pkey" PRIMARY KEY ("id")
);
CREATE INDEX "ModCase_guildId_targetId_createdAt_idx" ON "ModCase"("guildId", "targetId", "createdAt");
CREATE INDEX "ModCase_guildId_moderatorId_createdAt_idx" ON "ModCase"("guildId", "moderatorId", "createdAt");

CREATE TABLE "Warning" (
    "id" SERIAL NOT NULL,
    "guildId" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "moderatorId" TEXT NOT NULL,
    "reason" TEXT NOT NULL,
    "caseId" INTEGER,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Warning_pkey" PRIMARY KEY ("id")
);
CREATE INDEX "Warning_guildId_userId_createdAt_idx" ON "Warning"("guildId", "userId", "createdAt");

CREATE TABLE "LogConfig" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "messageDelete" TEXT,
    "messageEdit" TEXT,
    "memberJoin" TEXT,
    "memberLeave" TEXT,
    "banKick" TEXT,
    "roleChange" TEXT,
    "channelChange" TEXT,
    "voiceActivity" TEXT,
    "inviteActivity" TEXT,
    "memberUpdate" TEXT,
    "modActions" TEXT,
    CONSTRAINT "LogConfig_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "LogConfig_guildId_key" ON "LogConfig"("guildId");

CREATE TABLE "AutomodConfig" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "enabled" BOOLEAN NOT NULL DEFAULT false,
    "antiSpam" BOOLEAN NOT NULL DEFAULT false,
    "spamThreshold" INTEGER NOT NULL DEFAULT 5,
    "antiRaid" BOOLEAN NOT NULL DEFAULT false,
    "raidThreshold" INTEGER NOT NULL DEFAULT 10,
    "filterEnabled" BOOLEAN NOT NULL DEFAULT false,
    "filterWords" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "capsEnabled" BOOLEAN NOT NULL DEFAULT false,
    "capsThreshold" INTEGER NOT NULL DEFAULT 70,
    "linksEnabled" BOOLEAN NOT NULL DEFAULT false,
    "mentionsEnabled" BOOLEAN NOT NULL DEFAULT false,
    "mentionThreshold" INTEGER NOT NULL DEFAULT 5,
    "newAccountAge" INTEGER NOT NULL DEFAULT 0,
    "exemptRoles" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "exemptChannels" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    CONSTRAINT "AutomodConfig_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "AutomodConfig_guildId_key" ON "AutomodConfig"("guildId");

CREATE TABLE "VerifyConfig" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "enabled" BOOLEAN NOT NULL DEFAULT false,
    "mode" TEXT NOT NULL DEFAULT 'button',
    "roleId" TEXT,
    "channelId" TEXT,
    "messageId" TEXT,
    CONSTRAINT "VerifyConfig_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "VerifyConfig_guildId_key" ON "VerifyConfig"("guildId");

CREATE TABLE "LevelConfig" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    "xpMin" INTEGER NOT NULL DEFAULT 15,
    "xpMax" INTEGER NOT NULL DEFAULT 25,
    "cooldown" INTEGER NOT NULL DEFAULT 60,
    "announceEnabled" BOOLEAN NOT NULL DEFAULT true,
    "announceChannel" TEXT,
    "blacklistChannels" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    CONSTRAINT "LevelConfig_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "LevelConfig_guildId_key" ON "LevelConfig"("guildId");

CREATE TABLE "LevelRole" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "levelConfigId" TEXT NOT NULL,
    "roleId" TEXT NOT NULL,
    "level" INTEGER NOT NULL,
    CONSTRAINT "LevelRole_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "LevelRole_guildId_level_key" ON "LevelRole"("guildId", "level");
CREATE INDEX "LevelRole_guildId_roleId_idx" ON "LevelRole"("guildId", "roleId");

CREATE TABLE "MemberLevel" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "xp" INTEGER NOT NULL DEFAULT 0,
    "level" INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT "MemberLevel_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "MemberLevel_guildId_userId_key" ON "MemberLevel"("guildId", "userId");
CREATE INDEX "MemberLevel_guildId_xp_idx" ON "MemberLevel"("guildId", "xp");

CREATE TABLE "EcoConfig" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "currency" TEXT NOT NULL DEFAULT 'coins',
    "dailyAmt" INTEGER NOT NULL DEFAULT 100,
    "weeklyAmt" INTEGER NOT NULL DEFAULT 500,
    CONSTRAINT "EcoConfig_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "EcoConfig_guildId_key" ON "EcoConfig"("guildId");

CREATE TABLE "MemberEco" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "wallet" INTEGER NOT NULL DEFAULT 0,
    "bank" INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT "MemberEco_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "MemberEco_guildId_userId_key" ON "MemberEco"("guildId", "userId");
CREATE INDEX "MemberEco_guildId_wallet_idx" ON "MemberEco"("guildId", "wallet");

CREATE TABLE "ShopItem" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "ecoConfigId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "roleId" TEXT NOT NULL,
    "price" INTEGER NOT NULL,
    "stock" INTEGER NOT NULL DEFAULT -1,
    CONSTRAINT "ShopItem_pkey" PRIMARY KEY ("id")
);
CREATE INDEX "ShopItem_guildId_idx" ON "ShopItem"("guildId");

CREATE TABLE "TicketConfig" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "categoryId" TEXT,
    "logChannel" TEXT,
    "supportRole" TEXT,
    "panelMsg" TEXT,
    "maxPerUser" INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT "TicketConfig_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "TicketConfig_guildId_key" ON "TicketConfig"("guildId");

CREATE TABLE "Ticket" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "channelId" TEXT NOT NULL,
    "ownerId" TEXT NOT NULL,
    "claimedBy" TEXT,
    "status" TEXT NOT NULL DEFAULT 'open',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "closedAt" TIMESTAMP(3),
    CONSTRAINT "Ticket_pkey" PRIMARY KEY ("id")
);
CREATE INDEX "Ticket_guildId_status_idx" ON "Ticket"("guildId", "status");
CREATE INDEX "Ticket_guildId_ownerId_status_idx" ON "Ticket"("guildId", "ownerId", "status");

CREATE TABLE "WelcomeConfig" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "welcomeChannel" TEXT,
    "welcomeMessage" TEXT,
    "welcomeCard" BOOLEAN NOT NULL DEFAULT false,
    "farewellChannel" TEXT,
    "farewellMessage" TEXT,
    "autoRoles" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "botAutoRoles" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    CONSTRAINT "WelcomeConfig_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "WelcomeConfig_guildId_key" ON "WelcomeConfig"("guildId");

CREATE TABLE "StatChannel" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "channelId" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    CONSTRAINT "StatChannel_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "StatChannel_guildId_type_key" ON "StatChannel"("guildId", "type");
CREATE INDEX "StatChannel_guildId_idx" ON "StatChannel"("guildId");

CREATE TABLE "Giveaway" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "channelId" TEXT NOT NULL,
    "messageId" TEXT NOT NULL,
    "prize" TEXT NOT NULL,
    "winnersCount" INTEGER NOT NULL,
    "endsAt" TIMESTAMP(3) NOT NULL,
    "ended" BOOLEAN NOT NULL DEFAULT false,
    "paused" BOOLEAN NOT NULL DEFAULT false,
    "entries" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "winners" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Giveaway_pkey" PRIMARY KEY ("id")
);
CREATE INDEX "Giveaway_guildId_ended_endsAt_idx" ON "Giveaway"("guildId", "ended", "endsAt");

CREATE TABLE "Reminder" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "guildId" TEXT,
    "channelId" TEXT NOT NULL,
    "message" TEXT NOT NULL,
    "remindAt" TIMESTAMP(3) NOT NULL,
    "done" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Reminder_pkey" PRIMARY KEY ("id")
);
CREATE INDEX "Reminder_userId_done_remindAt_idx" ON "Reminder"("userId", "done", "remindAt");
CREATE INDEX "Reminder_guildId_done_remindAt_idx" ON "Reminder"("guildId", "done", "remindAt");

CREATE TABLE "Cooldown" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "command" TEXT NOT NULL,
    "expiresAt" TIMESTAMP(3) NOT NULL,
    CONSTRAINT "Cooldown_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "Cooldown_guildId_userId_command_key" ON "Cooldown"("guildId", "userId", "command");
CREATE INDEX "Cooldown_expiresAt_idx" ON "Cooldown"("expiresAt");

ALTER TABLE "ModConfig" ADD CONSTRAINT "ModConfig_guildId_fkey" FOREIGN KEY ("guildId") REFERENCES "Guild"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "ModTier" ADD CONSTRAINT "ModTier_guildId_fkey" FOREIGN KEY ("guildId") REFERENCES "Guild"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "LogConfig" ADD CONSTRAINT "LogConfig_guildId_fkey" FOREIGN KEY ("guildId") REFERENCES "Guild"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "AutomodConfig" ADD CONSTRAINT "AutomodConfig_guildId_fkey" FOREIGN KEY ("guildId") REFERENCES "Guild"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "VerifyConfig" ADD CONSTRAINT "VerifyConfig_guildId_fkey" FOREIGN KEY ("guildId") REFERENCES "Guild"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "LevelConfig" ADD CONSTRAINT "LevelConfig_guildId_fkey" FOREIGN KEY ("guildId") REFERENCES "Guild"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "LevelRole" ADD CONSTRAINT "LevelRole_levelConfigId_fkey" FOREIGN KEY ("levelConfigId") REFERENCES "LevelConfig"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "EcoConfig" ADD CONSTRAINT "EcoConfig_guildId_fkey" FOREIGN KEY ("guildId") REFERENCES "Guild"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "ShopItem" ADD CONSTRAINT "ShopItem_ecoConfigId_fkey" FOREIGN KEY ("ecoConfigId") REFERENCES "EcoConfig"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "TicketConfig" ADD CONSTRAINT "TicketConfig_guildId_fkey" FOREIGN KEY ("guildId") REFERENCES "Guild"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "WelcomeConfig" ADD CONSTRAINT "WelcomeConfig_guildId_fkey" FOREIGN KEY ("guildId") REFERENCES "Guild"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "StatChannel" ADD CONSTRAINT "StatChannel_guildId_fkey" FOREIGN KEY ("guildId") REFERENCES "Guild"("id") ON DELETE CASCADE ON UPDATE CASCADE;
