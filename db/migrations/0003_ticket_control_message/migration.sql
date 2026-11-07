-- Add persisted control-message identity for restart-safe ticket controls
ALTER TABLE "Ticket" ADD COLUMN "controlMessageId" TEXT;
