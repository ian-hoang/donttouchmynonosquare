#!/bin/bash
# One L4 GPU draining the audio queue with faster-whisper; exits when Stage A is done (no idle GPU).
#SBATCH --job-name=pf-whisper
#SBATCH --account=ai-workshop
#SBATCH --qos=ai-workshop
#SBATCH --partition=hpg-b200
#SBATCH --gpus=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=24gb
#SBATCH --time=04:00:00
#SBATCH --output=logs/whisper_b200_%j.out
cd /blue/ai-workshop/$USER/pokerface
module load cuda/12.8.1 cudnn/9.6.0 >/dev/null 2>&1
export PATH=$PWD/.venv/bin:$PATH HF_HOME=/blue/ai-workshop/$USER/.hf
SP=$(.venv/bin/python -c "import site; print(site.getsitepackages()[0])")
export LD_LIBRARY_PATH=$SP/nvidia/cublas/lib:$SP/nvidia/cudnn/lib:${LD_LIBRARY_PATH:-}
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
.venv/bin/python pipeline/hpg/whisper_worker.py "$@"
