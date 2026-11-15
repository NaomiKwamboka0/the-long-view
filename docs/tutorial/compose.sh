#!/bin/bash
# Put one episode together: the screen recording, the frame around it, the guide and the voice.
set -e; cd "$(dirname "$0")"; ep=$1; total=$(python3 -c "import json;print(json.load(open('plan-$ep.json'))['total'])")
ffmpeg -loglevel error -y -i screen-$ep.mp4 -f concat -safe 0 -i chrome-$ep.txt -i guide-$ep.mp4 -i voice-$ep.wav -filter_complex \
 "[0:v]fps=30,pad=1280:720:24:60:color=0xeef2ee[bg];[1:v]fps=30,format=rgba[ch];[bg][ch]overlay=0:0[a];[a][2:v]overlay=1000:12,format=yuv420p[v];[3:a]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[au]" \
 -map "[v]" -map "[au]" -t $total -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k -movflags +faststart hatua-$ep.part.mp4
mv hatua-$ep.part.mp4 hatua-$ep.mp4; ls -la hatua-$ep.mp4
