"""Mask contact details that hitchhikers typed into free-text ride fields.

The weekly Hugging Face dataset republishes ride comments verbatim, forever and
mirrored. A phone number, e-mail address or @handle in a comment is a contact
detail that the author shared with the next hitchhiker on the map, not with
every dataset downloader, so the export masks them. The site itself is unchanged.
"""

import re

# Requirement: be conservative. A false positive costs one masked token in a
# comment; a false negative leaves a stranger's number in a permanent public file.
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Digits grouped by spaces, dashes or parentheses only. A "." or "," inside the
# run means a coordinate or a date (52.5200, 13.4050 / 24.12.2019), not a phone.
# Without a leading +/00 it needs 9+ digits, which keeps year ranges (2015-2018)
# and 8-digit date stamps out; a +/00 prefix needs only 8.
PHONE_RE = re.compile(r"(?<![\w.,:/@-])(\+|00)?\d(?:[\s()-]{0,2}\d){7,14}(?![\w]|[.,]\d)")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
HANDLE_RE = re.compile(r"(?<![\w@])@[A-Za-z0-9_.]{3,30}\b")


def _mask_phone(m):
    if ISO_DATE_RE.match(m.group(0)):
        return m.group(0)
    digits = re.sub(r"\D", "", m.group(0))
    if not m.group(1) and len(digits) < 9:
        return m.group(0)
    # Runs of 6+ separated pairs ("##-##-##-##...") are a list, not a number.
    if m.group(0).count("-") >= 5:
        return m.group(0)
    return "[phone removed]"


def redact_text(text):
    if not isinstance(text, str) or not text:
        return text
    text = EMAIL_RE.sub("[email removed]", text)
    text = PHONE_RE.sub(_mask_phone, text)
    return HANDLE_RE.sub("[handle removed]", text)
