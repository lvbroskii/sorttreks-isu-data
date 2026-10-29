#!/usr/bin/env bash
# Only loads/appends the isolated evidence branch; never pushes main or force-pushes.
set -euo pipefail
operation=$1
archive_dir=$2
remote=$3
case "$operation" in
  load)
    test ! -e "$archive_dir"
    refs_file=$(mktemp)
    trap 'rm -f "$refs_file"' EXIT
    if git ls-remote --exit-code --heads "$remote" refs/heads/pilot-data > "$refs_file"; then
      git clone --depth=1 --single-branch --branch pilot-data "$remote" "$archive_dir"
    elif [ "$?" -eq 2 ]; then
      mkdir -p "$archive_dir"
      git -C "$archive_dir" init -b pilot-data
      git -C "$archive_dir" remote add origin "$remote"
    else
      echo 'Cannot inspect evidence branch; refusing to start with empty state.' >&2
      exit 1
    fi
    ;;
  save)
    test "$(git -C "$archive_dir" branch --show-current)" = pilot-data
    git -C "$archive_dir" config user.name 'ISU read-only pilot'
    git -C "$archive_dir" config user.email 'actions@users.noreply.github.com'
    git -C "$archive_dir" add --all -- . ":(exclude)*.tmp"
    if ! git -C "$archive_dir" diff --cached --quiet; then
      git -C "$archive_dir" commit -m 'Archive read-only Montreal observation'
      git -C "$archive_dir" push origin HEAD:refs/heads/pilot-data
    fi
    ;;
  *) echo 'Expected load or save' >&2; exit 2 ;;
esac
