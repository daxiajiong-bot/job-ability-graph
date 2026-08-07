#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.neo4j.yml"
ENV_FILE="${ENV_FILE:-${PROJECT_ROOT}/.env}"
FALLBACK_ENV_FILE="${PROJECT_ROOT}/.env.example"

if [[ -f "${ENV_FILE}" ]]; then
  ENV_ARGS=(--env-file "${ENV_FILE}")
else
  ENV_ARGS=(--env-file "${FALLBACK_ENV_FILE}")
fi

cd "${PROJECT_ROOT}"

docker_compose() {
  docker compose "${ENV_ARGS[@]}" -f "${COMPOSE_FILE}" "$@"
}

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not installed or not in PATH. Install Docker Desktop first." >&2
    exit 127
  fi
  if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose v2 is required. Check Docker Desktop installation." >&2
    exit 127
  fi
}

env_value() {
  local key="$1"
  local default_value="$2"
  local source_file="${FALLBACK_ENV_FILE}"
  [[ -f "${ENV_FILE}" ]] && source_file="${ENV_FILE}"
  local value
  value="$(grep -E "^${key}=" "${source_file}" | tail -n 1 | cut -d= -f2- || true)"
  if [[ -n "${value}" ]]; then
    printf '%s' "${value}"
  else
    printf '%s' "${default_value}"
  fi
}

container_name() {
  env_value "NEO4J_CONTAINER_NAME" "job-ability-neo4j"
}

neo4j_password() {
  env_value "NEO4J_PASSWORD" "jobgraph_neo4j_2026"
}

wait_for_neo4j() {
  local name
  local password
  name="$(container_name)"
  password="$(neo4j_password)"
  echo "Waiting for Neo4j to accept Bolt connections..."
  for _ in {1..60}; do
    if docker exec "${name}" cypher-shell -u neo4j -p "${password}" "RETURN 1 AS ok;" >/dev/null 2>&1; then
      echo "Neo4j is ready: http://localhost:$(env_value "NEO4J_HTTP_PORT" "7474")"
      return 0
    fi
    sleep 2
  done
  echo "Neo4j did not become ready in time. Run: scripts/neo4j.sh logs" >&2
  return 1
}

usage() {
  cat <<'USAGE'
Usage: scripts/neo4j.sh <command>

Commands:
  start     Start Neo4j with docker compose and wait until it is ready
  stop      Stop Neo4j containers but keep named volumes
  restart   Restart Neo4j and wait until it is ready
  status    Show container status
  logs      Follow Neo4j logs
  shell     Open cypher-shell as user neo4j
  browser   Print Neo4j Browser and Bolt URLs
  reset     Stop Neo4j and delete local Neo4j named volumes

Set ENV_FILE=/path/to/.env to use a custom env file.
USAGE
}

command="${1:-}"
case "${command}" in
  start)
    require_docker
    docker_compose up -d
    wait_for_neo4j
    ;;
  stop)
    require_docker
    docker_compose down
    ;;
  restart)
    require_docker
    docker_compose restart
    wait_for_neo4j
    ;;
  status)
    require_docker
    docker_compose ps
    ;;
  logs)
    require_docker
    docker_compose logs -f neo4j
    ;;
  shell)
    require_docker
    docker exec -it "$(container_name)" cypher-shell -u neo4j -p "$(neo4j_password)"
    ;;
  browser)
    echo "Neo4j Browser: http://localhost:$(env_value "NEO4J_HTTP_PORT" "7474")"
    echo "Bolt URI: bolt://localhost:$(env_value "NEO4J_BOLT_PORT" "7687")"
    echo "Username: neo4j"
    echo "Password: $(neo4j_password)"
    ;;
  reset)
    require_docker
    docker_compose down -v
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "Unknown command: ${command}" >&2
    usage >&2
    exit 2
    ;;
esac
