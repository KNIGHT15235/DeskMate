from __future__ import annotations

from pydantic import BaseModel, Field

from likecc.tools.base import Tool, ToolResult


class QuestionItem(BaseModel):
    type: str = Field(description="Question type: text, radio, select, checkbox")
    name: str = Field(description="Question identifier")
    message: str = Field(description="Question text to display")
    options: list[str] = Field(
        default_factory=list,
        description="Options for radio/select/checkbox types",
    )


class AskUserParams(BaseModel):
    questions: list[QuestionItem] = Field(
        description="List of questions to ask the user", min_length=1,
    )


class AskUserTool(Tool):
    name = "AskUserQuestion"
    description = (
        "Ask the user one or more questions when you need information "
        "that cannot be determined from code or context alone. Supports "
        "text input, radio (single select), select, and checkbox (multi select) "
        "question types."
    )
    params_model = AskUserParams
    category: str = "read"
    is_system_tool = True
    should_defer = True


    async def execute(self, params: AskUserParams) -> ToolResult:
        # Agent publishes UserInputRequest before waiting on its run-scoped
        # Interaction. Direct invocation has no event/reply channel.
        return ToolResult(output="User input requires an interactive run", is_error=True)
