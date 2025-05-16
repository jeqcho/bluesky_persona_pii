# This script removes a given user DID from the released dataset

import os
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any
from dotenv import load_dotenv
from tqdm import tqdm

# Load environment variables from .env file
dotenv_path: Path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path)

SECRET: str | None = os.environ.get("HASH_SECRET")
if not SECRET:
    raise ValueError(
        "HASH_SECRET environment variable not found. Make sure to create .env file with HASH_SECRET."
    )

HOME_DIR: Path = Path.home()
CLEANED_DIR: Path = HOME_DIR / "cleaned"
DID_LIST_FILE: Path = Path(__file__).parent / "did_removal_list.txt"

ThreadMessage = Dict[str, Any]
Thread = List[ThreadMessage]


def recompute_hashed_user_id(target_did: str, thread: Thread) -> str:
    # Remove user_id from each message for hashing
    dids: List[str] = []
    thread_no_uid: List[Dict[str, Any]] = []
    for message in thread:
        msg: Dict[str, Any] = dict(message)
        dids.append(msg.pop("user_id"))
        thread_no_uid.append(msg)
    dump: str = json.dumps(thread_no_uid, sort_keys=True)
    hashed_id: str = hashlib.sha256(f"{target_did}{dump}{SECRET}".encode()).hexdigest()
    return hashed_id


def remove_user_from_cleaned(target_did: str) -> None:
    total_removed: int = 0
    # Get list of files first to show accurate total
    cluster_files = list(CLEANED_DIR.glob("processed_*_clusters/cluster_*.jsonl"))
    
    # Main progress bar for files
    for cluster_file in tqdm(cluster_files, desc="Processing cluster files", unit="file"):
        temp_file: Path = cluster_file.with_suffix(".tmp")
        removed_count: int = 0
        
        # Count lines in file for nested progress bar
        file_line_count = sum(1 for _ in open(cluster_file, 'r'))
        
        with open(cluster_file, "r") as fin, open(temp_file, "w") as fout:
            # Nested progress bar for lines in current file
            for line in tqdm(fin, total=file_line_count, desc=f"File: {cluster_file.name}", 
                             leave=False, unit="thread"):
                data: Dict[str, Any] = json.loads(line)
                thread: Thread = data["thread"]
                # Recompute the hash for the target DID for this thread
                hashed_id: str = recompute_hashed_user_id(target_did, thread)
                # If any message's user_id matches, skip this thread
                found: bool = any(msg["user_id"] == hashed_id for msg in thread)
                if found:
                    removed_count += 1
                    continue
                fout.write(line)
                
        # Replace original file
        if removed_count > 0:
            temp_file.replace(cluster_file)
            # Update total counter
            total_removed += removed_count
            tqdm.write(f"Removed {removed_count} threads from {cluster_file.name}")
        else:
            # If no threads were removed, delete the temp file
            temp_file.unlink(missing_ok=True)
            tqdm.write(f"No threads to remove from {cluster_file.name}")
    
    print(f"\nRemoval complete: {total_removed} threads removed across all files")


def read_dids_from_file() -> List[str]:
    """Read DIDs from the removal list file."""
    if not DID_LIST_FILE.exists():
        raise FileNotFoundError(f"DID list file not found at {DID_LIST_FILE}")
    
    with open(DID_LIST_FILE, 'r') as f:
        dids = [line.strip() for line in f if line.strip()]
    
    if not dids:
        raise ValueError(f"No DIDs found in {DID_LIST_FILE}")
    
    return dids


def main() -> None:
    try:
        dids = read_dids_from_file()
        print(f"Found {len(dids)} DIDs to remove")
        
        for did in dids:
            print(f"\nProcessing DID: {did}")
            remove_user_from_cleaned(did)
        
        print("\nAll DIDs processed successfully!")
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        print(f"Please create {DID_LIST_FILE} with one DID per line")
        exit(1)


if __name__ == "__main__":
    main()
