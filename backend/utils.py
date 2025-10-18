import requests
import backoff
import json
import re
from schemas import Paper
################################################################################

# Define doi regex pattern
# From https://www.crossref.org/blog/dois-and-matching-regular-expressions/
# Removed start and end anchors since we are expecting doi to be anywhere
doi_regex_pattern = re.compile(r"10.\d{4,9}\/[-._;()/:A-Z0-9]+", re.IGNORECASE)



# Function to doi from input text
def extract_doi_from_text(text: str) -> str | None:

    # Search for matches
    match = doi_regex_pattern.search(text)

    # Return the match if found, otherwise return None
    return match.group(0) if match else None


################################################################################
# Function to extract doi from the url
def extract_doi_from_url(doi_url: str) -> str:
    prefix = doi_url.split("/")[-2]
    suffix = doi_url.split("/")[-1]

    doi = f"{prefix}/{suffix}"
    
    return doi

################################################################################
CROSSREF_BASE_URL = "https://api.crossref.org/works"

@backoff.on_exception(
    wait_gen=backoff.expo,
    exception=(requests.exceptions.RequestException, RuntimeError),
    jitter=backoff.full_jitter,
    max_tries=3
)
def call_crossref(doi: str) -> dict:
    crossref_api_url = f"{CROSSREF_BASE_URL}/{doi}"
    
    # try:

    response = requests.get(crossref_api_url)
    response.raise_for_status()
        
    response_json = response.json()
    return response_json
        
    # except requests.exceptions.HTTPError:
        


def fetch_paper_by_doi(doi: str) -> Paper:
    
    # Search for the paper using the Crossref API
    paper_json =call_crossref(doi).get('message')

    # Create the result model (create an instance instead of assigning to the class)
    paper = Paper(
            doi=paper_json.get('DOI'),
            title=paper_json.get('title')[0],
            authors=paper_json.get('author'),
            abstract=paper_json.get('abstract'),
            url=paper_json.get('URL'),
            month=paper_json.get('issued').get('date-parts')[0][1],
            year=paper_json.get('issued').get('date-parts')[0][2],
            categories=paper_json.get('group-title').lower(),
        )
    
    return paper