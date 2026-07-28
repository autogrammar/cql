"""Request models shared by the CQL HTTP route groups."""

from pydantic import BaseModel, Field


class TextIn(BaseModel):
    text: str = Field("", description="DSL source text.")


class ValueIn(BaseModel):
    value: str = Field("", description="Raw value to quote.")


class HighlightIn(TextIn):
    mode: str = Field(
        "html",
        pattern="^(html|tokens)$",
        description="Only 'html' is implemented; 'tokens' returns 501 until the full port lands.",
    )


class AstIn(BaseModel):
    ast: dict = Field(..., description="DSL AST to serialize.")


class ScenarioBuildIn(BaseModel):
    source: str = Field("test", description="Source type: 'test' or 'generic'.")
    data: dict = Field(..., description="Scenario data to build DSL from.")


class QuotedTokenIn(BaseModel):
    token: str = Field("", description="Single quoted literal to parse.")


class AstOnlyIn(BaseModel):
    ast: object = Field(..., description="AST value to validate against the DSL JSON Schema.")


class XmlIn(BaseModel):
    xml: str = Field("", description="XML document to parse.")


class XmlMigrateIn(XmlIn):
    nameHint: str | None = Field(
        None,
        description="Optional scenario name hint when XML omits one.",
    )


class ExecIn(BaseModel):
    text: str = Field("", description="DSL source text to execute.")
    context: dict | None = Field(
        None,
        description="Optional execution context (getParamValue, runTask).",
    )
