from typing import List
from app.ai.orchestration.context import AIContext

class IntentClassifier:
    @staticmethod
    def classify(question: str, file_ids: List[str]) -> str:
        q = question.lower()
        if any(w in q for w in ["policy", "violate", "violation", "compliance", "rule book"]):
            return "POLICY_EVALUATION"
        if not file_ids:
            return "GENERAL_CHAT"
        if len(file_ids) > 1:
            return "MULTI_FILE_ANALYSIS"
        if any(w in q for w in ["schema", "columns", "headers", "preview", "inspect", "what is inside"]):
            return "DATA_INSPECTION"
        return "DATA_ANALYSIS"
