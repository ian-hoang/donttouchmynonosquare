#!/bin/sh
# Single uploader: ship finished windows from the Mac outbox to the HiPerGator inbox, one rsync at a time.
cd "$(dirname "$0")/.."
while true; do
  n=$(ls data/media/outbox/*.mp4 2>/dev/null | wc -l)
  if [ "$n" -gt 0 ]; then
    rsync -a --remove-source-files --include='*.mp4' --exclude='*' -e "ssh -o ControlPath=$HOME/.ssh/cm-hpg" data/media/outbox/ ojasvamishra@hpg.rc.ufl.edu:/blue/ai-workshop/ojasvamishra/pokerface/data/media/inbox/
  else
    sleep 5
  fi
done
