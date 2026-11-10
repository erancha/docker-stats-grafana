#!/usr/bin/env bash
#
# Build the consumer image and push it to Docker Hub as DOCKER_USERNAME/docker-stats-grafana.
#
#   ./scripts/build-push-consumer.sh [--platform PLATFORM] [VERSION]
#
#   VERSION              the tag to push (default: latest); a named version is pushed as latest too
#   --platform PLATFORM  the architecture to build for (default: linux/arm64)
#   -h, --help
#
#   ./scripts/build-push-consumer.sh
#   ./scripts/build-push-consumer.sh --platform linux/amd64 1.2.0
#
# An image runs only on the architecture it was built for; the default is the architecture of
# the deployed host. Requires DOCKER_USERNAME in .env and a completed "docker login"; without
# the login the push fails with Docker's own message.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

PLATFORM="linux/arm64"
VERSION="latest"
while [ $# -gt 0 ]; do
  case "$1" in
    --platform)
      [ $# -ge 2 ] || { print_help >&2; exit 2; }
      PLATFORM="$2"; shift ;;
    -h|--help) print_help; exit 0 ;;
    -*) print_help >&2; exit 2 ;;
    *) VERSION="$1" ;;
  esac
  shift
done

require_env
require_docker
IMAGE="$(env_value "$ENV_FILE" DOCKER_USERNAME)/docker-stats-grafana"

tags=("$IMAGE:$VERSION")
if [ "$VERSION" != latest ]; then
  tags+=("$IMAGE:latest")
fi

build=(docker build --platform "$PLATFORM")
for tag in "${tags[@]}"; do build+=(-t "$tag"); done
echo "Building ${tags[*]} for $PLATFORM..."
"${build[@]}" "$CONSUMER"

for tag in "${tags[@]}"; do
  echo "Pushing $tag..."
  docker push "$tag"
done
echo "Pushed. Pull it with:  docker pull ${tags[0]}"
