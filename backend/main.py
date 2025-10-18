# Import required libraries
from datetime import datetime
from functools import cache
import os
from utils import call_crossref, extract_doi_from_text

import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mixedbread import Mixedbread
from pymilvus import MilvusClient
from schemas import Paper, TextRequest
import pydantic_core
import requests
################################################################################
# Configuration

app = FastAPI()

# TODO: MAKE IT SECURE
# Allow frontend to talk to backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or ["http://localhost:5500"] if serving static files
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get current year
current_year = str(datetime.now().year)

# Import secrets
load_dotenv()

# Connect to Zilliz via Milvus client
ENDPOINT = os.getenv("ENDPOINT")
TOKEN = os.getenv("TOKEN")
milvus_client = MilvusClient(uri=ENDPOINT, token=TOKEN)

# Setup search parameters
COLLECTION_NAME = os.getenv("COLLECTION_NAME")
SEARCH_LIMIT = int(os.getenv("SEARCH_LIMIT"))

# Setup mxbai client
mxbai_api_key = os.getenv("MXBAI_API_KEY")
mxbai = Mixedbread(api_key=mxbai_api_key)

################################################################################

# Function to search paper by DOI
def fetch_paper_by_doi(doi: str) -> Paper:
    
    # Search for the paper using the Crossref API
    paper_json = call_crossref(doi).get('message')

    # Create the result model (create an instance instead of assigning to the class)
    paper = Paper(
            doi=paper_json.get('DOI'),
            abstract=paper_json.get('abstract')
        )
    
    return paper


################################################################################


# Function to embed text using https://huggingface.co/mixedbread-ai/mxbai-embed-large-v1
@cache
def embed_text(text: str) -> bytes:
    # Call the MixedBread.ai API to generate the embedding
    result = mxbai.embed(
        model="mixedbread-ai/mxbai-embed-large-v1",
        input=text,
        normalized=True,
        encoding_format="ubinary",
        dimensions=1024,
    )

    # Extract the embedding from the response
    embedding = result.data[0].embedding

    # Convert the embedding to a numpy array of uint8 encoding and then to bytes
    vector_bytes = np.array(embedding, dtype=np.uint8).tobytes()

    return vector_bytes


################################################################################
# Single vector search
def search_by_vector(vector: bytes, filter: str = "") -> list[dict]:
    # Request zilliz for the vector search
    result = milvus_client.search(
        collection_name=COLLECTION_NAME,  # Collection to search in
        data=[vector],  # Vector to search for
        limit=SEARCH_LIMIT,  # Max. number of search results to return
        output_fields=[
            "doi",
            "title",
            "abstract",
            "authors",
            "category",
            "month",
            "year",
            "url",
        ],  # Output fields to return
        filter=filter,  # Filter to apply to the search
    )

    # returns a list of dictionaries with id and distance as keys
    return result[0]


################################################################################


# Search the collection using text
@app.post("/search_by_text")
def search_by_text(request: TextRequest) -> list[dict]:
    # Extract objects?
    text = request.text
    filter = request.filter

    # Embed the text
    embedding = embed_text(text)

    # Send vector for search
    results = search_by_vector(vector=embedding, filter=filter)

    return results


################################################################################


# Search by known id
# The onus is on the user to make sure the id exists
# Use with similar results feature
@app.get("/search_by_known_id")
def search_by_known_id(doi: str, filter: str = "") -> list[dict]:
    # Get the id which is already in database
    id_in_db = milvus_client.get(collection_name=COLLECTION_NAME, ids=[doi])

    # Get the bytes of a binary vector
    embedding = id_in_db[0]["vector"][0]

    # Run similarity search
    results = search_by_vector(vector=embedding, filter=filter)

    return results


################################################################################


# Search by id. this will first hit the db to get vector
# else use abstract from site to arxiv
@app.get("/search_by_id")
def search_by_id(doi: str, filter: str = "") -> list[dict]:
    # Search if id is already in database
    id_in_db = milvus_client.get(collection_name=COLLECTION_NAME, ids=[doi])

    # If the id is already in database
    if bool(id_in_db):
        # Get the bytes of a binary vector
        embedding = id_in_db[0]["vector"][0]

    # If the id is not already in database
    else:
        try:
            # Search arxiv for paper details
            paper = fetch_paper_by_doi(doi)
        
        # Return error for missing information in crossref
        # Abstract key was missing in response, and returned None
        except pydantic_core._pydantic_core.ValidationError:
            raise HTTPException(status_code=404, detail="Abstract not found in Crossref")
            
        # Crossref does not have the doi, and hence requests raises for status
        except requests.exceptions.HTTPError:
            raise HTTPException(status_code=404, detail="DOI not found in Crossref")
            
        # Embed abstract
        embedding = embed_text(paper.abstract)

    results = search_by_vector(vector=embedding, filter=filter)

    return results


################################################################################


# Simulate a search point which automatically figures out if the search is using
# id or text
@app.post("/search")
def search(request: TextRequest) -> list[dict]:
    text = request.text
    filter = request.filter

    id_in_text = extract_doi_from_text(text)

    if id_in_text:
        results = search_by_id(id_in_text, filter)

    else:
        results = search_by_text(request)

    return results
