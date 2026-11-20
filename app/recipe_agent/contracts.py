from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

PositiveId = Annotated[int, Field(gt=0)]
Selector = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
]
Name = Literal[
    "full_name_raw",
    "bib",
    "gender",
    "status",
    "place_abs",
    "place_gender",
    "chip_time_s",
    "gun_time_s",
    "club_raw",
    "city",
    "age_group",
    "birth_year",
]
PlaceBy = Literal["chip", "gun"]
Status = Literal["FIN", "DNF", "DNS", "DSQ", "NC", "LAP"]
Time = Annotated[float, Field(gt=0, le=604800, allow_inf_nan=False)]
REQUIRED_RECIPE_FIELDS = ("full_name_raw", "gender", "place_abs")


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, loc_by_alias=False
    )


class RecipeField(Contract):
    name: Name
    selector: Selector
    type: Literal["text", "attribute", "regex"] = Field(
        description=(
            "Use text for a whole cell. Type attribute requires an attribute key. "
            "Type regex requires a pattern key at the same level as name and selector."
        )
    )
    attribute: (
        Annotated[
            str, StringConstraints(pattern=r"^(data-[\w-]+|title|value|aria-label)$")
        ]
        | None
    ) = None
    pattern: Annotated[str, StringConstraints(min_length=1, max_length=160)] | None = (
        None
    )

    @model_validator(mode="after")
    def check_options(self) -> Self:
        if (self.type == "attribute") != (self.attribute is not None):
            raise ValueError("attribute extraction requires an attribute")
        if (self.type == "regex") != (self.pattern is not None):
            raise ValueError("regex extraction requires a pattern")
        return self


class RecipeProposal(Contract):
    baseSelector: Selector
    fields: list[RecipeField] = Field(
        min_length=4,
        max_length=12,
        description=(
            f"Required names: {', '.join(REQUIRED_RECIPE_FIELDS)}. "
            "Include at least one of chip_time_s or gun_time_s. Names must be unique."
        ),
    )

    @model_validator(mode="after")
    def check_fields(self) -> Self:
        names = {field.name for field in self.fields}
        missing = set(REQUIRED_RECIPE_FIELDS) - names
        if missing:
            raise ValueError(f"missing required fields: {', '.join(sorted(missing))}")
        if len(names) != len(self.fields):
            raise ValueError("field names must be unique")
        if not names & {"chip_time_s", "gun_time_s"}:
            raise ValueError("at least one official time field is required")
        return self


class ResultRow(Contract):
    full_name_raw: str = Field(min_length=2, max_length=250)
    gender: Literal["M", "F"]
    status: Status = "FIN"
    bib: str | None = Field(default=None, max_length=80)
    place_abs: PositiveId | None = None
    place_gender: PositiveId | None = None
    chip_time_s: Time | None = None
    gun_time_s: Time | None = None
    club_raw: str | None = Field(default=None, max_length=250)
    city: str | None = Field(default=None, max_length=250)
    age_group: str | None = Field(default=None, max_length=80)
    birth_year: int | None = Field(default=None, ge=1900, le=2100)


class ProtocolSample(Contract):
    raw_id: PositiveId
    place_by: PlaceBy
    total: PositiveId | None = None


class GoldenInput(ProtocolSample):
    expected: list[ResultRow] = Field(min_length=1, max_length=30000)


class StartRepair(Contract):
    source_id: PositiveId
    samples: list[ProtocolSample] = Field(min_length=1, max_length=3)
    issue_id: PositiveId | None = None

    @model_validator(mode="after")
    def unique_samples(self) -> Self:
        if len({sample.raw_id for sample in self.samples}) != len(self.samples):
            raise ValueError("sample raw IDs must be distinct")
        return self


class ReviewDecision(Contract):
    action: Literal["approve", "edit", "reject"]
    candidate: RecipeProposal | None = None
    comment: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def check_candidate(self) -> Self:
        if (self.action == "edit") != (self.candidate is not None):
            raise ValueError("only an edit requires a replacement recipe")
        return self
