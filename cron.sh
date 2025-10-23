# @reboot cd hitch && screen -d -m bash -c '. $HOME/.bashrc; /usr/local/bin/waitress-serve server:app; bash'
# every 10 minutes
# */10 * * * * cd /app && /usr/bin/flock -n /tmp/fetch_nostr.lockfile bash -c '/usr/local/bin/flask --app hitch generate fetch_nostr' > logs/fetch_nostr.log 2>&1
# every minute
* * * * * cd /app && /usr/bin/flock -n /tmp/show.lockfile bash -c '/usr/local/bin/flask --app hitch generate show' > logs/show.log 2>&1
# every day at 2 AM
0 7 * * * cd /app && /usr/bin/flock -n /tmp/sync_upstream.lockfile bash -c '/usr/local/bin/flask --app hitch generate sync_upstream' > logs/sync_upstream.log 2>&1
# each day at midnight
# 0 0 * * * cd /app && /usr/bin/flock -n /tmp/dump.lockfile bash -c '. $HOME/.bashrc; /usr/local/bin/python flask --app hitch generate dump' > logs/dump.log 2>&1
# every day at midnight
# 0 0 * * * cd /app && /usr/bin/flock -n /tmp/dashboard.lockfile bash -c '. $HOME/.bashrc; /usr/local/bin/python flask --app hitch generate dashboard' > logs/dashboard.log 2>&1
# each day at 3
# 0 3 * * * cd /app && /usr/bin/flock -n /tmp/dashboard.lockfile bash -c '. $HOME/.bashrc; /usr/local/bin/python flask --app hitch generate fetch-roads' > logs/fetchroad.log 2>&1
# each day at midnight
# 0 0 * * * cd /app && /usr/bin/flock -n /tmp/dashboard.lockfile bash -c '. $HOME/.bashrc; /usr/local/bin/python flask --app hitch generate fetch-areas' > logs/fetcharea.log 2>&1
# every month
# Note: hitchhiking heatmap functionality has been moved to show.py
