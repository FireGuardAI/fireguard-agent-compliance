class ComplianceError(Exception):
    """Base exception for the compliance agent domain."""


class RetrievalClientError(ComplianceError):
    """Raised when calling fireguard-agent-retrieval fails (network,
    timeout, or non-200 response)."""


class ComplianceEngineError(ComplianceError):
    """Raised when the Gemini API call itself fails (auth, quota,
    network, timeout — after retries are exhausted)."""


class LLMResponseParsingError(ComplianceError):
    """Raised when Gemini's response isn't valid JSON, or doesn't match
    the expected ComplianceResponse schema."""
