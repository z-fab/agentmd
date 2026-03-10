import operator
from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """State for the ReAct graph. Messages are append-only."""

    messages: Annotated[Sequence[BaseMessage], operator.add]
