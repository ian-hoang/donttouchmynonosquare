# Running the heavy pipeline on HiPerGator

Split of work:
- **Mac (orchestrator):** YouTube search and download (residential/campus IP; datacenter IPs get bot-checked),
  research layer, backtests, note.
- **HiPerGator (muscle):** per-video feature extraction as a SLURM job array: MediaPipe face + pose on CPU
  cores, Whisper large-v3 on GPU (faster-whisper/CUDA), openSMILE. Only `video_features` rows come back.

## One-time setup (you do this; Claude never sees your password or Duo)

1. Add this block to `~/.ssh/config` (replace the username if your GatorLink differs):

```
Host hpg
    HostName hpg.rc.ufl.edu
    User ojasvamishra
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h-%p
    ControlPersist 18h
    ServerAliveInterval 60
```

2. In a terminal, run `ssh hpg` once and complete password + Duo. Leave it open (or close it; the
   master connection persists for 18h). After that, `ssh hpg <command>` and `rsync ... hpg:` run without
   prompting, which is how the pipeline drives the cluster.

3. Hackathon allocation (UF Research Computing email, 2026-10-01): user `ojasvamishra`, group/account
   **`ai-workshop`** (`--account=ai-workshop --qos=ai-workshop`), storage under `/blue/ai-workshop/`.
   The group shares **250 NCUs, 5 GPUs and 2 TB of Blue storage across all participants**. We request at
   most 48 cores and 1 GPU at a time, cap wall time, and delete media as soon as it is processed.
   The HiPerGator New User Training is mandatory before first use.

## What the pipeline does on HPG
```
/blue/<group>/<user>/pokerface/        code + venv (module load python/3.12, cuda)
  media/<video_id>.{mp4,m4a}           rsynced from the Mac in batches, deleted after extraction
  out/<video_id>.json                  per-video features, rsynced back
sbatch --array=0-N%64 pipeline/hpg/extract_array.sbatch   # 64 concurrent tasks, 4 CPUs each
sbatch pipeline/hpg/whisper_gpu.sbatch                     # one GPU worker draining the audio queue
```
