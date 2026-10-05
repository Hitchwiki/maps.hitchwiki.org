"""Daily job: email a reminder for chat messages still unread a week after they arrived.

The logic lives in hitch/blueprints/utils/unread_message_reminders.py (see there for the
one-reminder-per-burst rule); this module only runs it, because `flask generate` executes
a script by importing it.
"""

import logging

from flask import current_app

from hitch.blueprints.utils.unread_message_reminders import remind_unread_messages

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

if not current_app.config.get("SPARKPOST_API_KEY"):
    logger.warning("SPARKPOST_API_KEY not set — skipping unread-message reminders")
else:
    logger.info("Done — %d unread-message reminder emails sent", remind_unread_messages())
