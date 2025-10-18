from pydantic import BaseModel, HttpUrl, field_validator, Field
import re
from datetime import datetime


# Create a request model
class TextRequest(BaseModel):
    text: str
    filter: str = ""


arxiv_url_regex = re.compile(r".+arxiv\.org.+")
current_year = datetime.now().year

# Response model for arxiv papers
class Paper(BaseModel):
    doi: str = Field(min_length=1)
    abstract: str = Field(min_length=1)


