import os
import tempfile

import pytest
import yaml


@pytest.fixture
def config():
    """Default test configuration."""
    return {
        "notebook_name": "My Notebook",
        "monitored_lists": ["Hoy", "Esta semana", "En espera"],
        "polling_interval_seconds": 30,
        "list_to_section_map": {
            "Hoy": "Hoy",
            "Esta semana": "Esta semana",
            "En espera": "En espera",
        },
        "rules": {
            "positive_keywords": [
                "preparar", "diseñar", "investigar", "organizar",
                "resolver", "planear", "propuesta", "presentación",
                "proyecto", "analizar", "evaluar", "documentar", "estrategia",
            ],
            "negative_keywords": [
                "pagar", "comprar", "llamar", "enviar",
                "mandar", "imprimir", "agendar", "recordar",
            ],
            "force_onenote_prefix": "#onenote",
            "force_skip_prefix": "#simple",
            "min_words_for_complex": 8,
            "score_threshold": 2,
        },
        "weekly_review": {
            "enabled": True,
            "day": "sunday",
            "time": "18:00",
            "duration_minutes": 30,
        },
        "logging": {
            "level": "DEBUG",
            "file_path": "/tmp/onenote_todo_sync_test.log",
            "max_file_size_mb": 1,
            "backup_count": 1,
        },
    }


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def config_file(config, tmp_path):
    """Write config to a temporary YAML file."""
    config_path = tmp_path / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    return str(config_path)
