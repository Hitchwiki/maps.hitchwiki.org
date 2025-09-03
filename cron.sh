# @reboot cd hitch && screen -d -m bash -c '. $HOME/.bashrc; /usr/local/bin/waitress-serve server:app; bash'
# every minute
* * * * * cd hitch && /usr/bin/flock -n /tmp/show.lockfile bash -c '. $HOME/.bashrc; /usr/local/bin/python flask --app hitch generate show' > showlog.txt 2>&1
# each day at midnight
0 0 * * * cd hitch && /usr/bin/flock -n /tmp/dump.lockfile bash -c '. $HOME/.bashrc; /usr/local/bin/python flask --app hitch generate dump' > dumplog.txt 2>&1
# every day at midnight
0 0 * * * cd hitch && /usr/bin/flock -n /tmp/dashboard.lockfile bash -c '. $HOME/.bashrc; /usr/local/bin/python flask --app hitch generate dashboard' > dashboardlog.txt 2>&1
# each day at 3
0 3 * * * cd hitch && /usr/bin/flock -n /tmp/dashboard.lockfile bash -c '. $HOME/.bashrc; /usr/local/bin/python flask --app hitch generate fetch-roads' > logs/fetchroadlog.txt 2>&1
# each day at midnight
0 0 * * * cd hitch && /usr/bin/flock -n /tmp/dashboard.lockfile bash -c '. $HOME/.bashrc; /usr/local/bin/python flask --app hitch generate fetch-areas' > logs/fetcharealog.txt 2>&1
# every month
0 0 1 * * cd hitch && /usr/bin/flock -n /tmp/hitchhiking.lockfile bash -c '. $HOME/.bashrc; /usr/local/bin/python flask --app hitch generate hitchhiking' > heatmaplog.txt 2>&1

