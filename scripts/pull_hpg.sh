#!/bin/sh
# Pull Stage A outputs (landmarks, face crops, audio, transcripts) from HiPerGator into data/cache/.
set -e
R=ojasvamishra@hpg.rc.ufl.edu:/blue/ai-workshop/ojasvamishra/pokerface/data/cache/
for d in vision audio transcripts; do
  mkdir -p "data/cache/$d"
  rsync -az --exclude '*.part' --exclude '*.tmp' --exclude '_subs' -e "ssh -o ControlPath=$HOME/.ssh/cm-hpg" "$R$d/" "data/cache/$d/"
done
echo "vision $(ls data/cache/vision/*.vision.json 2>/dev/null | wc -l) audio $(ls data/cache/audio/*.flac 2>/dev/null | wc -l) whisper $(ls data/cache/transcripts/*.whisper.json 2>/dev/null | wc -l)"
