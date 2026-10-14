#!/bin/bash
set -euo pipefail

# command line arguments
if [[ $# -ne 1 || ! -d "$1" ]]; then
  echo "Usage: $0 <data-directory>" >&2
  exit 1
fi
data_dir=$1

# Remove logs older than 90 days before compressing the remaining logs.
find "$data_dir" -path '*/logs/*' -type f \
  \( -name '*.log' -o -name '*.log.gz' \) \
  ! -name 'launch.log' -mtime +90 \
  -delete -printf 'Removed %p\n'

# Compress logs older than 7 days beneath logs directories, excluding launch.log.
# Replace existing archives with the current log contents.
find "$data_dir" -path '*/logs/*' -name '*.log' ! -name 'launch.log' -type f -mtime +7 -exec bash -c '
  status=0
  for log do
    printf "Compressing %s\n" "$log"
    gzip -f -- "$log" < /dev/null || status=1
  done
  exit "$status"
' bash {} +
