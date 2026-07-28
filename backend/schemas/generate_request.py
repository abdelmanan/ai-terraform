from pydantic import BaseModel


class GenerateRequest(BaseModel):

    cloud: str

    project_name: str

    region: str

    template: str = "landing-zone"