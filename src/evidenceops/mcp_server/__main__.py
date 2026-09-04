"""Console entry point for the local EvidenceOps MCP STDIO server."""

from evidenceops.retrieval.service import build_documentation_service
from evidenceops.settings import get_settings

from .server import create_server


def main() -> int:
    """Run the local MCP server over standard input and output only."""

    create_server(build_documentation_service(get_settings())).run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
