#!/bin/bash
# 补齐 realesrgan_full.zip 的缺失区间并组装校验
# （GitHub 直连超时时的镜像分块下载辅助脚本，用法见 README）
set -u
cd "$(dirname "$0")/.."   # 项目根目录（不依赖本地绝对路径）
URL="https://gh-proxy.com/https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip"
SIZE=45474481
N=12
CHUNK=$(( (SIZE + N - 1) / N ))
D=tools_test/chunks

# 清掉上一任务遗留的 curl 进程，防止并发写坏分块文件
taskkill //F //IM curl.exe >/dev/null 2>&1
sleep 1

fetch_range() { # A B out
  local A=$1 B=$2 OUT=$3
  local WANT=$((B - A + 1))
  for try in 1 2 3 4 5 6; do
    local HAVE=0
    [ -f "$OUT" ] && HAVE=$(stat -c%s "$OUT")
    [ "$HAVE" -ge "$WANT" ] && return 0
    curl -sL --connect-timeout 15 --max-time 150 -r $((A + HAVE))-$B -o - "$URL" >> "$OUT" 2>/dev/null
  done
  HAVE=$(stat -c%s "$OUT" 2>/dev/null || echo 0)
  [ "$HAVE" -ge "$WANT" ]
}

for ROUND in 1 2 3 4; do
  MISSING=0
  for i in $(seq 0 $((N-1))); do
    S=$((i * CHUNK)); E=$(( (i + 1) * CHUNK - 1 )); [ $E -ge $SIZE ] && E=$((SIZE - 1))
    WANT=$((E - S + 1))
    HAVE=0; [ -f "$D/p$i" ] && HAVE=$(stat -c%s "$D/p$i")
    REM=$((WANT - HAVE))
    [ "$REM" -le 0 ] && continue
    MISSING=$((MISSING + 1))
    K=4
    SUB=$(( (REM + K - 1) / K ))
    for j in $(seq 0 $((K-1))); do
      A=$((S + HAVE + j * SUB)); B=$((A + SUB - 1)); [ $B -gt $E ] && B=$E
      [ $A -gt $E ] && continue
      fetch_range $A $B "$D/s${i}_${j}" &
    done
  done
  wait
  echo "round $ROUND done, chunks still missing: $MISSING"
  [ "$MISSING" -eq 0 ] && break
done

# 组装
OUT=tools_test/realesrgan_full.zip
rm -f "$OUT"
OK=1
for i in $(seq 0 $((N-1))); do
  S=$((i * CHUNK)); E=$(( (i + 1) * CHUNK - 1 )); [ $E -ge $SIZE ] && E=$((SIZE - 1))
  WANT=$((E - S + 1))
  CATSIZE=0
  parts="$D/p$i"
  HAVE=0; [ -f "$D/p$i" ] && HAVE=$(stat -c%s "$D/p$i")
  if [ "$HAVE" -lt "$WANT" ]; then
    for j in $(seq 0 3); do
      [ -f "$D/s${i}_${j}" ] && parts="$parts $D/s${i}_${j}"
    done
  fi
  for f in $parts; do
    CS=$(stat -c%s "$f")
    cat "$f" >> "$OUT"
    CATSIZE=$((CATSIZE + CS))
  done
  if [ "$CATSIZE" -ne "$WANT" ]; then
    echo "CHUNK $i MISMATCH: got $CATSIZE want $WANT"
    OK=0
  fi
done
FINAL=$(stat -c%s "$OUT")
echo "final size: $FINAL / $SIZE, ok=$OK"
if [ "$FINAL" -eq "$SIZE" ]; then
  echo ASSEMBLE_OK
  rm -rf "$D"
fi
