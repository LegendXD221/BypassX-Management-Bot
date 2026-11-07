-- CreateTable
CREATE TABLE "StarboardConfig" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "enabled" BOOLEAN NOT NULL DEFAULT false,
    "channelId" TEXT,
    "threshold" INTEGER NOT NULL DEFAULT 3,
    "emoji" TEXT NOT NULL DEFAULT '⭐',
    "allowSelfStar" BOOLEAN NOT NULL DEFAULT false,
    "ignoredChannels" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "StarboardConfig_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "StarboardConfig_guildId_key" ON "StarboardConfig"("guildId");

-- CreateTable
CREATE TABLE "StarboardMessage" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "sourceMessageId" TEXT NOT NULL,
    "sourceChannelId" TEXT NOT NULL,
    "starboardMessageId" TEXT,
    "authorId" TEXT NOT NULL,
    "content" TEXT NOT NULL DEFAULT '',
    "attachmentUrls" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "stars" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    CONSTRAINT "StarboardMessage_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "StarboardMessage_guildId_sourceMessageId_key" ON "StarboardMessage"("guildId", "sourceMessageId");
CREATE INDEX "StarboardMessage_guildId_stars_idx" ON "StarboardMessage"("guildId", "stars");
CREATE INDEX "StarboardMessage_guildId_authorId_createdAt_idx" ON "StarboardMessage"("guildId", "authorId", "createdAt");

-- CreateTable
CREATE TABLE "EngagementDaily" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "date" TEXT NOT NULL,
    "messages" INTEGER NOT NULL DEFAULT 0,
    "reactions" INTEGER NOT NULL DEFAULT 0,
    "joins" INTEGER NOT NULL DEFAULT 0,
    "leaves" INTEGER NOT NULL DEFAULT 0,
    "activeUsers" INTEGER NOT NULL DEFAULT 0,
    "topChannels" JSONB,
    CONSTRAINT "EngagementDaily_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "EngagementDaily_guildId_date_key" ON "EngagementDaily"("guildId", "date");
CREATE INDEX "EngagementDaily_guildId_date_idx" ON "EngagementDaily"("guildId", "date");

ALTER TABLE "StarboardConfig" ADD CONSTRAINT "StarboardConfig_guildId_fkey"
    FOREIGN KEY ("guildId") REFERENCES "Guild"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "StarboardMessage" ADD CONSTRAINT "StarboardMessage_guildId_fkey"
    FOREIGN KEY ("guildId") REFERENCES "Guild"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "EngagementDaily" ADD CONSTRAINT "EngagementDaily_guildId_fkey"
    FOREIGN KEY ("guildId") REFERENCES "Guild"("id") ON DELETE CASCADE ON UPDATE CASCADE;
