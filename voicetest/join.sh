#!/bin/bash
# join.sh MODEL: out/MODEL-line1..N.wav -> out/MODEL-FULL.wav (24 kHz mono, 0.45 s between lines, like a narrator)
set -e; m=$1; args=(); f=""; n=0
for w in $(ls out/$m-line*.wav | sort -V); do args+=(-i "$w"); f+="[$n:a]aresample=24000,aformat=channel_layouts=mono,apad=pad_dur=0.45[a$n];"; n=$((n+1)); done
c=""; for i in $(seq 0 $((n-1))); do c+="[a$i]"; done
ffmpeg -y -loglevel error "${args[@]}" -filter_complex "${f}${c}concat=n=$n:v=0:a=1[o]" -map "[o]" "out/$m-FULL.wav"
echo "$m: $(ffprobe -v error -show_entries format=duration -of csv=p=0 out/$m-FULL.wav)s"
