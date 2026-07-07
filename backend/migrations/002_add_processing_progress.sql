-- Migration: Add processing_progress field to pending_reviews
-- Date: 2026-03-01
-- Purpose: Support real-time progress tracking during reanalysis

ALTER TABLE pending_reviews ADD COLUMN processing_progress TEXT;

-- Update status column to support 'processing' state
-- Note: SQLite doesn't support ALTER COLUMN, so we document the change here
-- The 'status' column now accepts: 'pending', 'approved', 'rejected', 'processing'
