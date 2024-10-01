# Import required libraries
import gradio as gr
from pymilvus import MilvusClient
import numpy as np
import requests
from mixedbread_ai.client import MixedbreadAI
from dotenv import dotenv_values
import re
from functools import cache
import pandas as pd

################################################################################
# Configuration

# Define Milvus client
milvus_client = MilvusClient("http://localhost:19530")

# Import secrets
config = dotenv_values(".env")

# Setup mxbai
mxbai_api_key = config["MXBAI_API_KEY"]
mxbai = MixedbreadAI(api_key=mxbai_api_key)

################################################################################

# Function to search bioRiv by DOI
@cache
def fetch_biorxiv_by_id(doi):

    # Define the base URL for the bioRxiv API
    base_url = "https://api.biorxiv.org/details/biorxiv/"

    # Construct the full URL for the API request
    url = f"{base_url}{doi}"

    # Send the API request
    response = requests.get(url)

    # Check if the request was successful
    if response.status_code == 200:
        # Parse the JSON response
        data = response.json()
        # Extract the abstract from the response data
        # abstract = data["abstract"]
        return {
            "Title": data['collection'][0]['title'],
            "Authors": data['collection'][0]['authors'],
            "Abstract": data['collection'][0]['abstract'],
            "URL": f"https://doi.org/{doi}"
        }
    else:
        # Print an error message if the request was not successful
        print(f"Error: {response.status_code}")
        return None

################################################################################
# Function to embed text
@cache
def embed(text):

    res = mxbai.embeddings(
    model='mixedbread-ai/mxbai-embed-large-v1',
    input=text,
    normalized=True,
    encoding_format='float',
    truncation_strategy='end'
    )

    vector = np.array(res.data[0].embedding)

    return vector

################################################################################
# Single vector search

def search(vector, limit):

    result = milvus_client.search(
        collection_name="biorxiv_abstracts", # Replace with the actual name of your collection
        # Replace with your query vector
        data=[vector],
        limit=limit, # Max. number of search results to return
        search_params={"metric_type": "COSINE"} # Search parameters
    )

    # returns a list of dictionaries with id and distance as keys
    return result[0]

################################################################################
# Function to 

def fetch_all_details(search_results):

    all_details = []

    for search_result in search_results:

        paper_details = fetch_biorxiv_by_id(search_result['id'])

        paper_details['Similarity Score'] = np.round(search_result['distance']*100, 2)

        all_details.append(paper_details)

    return all_details

################################################################################
@cache
def make_clickable(val):
        # Regex to detect URLs in the value
        if re.match(r'^https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+', val):
            return f"[{val}]({val})"
        return val

################################################################################

# Function to convert list of dictionaries to a styled HTML table

def parse_output(data):
    
    df = pd.DataFrame(data)

    df['URL'] = df['URL'].apply(make_clickable)

    return df

################################################################################

# Function to handle the UI logic
@cache
def predict(input_type, input_text, limit):

    # When input is bioRxiv id
    if input_type == "BioRxiv DOI":

        # Search if id is already in database
        id_in_db = milvus_client.get(collection_name="biorxiv_abstracts",ids=[input_text])

        # If the id is already in database
        if bool(id_in_db):

            # Get the vector
            abstract_vector = id_in_db[0]['vector']

        else:

            # Search bioRxiv for paper details
            biorxiv_json = fetch_biorxiv_by_id(input_text)

            # Embed abstract
            abstract_vector = embed(biorxiv_json['Abstract'])

        # Search database
        search_results = search(abstract_vector, limit)

        # Gather details about the found papers
        all_details = fetch_all_details(search_results)
        

        df = parse_output(all_details)

        return df
    
    elif input_type == "Abstract or Description":

        abstract_vector = embed(input_text)

        search_results = search(abstract_vector, limit)

        all_details = fetch_all_details(search_results)
        
        df = parse_output(all_details)

        return df

    else:
        return "Please provide either an BioRxiv DOI or an abstract."
            

contact_text = """
# Contact Information

👤  [Mitanshu Sukhwani](https://www.linkedin.com/in/mitanshusukhwani/)

✉️  mitanshu.sukhwani@gmail.com

🐙  [mitanshu7](https://github.com/mitanshu7)
"""

examples = [
    ["BioRxiv DOI", "10.1101/2024.02.22.581503"],
    ["Abstract or Description", "Game theory applications in Biology"],
]

################################################################################
# Create the Gradio interface
with gr.Blocks(theme=gr.themes.Soft()) as demo:

    # Title and description
    gr.Markdown("# PaperMatchBio: Discover Related Research Papers")
    gr.Markdown("## Enter either a BioRxiv DOI or paste an abstract to explore papers based on semantic similarity.")
    gr.Markdown("### _BioRiv Database last updated: September 2024_")
    
    # Input Section
    with gr.Row():
        input_type = gr.Dropdown(
            choices=["BioRxiv DOI", "Abstract or Description"],
            label="Input Type",
            value="BioRxiv DOI",
            interactive=True,
        )
        id_or_text_input = gr.Textbox(
            label="Enter BioRiv DOI or Abstract", 
            placeholder="e.g., 10.1101/19013474 or an abstract...",
        )
    
    # Example inputs
    gr.Examples(
        examples=examples, 
        inputs=[input_type, id_or_text_input],
        label="Example Queries"
    )

    # Slider for results count
    slider_input = gr.Slider(
        minimum=1, maximum=25, value=5, step=1, 
        label="Number of Similar Papers"
    )

    # Submission Button
    submit_btn = gr.Button("Find Papers")
    
    # Output section
    output = gr.DataFrame(
        wrap=True, datatype=["str", "str", "str", "markdown", "number"], 
        label="Related Papers", 
        show_label=True,
        headers=["Title", "Authors", "Abstract", "URL", "Similarity Score"]
    )

    # Attribution
    gr.Markdown(contact_text)
    gr.Markdown("_Thanks to [BioRiv](https://biorxiv.org) for their open access interoperability._")

    # Link button click to the prediction function
    submit_btn.click(predict, [input_type, id_or_text_input, slider_input], output)


################################################################################

if __name__ == "__main__":
    demo.launch(server_port=7862)
