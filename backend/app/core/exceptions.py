"""Exception hierarchy for the travel agent system."""


class TravelAgentError(Exception):
    """Base exception for all travel agent errors."""


class AgentError(TravelAgentError):
    """Raised when an agent node fails during execution."""


class LLMCallError(AgentError):
    """Raised when an LLM API call fails."""


class ParseError(AgentError):
    """Raised when LLM output cannot be parsed into structured data."""


class RetryExhaustedError(AgentError):
    """Raised when all retry attempts are exhausted."""


class ConstraintViolationError(TravelAgentError):
    """Raised when itinerary violates hard constraints."""


class DependencyError(TravelAgentError):
    """Raised when agent dependencies are not met."""


class CircuitBreakerOpenError(AgentError):
    """Raised when the circuit breaker is open for an agent."""
