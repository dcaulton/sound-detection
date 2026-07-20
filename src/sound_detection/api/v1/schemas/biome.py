from pydantic import BaseModel


class BiomeSummaryUpdate(BaseModel):
    grok_narrative: str | None = None
    # optional: allow updating human_narrative too if you want
    human_narrative: str | None = None
