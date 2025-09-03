import html
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

# Spots
logger.info("Fetching data for spots")
df = pd.read_sql(
    "select * from points where not banned and datetime is not null",
    get_db(),
)

df["datetime"] = df["datetime"].astype("datetime64[ns]")

hist_data = df["datetime"]
fig = px.histogram(df["datetime"], title="Entries per month")


fig.update_xaxes(
    range=[
        "2006-01-01",
        pd.Timestamp.today().strftime("%Y-%m-%d"),
    ],
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
fig.update_layout(yaxis_title="# of entries")


logger.info("Generating HTML for spots timeline plot")
timeline_plot = fig.to_html("dash.html", full_html=False)

# Duplicates
logger.info("Fetching data for duplicates")
df = pd.read_sql(
    "select * from duplicates",
    get_db(),
)

df["datetime"] = df["datetime"].astype("datetime64[ns]")

hist_data = df["datetime"]
fig = px.histogram(df["datetime"], title="Entries per month")


fig.update_xaxes(
    range=[
        "2024-06-01",
        pd.Timestamp.today().strftime("%Y-%m-%d"),
    ],
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
fig.update_layout(yaxis_title="# of entries")


logger.info("Generating HTML for duplicates timeline plot")
timeline_plot_duplicate = fig.to_html("dash.html", full_html=False)


# TODO: necessary to track user prgress, move elsewhere later
def e(s):
    return html.escape(s.replace("\n", "<br>"))


logger.info("Fetching user points data")
points = pd.read_sql(
    sql="select * from points where not banned order by datetime is not null desc, datetime desc",
    con=get_db(),
)
points["user_id"] = points["user_id"].astype(pd.Int64Dtype())

logger.info("Fetching user data")
users = pd.read_sql("select * from user", get_db())
points["username"] = pd.merge(
    left=points[["user_id"]],
    right=users[["id", "username"]],
    left_on="user_id",
    right_on="id",
    how="left",
)["username"]
points["hitchhiker"] = points["nickname"].fillna(points["username"])
points["hitchhiker"] = points["hitchhiker"].str.lower()


def get_num_reviews(username):
    return len(points[points["hitchhiker"] == username.lower()])


logger.info("Generating user accounts section")
user_accounts = ""
count_inactive_users = 0
for _, user in users.iterrows():
    if get_num_reviews(user.username) >= 1:
        user_accounts += (
            f'<a href="/account/{e(user.username)}">{e(user.username)}</a>'
            + " - "
            + f'<a href="/?user={e(user.username)}#filters">Their spots</a>'
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
            "timeline_duplicate": timeline_plot_duplicate,
            "user_accounts": user_accounts,
        }
    )
    out.write(output)

logger.info("Dashboard generation complete")
