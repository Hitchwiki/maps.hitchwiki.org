# @reboot cd hitch && screen -d -m bash -c '. $HOME/.bashrc; /usr/local/bin/waitress-serve server:app; bash'
# every minute
* * * * * cd /app && /usr/bin/flock -n /tmp/fetch_hitchhiking_events.lockfile bash -c '. $HOME/.bashrc; /usr/bin/node hitch/scripts/fetch_hitchhiking_events/dist/index.js' > logs/fetch_hitchhiking_events.log 2>&1
# every minute
* * * * * cd /app && /usr/bin/flock -n /tmp/show.lockfile bash -c '/usr/local/bin/flask --app hitch generate show' > logs/show.log 2>&1
# each day at midnight
# 0 0 * * * cd /app && /usr/bin/flock -n /tmp/dump.lockfile bash -c '. $HOME/.bashrc; /usr/local/bin/python flask --app hitch generate dump' > logs/dump.log 2>&1
# every day at midnight
# 0 0 * * * cd /app && /usr/bin/flock -n /tmp/dashboard.lockfile bash -c '. $HOME/.bashrc; /usr/local/bin/python flask --app hitch generate dashboard' > logs/dashboard.log 2>&1
# each day at 3
# 0 3 * * * cd /app && /usr/bin/flock -n /tmp/dashboard.lockfile bash -c '. $HOME/.bashrc; /usr/local/bin/python flask --app hitch generate fetch-roads' > logs/fetchroad.log 2>&1
# each day at midnight
# 0 0 * * * cd /app && /usr/bin/flock -n /tmp/dashboard.lockfile bash -c '. $HOME/.bashrc; /usr/local/bin/python flask --app hitch generate fetch-areas' > logs/fetcharea.log 2>&1
# every month
# 0 0 1 * * cd /app && /usr/bin/flock -n /tmp/hitchhiking.lockfile bash -c '. $HOME/.bashrc; /usr/local/bin/python flask --app hitch generate hitchhiking' > logs/heatmap.log 2>&1
