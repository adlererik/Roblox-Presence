"""Shared report window and bounded presence-history retention."""

REPORT_DAYS = 30
# One extra elapsed day covers local calendar boundaries and daylight saving.
HISTORY_RETENTION_DAYS = REPORT_DAYS + 1
