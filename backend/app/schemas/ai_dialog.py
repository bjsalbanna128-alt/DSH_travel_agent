from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

DialogField = Literal["destination", "days", "travel_time", "budget_total", "pace"]
Pace = Literal["relaxed", "moderate", "intensive"]
Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class DialogConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    introduction: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""
    order: list[DialogField] = Field(min_length=5, max_length=5)
    required: list[DialogField] = Field(min_length=2, max_length=5)
    questions: dict[DialogField, Question]
    default_budget: float | None = Field(None, ge=0, allow_inf_nan=False)
    default_pace: Pace | None = None

    @field_validator("introduction", "questions")
    @classmethod
    def plain_text(cls, value):
        texts = value.values() if isinstance(value, dict) else [value]
        if any(any(char in text for char in "<>{}") for text in texts):
            raise ValueError("请输入纯文本，不能包含脚本或变量占位符")
        return value

    @model_validator(mode="before")
    @classmethod
    def upgrade_old_config(cls, value):
        """旧配置只有四个字段：升级时补上「出发日期」，并默认设为必问。"""
        if not isinstance(value, dict):
            return value
        order = list(value.get("order") or [])
        if "travel_time" in order:
            return value
        upgraded = dict(value)
        if "days" in order:
            order.insert(order.index("days") + 1, "travel_time")
        else:
            order.append("travel_time")
        questions = dict(value.get("questions") or {})
        questions.setdefault("travel_time", "你计划哪天出发？可以说日期或季节。")
        required = list(value.get("required") or [])
        if "travel_time" not in required:
            required.append("travel_time")
        upgraded.update(order=order, questions=questions, required=required)
        return upgraded

    @model_validator(mode="after")
    def check_fields(self):
        fields = {"destination", "days", "travel_time", "budget_total", "pace"}
        if set(self.order) != fields:
            raise ValueError("追问顺序必须包含五个互不重复的字段")
        if len(set(self.required)) != len(self.required) or not {"destination", "days"} <= set(self.required):
            raise ValueError("目的地、天数始终必问，必问项不能重复")
        if set(self.questions) != fields:
            raise ValueError("五个字段均须填写追问文案")
        if "budget_total" in self.required and self.default_budget is not None:
            raise ValueError("必问预算不能设置默认值")
        if "pace" in self.required and self.default_pace is not None:
            raise ValueError("必问节奏不能设置默认值")
        return self


INITIAL_DIALOG = DialogConfig(
    order=["destination", "days", "travel_time", "budget_total", "pace"],
    required=["destination", "days", "travel_time"],
    questions={
        "destination": "你想去哪个城市或目的地？",
        "days": "你计划玩几天？",
        "travel_time": "你计划哪天出发？可以说日期或季节。",
        "budget_total": "这次旅行总预算大约是多少元？",
        "pace": "你喜欢轻松、适中还是紧凑的旅行节奏？",
    },
    default_budget=0,
    default_pace="moderate",
)


class DialogRevision(BaseModel):
    expected_revision: int = Field(ge=1, strict=True)


class SaveDialog(DialogRevision):
    config: DialogConfig


class TrialDialog(DialogRevision):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    continuation: str | None = Field(None, max_length=32000)

