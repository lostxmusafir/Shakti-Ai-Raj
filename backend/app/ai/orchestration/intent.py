from typing import List

class IntentClassifier:
    @staticmethod
    def classify(question: str, file_ids: List[str]) -> str:
        q = question.lower().strip()
        
        # Policy Evaluation
        if any(w in q for w in [
            "policy", "violate", "violation", "compliance", "rule book", "rulebook",
            "sec-", "fin-", "breach", "illegal", "security check", "audit"
        ]):
            return "POLICY_EVALUATION"
            
        conceptual_time_travel = any(phrase in q for phrase in (
            "time travel", "time machine", "grandfather paradox", "bootstrap paradox",
        ))
        data_anchors = (
            "sheet", "spreadsheet", "dataset", "file", "timestamp", "time stamp",
            "row", "column", "record", "location", "employee", "travel log",
        )
        if conceptual_time_travel and not any(anchor in q for anchor in data_anchors):
            return "GENERAL_CHAT"

        if not file_ids:
            return "GENERAL_CHAT"
            
        # Data Inspection / Dataset overview
        if any(w in q for w in [
            "schema", "columns", "headers", "preview", "inspect", "what is inside",
            "tell me about", "about the sheet", "about the file", "about the dataset",
            "explain sheet", "describe sheet", "dataset details", "what columns",
            "structure", "data profile", "sheet me kya hai", "dataset me kya hai",
            "data overview", "sheet overview"
        ]) and not any(w in q for w in ["split", "sum", "total", "average", "bheja", "kisne", "transfer", "blocked", "peak", "external"]):
            return "DATA_INSPECTION"
            
        if len(file_ids) > 1:
            return "MULTI_FILE_ANALYSIS"
            
        return "DATA_ANALYSIS"
