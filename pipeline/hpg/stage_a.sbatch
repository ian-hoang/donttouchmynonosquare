#!/bin/bash
# Stage A on HiPerGator: download -> MediaPipe face/pose (CPU) -> 16 kHz FLAC of the analysis window.
# Usage: sbatch --array=0-(N-1)%40 pipeline/hpg/stage_a.sbatch <chunk_dir>
#SBATCH --job-name=pf-stageA
#SBATCH --account=ai-workshop
#SBATCH --qos=ai-workshop
#SBATCH --cpus-per-task=2
#SBATCH --mem=6gb
#SBATCH --time=03:00:00
#SBATCH --output=logs/stageA_%A_%a.out
set -u
cd /blue/ai-workshop/$USER/pokerface
export PATH=$PWD/.venv/bin:$PATH OMP_NUM_THREADS=2 PF_DELEGATE=CPU PF_SECTIONS=1 PF_CAPTIONS=0
CHUNK=$1/chunk_${SLURM_ARRAY_TASK_ID}.txt
while read -r vid; do
  [ -z "$vid" ] && continue
  .venv/bin/python -c "import sys,json; sys.path.insert(0,'pipeline'); from run_local import process; print(json.dumps(process('$vid')), flush=True)"
done < "$CHUNK"
