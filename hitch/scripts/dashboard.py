import html
import json
import logging
import os
from string import Template

import pandas as pd
import plotly.express as px

from hitch.helpers import get_db, get_dirs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dirs = get_dirs()

logger.info("Creating directories if they don't exist")
os.makedirs(dirs["dist"], exist_ok=True)

logger.info("Loading template and output paths")
template_path = os.path.join(dirs["templates"], "dashboard_template.html")
outname = os.path.join(dirs["dist"], "dashboard.html")

# Rides timeline
logger.info("Fetching ride events")
df = pd.read_sql(
    "select * from ride_event where submission_time is not null",
    get_db(),
)

if len(df) == 0:
    logger.warning("No ride events found, generating empty dashboard")
    df["datetime"] = pd.Series(dtype="datetime64[ns]")
else:
    # submission_time is RFC 9557 string, parse it
    df["datetime"] = pd.to_datetime(df["submission_time"], errors="coerce")
    df = df.dropna(subset=["datetime"])

logger.info(f"Got {len(df)} rides with valid timestamps")

fig = px.histogram(df["datetime"], title="Rides per month")
fig.update_xaxes(
    rangeselector=dict(
        buttons=list(
            [
                dict(count=1, label="1m", step="month", stepmode="backward"),
                dict(count=6, label="6m", step="month", stepmode="backward"),
                dict(count=1, label="1y", step="year", stepmode="backward"),
                dict(count=2, label="2y", step="year", stepmode="backward"),
                dict(count=5, label="5y", step="year", stepmode="backward"),
                dict(count=10, label="10y", step="year", stepmode="backward"),
                dict(step="all"),
            ]
        )
    ),
)
fig.update_layout(showlegend=False)
fig.update_layout(xaxis_title=None)
fig.update_layout(yaxis_title="# of rides")

logger.info("Generating HTML for rides timeline plot")
timeline_plot = fig.to_html("dash.html", full_html=False)


# User accounts
def e(s):
    return html.escape(s.replace("\n", "<br>"))


logger.info("Fetching user data")
users = pd.read_sql("select * from user", get_db())

# Count rides per hitchhiker nickname from ride_event
rides = pd.read_sql("select hitchhikers, source from ride_event", get_db())

nickname_counts = {}
for _, row in rides.iterrows():
    hitchhikers = row["hitchhikers"]
    if isinstance(hitchhikers, str):
        try:
            hitchhikers = json.loads(hitchhikers)
        except (json.JSONDecodeError, TypeError):
            continue
    if not isinstance(hitchhikers, list):
        continue
    for hh in hitchhikers:
        nickname = hh.get("nickname", "").lower() if isinstance(hh, dict) else ""
        if nickname:
            nickname_counts[nickname] = nickname_counts.get(nickname, 0) + 1


def get_num_reviews(username):
    return nickname_counts.get(username.lower(), 0)


logger.info("Generating user accounts section")
user_accounts = ""
count_inactive_users = 0
for _, user in users.iterrows():
    if get_num_reviews(user.username) >= 1:
        user_accounts += (
            f'<a href="/account/{e(user.username)}">{e(user.username)}</a>'
            + " - "
            + f'<a href="/?user={e(user.username)}#filters">Their spots</a>'
            + f" ({get_num_reviews(user.username)} rides)"
        )
        user_accounts += "<br>"
    else:
        count_inactive_users += 1
user_accounts += f"<br>There are {count_inactive_users} inactive users"


### Put together ###
logger.info("Combining all parts into the final HTML")
with open(template_path, encoding="utf-8") as template, open(outname, "w", encoding="utf-8") as out:
    output = Template(template.read()).substitute(
        {
            "timeline": timeline_plot,
            "user_accounts": user_accounts,
        }
    )
    out.write(output)

logger.info("DASHBOARD SCRIPT FINISHED")
