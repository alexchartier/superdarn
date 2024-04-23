#######################
# Retrieve deposition IDs
#######################
import requests

# Replace with your Zenodo access token
access_token = 'your_zenodo_access_token'

# Get the list of your deposits
response = requests.get(
    'https://zenodo.org/api/deposit/depositions',
    headers={
        'Authorization': f'Bearer {access_token}'
    }
)

# Check the status code to see if the request was successful
if response.status_code == 200:
    # Get the list of deposits from the response
    deposits = response.json()

    # Find the deposition with the desired title
    desired_title = "My Record"
    for deposit in deposits:
        if deposit['metadata']['title'] == desired_title:
            deposition_id = deposit['id']
            print(f"The deposition ID for '{
                  desired_title}' is {deposition_id}")
            break
else:
    print("An error occurred:", response.text)


#######################
# Use deposition IDs to upload new versions
#######################

# Replace with your Zenodo access token
access_token = 'your_zenodo_access_token'

# Replace with the unique identifier of your deposit
deposition_id = 12345

# Update the metadata for the new version
metadata = {
    "metadata": {
        "title": "My Updated Record",
        "upload_type": "publication",
        "publication_type": "article",
        "creators": [
            {
                "name": "Doe, John",
                "affiliation": "My University"
            }
        ],
        "description": "This is an updated version of my record."
    }
}

# Update the deposit with the new version
response = requests.put(
    f'https://zenodo.org/api/deposit/depositions/{deposition_id}',
    headers={
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    },
    json=metadata
)

# Publish the new version
response = requests.post(
    f'https://zenodo.org/api/deposit/depositions/{
        deposition_id}/actions/publish',
    headers={
        'Authorization': f'Bearer {access_token}'
    }
)

# Check the status code to see if the request was successful
if response.status_code == 200:
    print("The new version was uploaded and published successfully!")
else:
    print("An error occurred:", response.text)
