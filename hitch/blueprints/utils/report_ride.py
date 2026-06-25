"""Shared constants for the ride-reporting feature.

A ride can be reported by logged-in users; once REPORTS_TO_HIDE distinct users report it
for the same reason, show.py drops it from the generated map data (see show.py).
"""

# Allowed report reasons mapped to their human-readable labels (shown on the report form).
# Keys are stored in RideReport.reason; keep them stable since they're persisted.
REPORT_REASONS = {
    "advertising": "Advertising / spam",
    "non_existing_spot": "Non-existing spot",
}

# A ride is auto-hidden once at least this many distinct users report it for the same
# reason. Because reports are unique per (ride, user), this is a count of distinct people.
REPORTS_TO_HIDE = 2
