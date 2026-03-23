"""ClaimState definition with Annotated reducers for LangGraph."""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class ClaimState(TypedDict):
    """State for the expense claim workflow.

    This is the shared state passed between all agent nodes in the LangGraph.
    Phase 1 intentionally keeps it minimal - future phases will expand with
    receipt data, findings, policy results, etc.
    """

    claimId: str
    status: str
    messages: Annotated[list[AnyMessage], add_messages]
