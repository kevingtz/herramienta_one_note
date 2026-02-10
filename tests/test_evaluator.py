import pytest

from src.rules.evaluator import TaskEvaluator


@pytest.fixture
def evaluator(config):
    return TaskEvaluator(config["rules"])


class TestTaskEvaluator:
    def test_simple_task_negative_keyword(self, evaluator):
        task = {"title": "Pagar luz", "body": {"content": ""}}
        assert evaluator.needs_onenote(task) is False

    def test_complex_task_positive_keyword(self, evaluator):
        task = {"title": "Investigar opciones de migración", "body": {"content": ""}}
        assert evaluator.needs_onenote(task) is True

    def test_force_onenote_prefix(self, evaluator):
        task = {"title": "#onenote Revisar notas", "body": {"content": ""}}
        assert evaluator.needs_onenote(task) is True

    def test_force_skip_prefix(self, evaluator):
        task = {"title": "#simple Investigar algo", "body": {"content": ""}}
        assert evaluator.needs_onenote(task) is False

    def test_long_title_adds_score(self, evaluator):
        task = {
            "title": "Preparar la documentación completa del nuevo sistema de gestión de inventarios",
            "body": {"content": ""},
        }
        assert evaluator.needs_onenote(task) is True

    def test_short_simple_task(self, evaluator):
        task = {"title": "Comprar pan", "body": {"content": ""}}
        assert evaluator.needs_onenote(task) is False

    def test_task_with_body_content(self, evaluator):
        task = {
            "title": "Revisar el reporte mensual de ventas del equipo",
            "body": {"content": "Ver datos en SharePoint"},
        }
        # Long title (9 words) + body content -> score should be >= 2
        assert evaluator.needs_onenote(task) is True

    def test_body_as_string(self, evaluator):
        task = {"title": "Diseñar nuevo logo", "body": "notas extra"}
        assert evaluator.needs_onenote(task) is True

    def test_medium_length_neutral_task(self, evaluator):
        task = {"title": "Revisar correo electrónico", "body": {"content": ""}}
        # No positive/negative keywords, 3 words (short penalty -1)
        assert evaluator.needs_onenote(task) is False

    def test_multiple_positive_keywords(self, evaluator):
        task = {
            "title": "Diseñar estrategia del proyecto",
            "body": {"content": ""},
        }
        # diseñar (+2) + estrategia (+2) + proyecto (+2) = 6
        assert evaluator.needs_onenote(task) is True

    def test_mixed_signals(self, evaluator):
        task = {"title": "Llamar para resolver el problema", "body": {"content": ""}}
        # llamar (-2) + resolver (+2) = 0, < threshold
        assert evaluator.needs_onenote(task) is False

    def test_empty_task(self, evaluator):
        task = {"title": "", "body": {"content": ""}}
        assert evaluator.needs_onenote(task) is False
