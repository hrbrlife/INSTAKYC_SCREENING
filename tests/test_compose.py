import yaml
from pathlib import Path

def test_sanctions_core_configuration():
    compose = yaml.safe_load(Path("compose-sanctions.yml").read_text())
    services = compose.get("services", {})
    assert "sanctions_core" in services
    sanctions_core = services["sanctions_core"]

    env = sanctions_core.get("environment", {})
    assert env.get("YENTE_INDEX_URL") == "http://elasticsearch:9200"
    assert env.get("YENTE_DATA_PATH") == "/data/export.tar.gz"
    assert env.get("YENTE_SCHEDULE") == "0 */6 * * *"
    assert env.get("YENTE_AUTO_REINDEX") == "true"

    volumes = sanctions_core.get("volumes", [])
    assert "sanctions_data:/data:ro" in volumes
