# PII Removal

I did this using c7i.4xlarge EC2 instance (c8g would be cheaper and faster but they ran out).

Remember to make sure that each side has the public SSH keys of the other in `/.ssh/authorized_keys`.

First I copied over the user_id to cluster mappings by running this on compute canada. Replace `EC2_DNS` with that of your EC2 instance.

```bash
# specify your EC2 DNS
EC2_DNS="??"

# include the user in one var:
REMOTE="ubuntu@${EC2_DNS}"

# Start SSH agent if not already running
eval $(ssh-agent)

# Create a master connection first
ssh -o "ControlMaster=yes" \
    -o "ControlPath=~/.ssh/cm-%r@%h:%p" \
    -o "ControlPersist=5m" \
    ${REMOTE} "echo 'Connection established'"
```

Now run this
```bash
# Now use the connection for each file transfer
for dir in processed_*; do
  # Create directory if it doesn't exist
  ssh -o "ControlPath=~/.ssh/cm-%r@%h:%p" ${REMOTE} "mkdir -p ~/${dir}"
  
  # Copy the file using the existing connection
  scp -o "ControlPath=~/.ssh/cm-%r@%h:%p" "$dir/user_clusters.json" "${REMOTE}:~/${dir}/"
done

# Close the master connection when done
ssh -O exit -o "ControlPath=~/.ssh/cm-%r@%h:%p" ${REMOTE}
```

We need at least one full partition so I also copied over the 25 clusters.
```bash
scp -r processed_25_clusters "${REMOTE}:~/"
```

Then on the EC2 instance, make sure the virtual environment is activated and installed.

```bash
cd ~/bluesky_persona_pii
source .venv/bin/activate
pip install -r requirements.txt
```

I first ran `merge_df.py` to merge all the 25 clusters into one cluster and break the chains into messages while keeping track of the IDs. This outputs `~/all_messages/merged_messages.parquet`.

```bash
cd ~/bluesky_persona_pii/src
python merge_df.py
```

I then ran `sample.py` to get some smaller files in `all_messages/` to work with. This is not required if you are following along, and not doing development. This is simply for debugging.

```bash
python sample.py
```

Then run the pii removal in the background, will take about 2 hours. If you want to test instead, you can use a smaller file say `subsample_10k.parquet` by editing `conf.json`. This saves to `full_data/pii_dataset_tags.parquet`.

```bash
mkdir logs
nohup python pii_temp.py > logs/pii.log 2>&1 &
```

Then run `rebuild_chains.py` to get it back into a blob at `full_data/single_cluster.jsonl`, takes about 8 minutes

```bash
python rebuild_chains.py
```

Next we will rebuild the clusters, and remove the `user_id`. We first need to generate a secret key to be used for hashing.

```bash
echo HASH_SECRET=$(openssl rand -base64 32) > .env
```

Finally run `rebuild_clusters.py` to rebuild it into `cleaned/`. This will use the secret above.

```bash
python rebuild_clusters.py
```

## Upload to Compute Canada
Then scp it back to compute canada. Run this on EC2 as usual.

```bash
cd ~/
# Create a master connection first
ssh -o "ControlMaster=yes" \
    -o "ControlPath=~/.ssh/cm-%r@%h:%p" \
    -o "ControlPersist=5m" \
    jchooi@narval.alliancecan.ca "echo 'Connection established'"
```

Then copy it
```bash
ssh -o "ControlPath=~/.ssh/cm-%r@%h:%p" jchooi@narval.alliancecan.ca "mkdir -p ~/projects/ctb-liyue/s4yor1/pii_removed/"
scp -o "ControlPath=~/.ssh/cm-%r@%h:%p" -r cleaned/processed_* jchooi@narval.alliancecan.ca:~/projects/ctb-liyue/s4yor1/pii_removed/
```

If something happens that causes some file to drop, you can just ssh each
```
scp -o "ControlPath=~/.ssh/cm-%r@%h:%p" -r cleaned/processed_25_clusters jchooi@narval.alliancecan.ca:~/projects/ctb-liyue/s4yor1/pii_removed/
```

## Upload to Huggingface

```bash
# Install the Hugging Face CLI
pip install -U "huggingface_hub[cli]"

# Login with your Hugging Face credentials
huggingface-cli login
```

If you are making updates, you might have to pull first

```bash
huggingface-cli download ComplexDataLab/BluePrint --repo-type dataset
```

Then copy over whatever that is useful, for example

```bash
# EXAMPLE
cp ~/.cache/huggingface/hub/datasets--ComplexDataLab--BluePrint/snapshots/34ff669510ee4db3a26952076b711a6afa75970b/{README.md,croissant.json} ~/cleaned/
```

Then upload the rest.

```bash
cd ~/cleaned

# Push your dataset files
huggingface-cli upload-large-folder ComplexDataLab/bluesky-persona . --repo-type=dataset --num-workers=16
```

## Notes

Here are the entities that are removed (and their corresponding token)
```
<CREDIT_CARD>
<CRYPTO>
<EMAIL_ADDRESS>
<IP_ADDRESS>
<PHONE_NUMBER>
<URL>
```

These are specified in `conf.json`.

Bluesky username handles are also removed, which is anything of the form `@username.bsky.social` or `@<URL>`.

Unix epoch is removed and reassigned from 1 to 52M+ as integers. Ties are broken arbitrarily (deterministically based on how the sorting algo on unix epoch worked). Each message will have exactly one integer. Call this `relative_integer_time`

`did` for each message is removed, and the `did` is replaced with the SHA256 hash of the `relative_integer_time` of their first message.

## Data Removal Request

If a data removal request is received:

1. Add the user's DID to `src/data_removal/did_removal_list.txt` (one DID per line)
2. Run the removal script:

```bash
cd ~/bluesky_persona_pii/src/data_removal
chmod +x ./remove.sh
./remove.sh
```

The script will:
- Remove the user's data from all dataset files
- Automatically upload the updated dataset to Hugging Face