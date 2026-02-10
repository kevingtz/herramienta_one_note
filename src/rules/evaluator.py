import logging

logger = logging.getLogger("onenote_todo_sync")


class TaskEvaluator:
    """Evaluates whether a task needs a OneNote page based on configurable rules."""

    def __init__(self, rules_config: dict):
        self.positive_keywords = [
            kw.lower() for kw in rules_config.get("positive_keywords", [])
        ]
        self.negative_keywords = [
            kw.lower() for kw in rules_config.get("negative_keywords", [])
        ]
        self.force_onenote_prefix = rules_config.get("force_onenote_prefix", "#onenote").lower()
        self.force_skip_prefix = rules_config.get("force_skip_prefix", "#simple").lower()
        self.min_words = rules_config.get("min_words_for_complex", 8)
        self.threshold = rules_config.get("score_threshold", 2)

    def needs_onenote(self, task: dict) -> bool:
        """Determine if a task should have a OneNote page."""
        title = task.get("title", "")
        title_lower = title.lower()
        body = task.get("body", {})
        body_content = ""
        if isinstance(body, dict):
            body_content = body.get("content", "")
        elif isinstance(body, str):
            body_content = body

        # Manual overrides
        if self.force_onenote_prefix in title_lower:
            logger.debug("Task '%s' forced to OneNote by prefix", title)
            return True
        if self.force_skip_prefix in title_lower:
            logger.debug("Task '%s' forced to skip OneNote by prefix", title)
            return False

        score = self._calculate_score(title_lower, body_content)
        result = score >= self.threshold
        logger.debug("Task '%s' score=%d, needs_onenote=%s", title, score, result)
        return result

    def _calculate_score(self, title_lower: str, body_content: str) -> int:
        score = 0

        # Positive keyword matches
        for kw in self.positive_keywords:
            if kw in title_lower:
                score += 2

        # Negative keyword matches
        for kw in self.negative_keywords:
            if kw in title_lower:
                score -= 2

        # Word count: long titles suggest complexity
        word_count = len(title_lower.split())
        if word_count >= self.min_words:
            score += 1

        # Short titles suggest simple tasks
        if word_count < 4:
            score -= 1

        # Having body content suggests context/complexity
        if body_content.strip():
            score += 1

        return score
