#!/bin/bash
set -e

# Run the Python removal script
cd "$(dirname "$0")"
echo "Running remove.py to remove DIDs from datasets..."
python remove.py
echo "Removal process completed successfully."

# Upload to Hugging Face
echo "Uploading to Hugging Face..."
# Skip login since assumed authenticated, otherwise you should run the following line
# huggingface-cli login
cd ~/cleaned
huggingface-cli upload-large-folder ComplexDataLab/bluesky-persona . --repo-type=dataset --num-workers=16

echo "Uploaded the new data release."