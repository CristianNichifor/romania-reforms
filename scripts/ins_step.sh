#!/usr/bin/env bash
#
# Run an importer that reads INS TEMPO, and treat "the source was not there" as a skip.
#
# `retea.UNREACHABLE` is 3, and an importer returns it only on the narrowest claim it can
# make: nothing was imported, every attempt failed the same way, and that way was the host
# refusing. Anything else keeps its own exit code and still fails the build.
#
# Why a wrapper rather than a few lines of shell in each step. The first version inlined
# `set +e` and an `exit 0` into three steps, and the `exit 0` was wrong in two of them: it
# ended the whole step, so an outage in Bucharest also skipped `build_multiplu_piata`,
# `build_randament_construit`, `build_randament_padure` and `build_valoare_nationala` —
# builders that read committed data and never touch INS. Exiting 0 from a wrapper lets the
# step carry on to them, and the `git diff --exit-code` that follows still runs: the importer
# wrote nothing, so there is nothing to diff, and the check becomes vacuous rather than either
# failing or being silently skipped.
#
# Usage:
#   scripts/ins_step.sh uv run python simulators/impozit-teren/scripts/import_populatie.py --all
set -u

"$@"
status=$?

if [ "$status" = "3" ]; then
  echo "::warning title=INS TEMPO unreachable::skipped, nothing imported: $*"
  exit 0
fi
exit "$status"
