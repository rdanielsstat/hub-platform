#!/usr/bin/env bash
# Prints the SemVer SERVICE_VERSION for HEAD, from the nearest release tag
# (vX.Y.Z; pre-release tags like v2.0.0-rc.1 are ignored):
#
#   no release tag reachable   0.0.0+<sha>
#   HEAD is tagged v1.2.0      1.2.0
#   2 commits after v1.2.0     1.2.0+2.g<sha>
#
# Build metadata (+...) sorts the same as the release it follows, and the
# result is SemVer but not a valid Docker tag, which is why image tags
# stay timestamp-sha (ci.yml). Needs full history and tags: in Actions,
# check out with fetch-depth: 0. Tested by backend/tests/test_service_version.py.
set -euo pipefail

if ! desc=$(git describe --tags --long \
    --match 'v[0-9]*.[0-9]*.[0-9]*' --exclude 'v*-*' 2>/dev/null); then
  echo "0.0.0+$(git rev-parse --short HEAD)"
  exit 0
fi

# --long always gives v<version>-<commits since tag>-g<sha>.
if [[ ! $desc =~ ^v([0-9]+\.[0-9]+\.[0-9]+)-([0-9]+)-(g[0-9a-f]+)$ ]]; then
  echo "service-version: can't parse release tag from '$desc'" >&2
  exit 1
fi
version=${BASH_REMATCH[1]}
commits=${BASH_REMATCH[2]}
sha=${BASH_REMATCH[3]}

if [[ $commits == 0 ]]; then
  echo "$version"
else
  echo "$version+$commits.$sha"
fi
