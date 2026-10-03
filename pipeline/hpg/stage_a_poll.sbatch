#!/bin/bash
# Compute-only Stage A worker: processes videos uploaded by the Mac feeder into data/media/inbox/.
#SBATCH --job-name=pf-poll
#SBATCH --account=ai-workshop
#SBATCH --cpus-per-task=2
#SBATCH --mem=6gb
#SBATCH --time=04:00:00
#SBATCH --output=logs/poll_%A_%a.out
cd /blue/ai-workshop/$USER/pokerface
export PATH=$PWD/.venv/bin:$PATH OMP_NUM_THREADS=2 PF_DELEGATE=CPU
.venv/bin/python pipeline/hpg/stage_a_poll.py --max-idle 900
