-- CreateTable
CREATE TABLE "ReactionRolePanel" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "channelId" TEXT NOT NULL,
    "messageId" TEXT,
    "mode" TEXT NOT NULL DEFAULT 'buttons',
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "ReactionRolePanel_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "ReactionRolePanel_guildId_enabled_idx" ON "ReactionRolePanel"("guildId", "enabled");

-- CreateTable
CREATE TABLE "ReactionRole" (
    "id" TEXT NOT NULL,
    "guildId" TEXT NOT NULL,
    "panelId" TEXT NOT NULL,
    "emoji" TEXT NOT NULL,
    "roleId" TEXT NOT NULL,
    "label" TEXT,
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    CONSTRAINT "ReactionRole_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "ReactionRole_panelId_emoji_key" ON "ReactionRole"("panelId", "emoji");
CREATE INDEX "ReactionRole_guildId_roleId_idx" ON "ReactionRole"("guildId", "roleId");

ALTER TABLE "ReactionRolePanel" ADD CONSTRAINT "ReactionRolePanel_guildId_fkey"
    FOREIGN KEY ("guildId") REFERENCES "Guild"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "ReactionRole" ADD CONSTRAINT "ReactionRole_panelId_fkey"
    FOREIGN KEY ("panelId") REFERENCES "ReactionRolePanel"("id") ON DELETE CASCADE ON UPDATE CASCADE;
