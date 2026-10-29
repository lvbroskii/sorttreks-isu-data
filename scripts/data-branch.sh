#!/usr/bin/env bash
# Only loads/appends the isolated evidence branch; never pushes main or force-pushes.
set -euo pipefail
operation=$1
archive_dir=$2
remote=$3
branch=${4:-pilot-data}
case "$branch" in pilot-data|pilot-validation) ;; *) echo "Unsupported evidence branch" >&2; exit 2 ;; esac
case "$operation" in
  load)
    test ! -e "$archive_dir"
    refs_file=$(mktemp)
    trap 'rm -f "$refs_file"' EXIT
    if git ls-remote --exit-code --heads "$remote" "refs/heads/$branch" > "$refs_file"; then
      git clone --depth=1 --single-branch --branch "$branch" "$remote" "$archive_dir"
    elif [ "$?" -eq 2 ]; then
      mkdir -p "$archive_dir"
      git -C "$archive_dir" init -b "$branch"
      git -C "$archive_dir" remote add origin "$remote"
    else
      echo 'Cannot inspect evidence branch; refusing to start with empty state.' >&2
      exit 1
    fi
    ;;
  save)
    test "$(git -C "$archive_dir" branch --show-current)" = "$branch"
    git -C "$archive_dir" config user.name 'ISU read-only pilot'
    git -C "$archive_dir" config user.email 'actions@users.noreply.github.com'
    git -C "$archive_dir" add --all -- . ":(exclude)*.tmp"
    if ! git -C "$archive_dir" diff --cached --quiet; then
      if [ "$branch" = pilot-validation ]; then
        message='Record synthetic offline workflow validation'
      else
        message='Archive read-only Montreal observation'
      fi
      git -C "$archive_dir" commit -m "$message"
      git -C "$archive_dir" push origin "HEAD:refs/heads/$branch"
    fi
    ;;
  *) echo 'Expected load or save' >&2; exit 2 ;;
esac
