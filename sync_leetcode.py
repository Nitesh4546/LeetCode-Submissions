#!/usr/bin/env python3
import os
import sys
import json
import time
import re
import argparse
import requests

# Default configuration values
DEFAULT_DOMAIN = "leetcode.com"
DEFAULT_DELAY = 1.0
DEFAULT_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

# GraphQL Queries
SUBMISSION_LIST_QUERY = """
query submissionList($offset: Int!, $limit: Int!, $lastKey: String) {
  submissionList(offset: $offset, limit: $limit, lastKey: $lastKey) {
    lastKey
    hasNext
    submissions {
      id
      lang
      statusDisplay
      title
      titleSlug
      timestamp
    }
  }
}
"""

SUBMISSION_DETAILS_QUERY = """
query submissionDetails($submissionId: Int!) {
  submissionDetails(submissionId: $submissionId) {
    id
    code
    runtime
    memory
    statusDisplay
    timestamp
    lang {
      name
      verboseName
    }
    question {
      titleSlug
      title
      translatedTitle
      questionId
    }
  }
}
"""

# Language to extension mapping
LANG_TO_EXT = {
    'cpp': 'cpp',
    'java': 'java',
    'python': 'py',
    'python3': 'py',
    'javascript': 'js',
    'typescript': 'ts',
    'csharp': 'cs',
    'golang': 'go',
    'rust': 'rs',
    'ruby': 'rb',
    'swift': 'swift',
    'php': 'php',
    'kotlin': 'kt',
    'dart': 'dart',
    'scala': 'scala',
    'c': 'c',
    'mysql': 'sql',
    'mssql': 'sql',
    'oraclesql': 'sql',
    'postgresql': 'sql',
    'bash': 'sh',
}

def parse_cookies(cookie_string):
    cookies = {}
    for item in cookie_string.split(';'):
        item = item.strip()
        if not item:
            continue
        if '=' in item:
            k, v = item.split('=', 1)
            cookies[k] = v
    return cookies

def sanitize_name(name):
    # Replace characters that are invalid in file/directory names: \ / : * ? " < > |
    sanitized = re.sub(r'[\\/*?:"<>|]', '_', name)
    # Strip leading/trailing whitespaces or dots
    sanitized = sanitized.strip(' .')
    # Collapse multiple underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    return sanitized

def has_local_solution(solved_dir, title, lang):
    if not os.path.exists(solved_dir):
        return False
    safe_title = sanitize_name(title)
    ext = LANG_TO_EXT.get(lang.lower(), lang.lower())
    for item in os.listdir(solved_dir):
        if item.endswith(f".{safe_title}"):
            file_path = os.path.join(solved_dir, item, f"solution.{ext}")
            if os.path.exists(file_path):
                return True
    return False

def load_config(config_path):
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load config from {config_path}: {e}")
    
    # Environment variables override config file
    if os.environ.get('LEETCODE_COOKIE'):
        config['cookie'] = os.environ.get('LEETCODE_COOKIE')
    if os.environ.get('LEETCODE_SESSION'):
        # If user provides session only, try to parse or set
        session = os.environ.get('LEETCODE_SESSION')
        csrf = os.environ.get('LEETCODE_CSRF_TOKEN', '')
        config['cookie'] = f"LEETCODE_SESSION={session}; csrftoken={csrf};"
    
    return config

def save_config(config_path, config):
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
        print(f"Saved configuration to {config_path}")
    except Exception as e:
        print(f"Error saving config to {config_path}: {e}")

def load_state(state_path):
    if os.path.exists(state_path):
        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load state from {state_path}: {e}")
    return {"last_synced_timestamp": 0}

def save_state(state_path, state):
    try:
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        print(f"Error saving state to {state_path}: {e}")

def query_graphql(query, variables, headers, domain):
    url = f"https://{domain}/graphql"
    max_retries = 3
    backoff = 1.5
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                url,
                json={"query": query, "variables": variables},
                headers=headers,
                timeout=30
            )
            if resp.status_code != 200:
                if resp.status_code == 403:
                    raise Exception("GraphQL request failed with HTTP 403 (Forbidden). Your cookies might be invalid or expired.")
                raise Exception(f"GraphQL request failed with HTTP {resp.status_code}: {resp.text}")
            
            data = resp.json()
            if 'errors' in data:
                raise Exception(f"GraphQL returned errors: {data['errors']}")
            return data.get('data', {})
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            print(f"\n[Warning] GraphQL request failed (attempt {attempt + 1}/{max_retries}). Retrying in {backoff}s... (Error: {e})")
            time.sleep(backoff)
            backoff *= 2

def get_terminal_width():
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80

def print_progress_bar(iteration, total, prefix='', suffix='', decimals=1, length=30, fill='█'):
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '░' * (length - filled_length)
    
    static_part = f"{prefix} |{bar}| {percent}% "
    width = get_terminal_width()
    
    # Leave room for carriage return and potential terminal quirks
    max_suffix_len = width - len(static_part) - 4
    if max_suffix_len > 0 and len(suffix) > max_suffix_len:
        suffix = suffix[:max_suffix_len - 3] + "..."
        
    sys.stdout.write(f'\r\033[K{static_part}{suffix}')
    sys.stdout.flush()
    if iteration == total:
        sys.stdout.write('\n')
        sys.stdout.flush()

def main():
    parser = argparse.ArgumentParser(description="Sync solved LeetCode solutions to local files.")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    parser.add_argument("--state", default="state.json", help="Path to state file")
    parser.add_argument("--reset", action="store_true", help="Reset sync state and download everything from scratch")
    parser.add_argument("--delay", type=float, help="Delay between downloading submissions (in seconds)")
    args = parser.parse_args()

    # If config file doesn't exist, create it with placeholders
    if not os.path.exists(args.config):
        default_config = {
            "cookie": "LEETCODE_SESSION=your_leetcode_session_here; csrftoken=your_csrftoken_here;",
            "domain": "leetcode.com",
            "rate_limit_delay": 1.0
        }
        save_config(args.config, default_config)
        print(f"\nCreated configuration template at '{args.config}'.")
        print("Please edit this file and replace the placeholder values with your actual LeetCode cookies.")
        print("See README.md for instructions on how to retrieve your cookies.")
        sys.exit(1)

    # Load configuration
    config = load_config(args.config)
    
    # Check if the cookie is set and is not a placeholder
    cookie_val = config.get('cookie', '')
    if not cookie_val or "your_leetcode_session_here" in cookie_val or "your_csrftoken_here" in cookie_val:
        print(f"\nError: Please configure your actual LeetCode cookie in '{args.config}'.")
        print("It currently contains placeholder values or is empty.")
        print("See README.md for details on how to get your cookies.")
        sys.exit(1)

    cookie_str = config['cookie']
    domain = config.get('domain', DEFAULT_DOMAIN)
    delay = args.delay if args.delay is not None else config.get('rate_limit_delay', DEFAULT_DELAY)

    # Parse cookies to extract csrftoken
    cookies = parse_cookies(cookie_str)
    csrf_token = cookies.get('csrftoken')
    if not csrf_token:
        # Try finding x-csrftoken or csrf token from session
        print("Warning: 'csrftoken' cookie not found in the provided cookie string.")
        print("Proceeding, but requests might fail if CSRF validation is strict.")

    # Setup headers
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Content-Type": "application/json",
        "Referer": f"https://{domain}",
        "Cookie": cookie_str
    }
    if csrf_token:
        headers["x-csrftoken"] = csrf_token

    # Load or reset state
    if args.reset:
        state = {"last_synced_timestamp": 0}
        print("Resetting sync state. Script will sync all solved questions.")
    else:
        state = load_state(args.state)

    last_synced_ts = state.get("last_synced_timestamp", 0)
    print(f"Syncing submissions solved after: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_synced_ts)) if last_synced_ts > 0 else 'Beginning of time'}")

    # Fetch submissions paginated
    offset = 0
    limit = 20
    submissions_to_process = []
    has_next = True
    
    print("Fetching submission history...")
    while has_next:
        variables = {
            "offset": offset,
            "limit": limit
        }
        try:
            data = query_graphql(SUBMISSION_LIST_QUERY, variables, headers, domain)
        except Exception as e:
            print(f"Error fetching submissions list: {e}")
            sys.exit(1)

        sub_list_data = data.get('submissionList')
        if not sub_list_data:
            print("Error: Failed to retrieve submission list. Check if your cookies are valid.")
            sys.exit(1)

        submissions = sub_list_data.get('submissions', [])
        if not submissions:
            break

        stop_fetching = False
        for sub in submissions:
            ts = int(sub['timestamp'])
            if ts <= last_synced_ts:
                stop_fetching = True
                break
            submissions_to_process.append(sub)

        if stop_fetching:
            print("Reached previously synchronized submissions.")
            break

        has_next = sub_list_data.get('hasNext', False)
        offset += limit
        print(f"Retrieved {len(submissions_to_process)} new submissions so far...")
        time.sleep(0.5)

    if not submissions_to_process:
        print("No new submissions found. Everything is up to date!")
        sys.exit(0)

    # Filter out duplicate accepted submissions (keep only the newest accepted one for each titleSlug and language)
    seen_accepted = set()
    deduped_count = 0
    for sub in submissions_to_process:
        if sub['statusDisplay'] == "Accepted":
            key = (sub['titleSlug'], sub['lang'].lower())
            if key in seen_accepted:
                sub['statusDisplay'] = "Duplicate"
                deduped_count += 1
            else:
                seen_accepted.add(key)

    if deduped_count > 0:
        print(f"Deduplicated {deduped_count} older accepted submissions (will skip downloading them).")

    # Reverse list to process chronologically (oldest first)
    submissions_to_process.reverse()
    print(f"\nProcessing {len(submissions_to_process)} submissions in chronological order...")

    # Create Solved directory if it doesn't exist
    os.makedirs("Solved", exist_ok=True)

    success_count = 0
    skip_count = 0
    
    for i, sub in enumerate(submissions_to_process, 1):
        ts = int(sub['timestamp'])
        sub_id = int(sub['id'])
        title = sub['title']
        status = sub['statusDisplay']
        lang = sub['lang']

        # Clear line and show current item
        status_suffix = f"({i}/{len(submissions_to_process)}) {title} [{status}]"
        print_progress_bar(i - 1, len(submissions_to_process), prefix='Downloading', suffix=status_suffix, length=35)

        if status != "Accepted":
            state["last_synced_timestamp"] = ts
            save_state(args.state, state)
            skip_count += 1
            print_progress_bar(i, len(submissions_to_process), prefix='Downloading', suffix=status_suffix, length=35)
            continue

        # Check if we already have a local solution for this problem/language (e.g. from previous years/runs)
        if has_local_solution("Solved", title, lang):
            state["last_synced_timestamp"] = ts
            save_state(args.state, state)
            skip_count += 1
            print_progress_bar(i, len(submissions_to_process), prefix='Downloading', suffix=f"({i}/{len(submissions_to_process)}) {title} [Exists]", length=35)
            continue

        # Fetch details for the accepted submission
        try:
            details_data = query_graphql(SUBMISSION_DETAILS_QUERY, {"submissionId": sub_id}, headers, domain)
        except Exception as e:
            sys.stdout.write('\n')
            print(f"Error fetching details: {e}")
            print("Stopping sync. You can run the script again to resume.")
            sys.exit(1)

        sub_details = details_data.get('submissionDetails')
        if not sub_details:
            sys.stdout.write('\n')
            print("Error: Could not retrieve submission details.")
            sys.exit(1)

        code = sub_details.get('code')
        question = sub_details.get('question', {})
        question_id = question.get('questionId')
        question_title = question.get('title')

        if not code or not question_id or not question_title:
            sys.stdout.write('\n')
            print("Error: Missing code or question info in submission details.")
            sys.exit(1)

        # Map language to file extension
        ext = LANG_TO_EXT.get(lang.lower(), lang.lower())
        
        # Sanitize folder name
        safe_title = sanitize_name(question_title)
        safe_id = sanitize_name(question_id)
        folder_name = f"{safe_id}.{safe_title}"
        problem_dir = os.path.join("Solved", folder_name)
        
        # Create directory for the problem
        os.makedirs(problem_dir, exist_ok=True)
        
        # Save code to solution file
        file_name = f"solution.{ext}"
        file_path = os.path.join(problem_dir, file_name)
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code)
            success_count += 1
        except Exception as e:
            sys.stdout.write('\n')
            print(f"Error saving file: {e}")
            print("Stopping sync. You can run the script again to resume.")
            sys.exit(1)

        # Update state timestamp
        state["last_synced_timestamp"] = ts
        save_state(args.state, state)

        # Update progress bar showing success
        print_progress_bar(i, len(submissions_to_process), prefix='Downloading', suffix=f"({i}/{len(submissions_to_process)}) {title} [Synced]", length=35)

        # Delay to prevent rate-limiting
        if i < len(submissions_to_process):
            time.sleep(delay)

    print(f"\nSync complete! Success: {success_count}, Skipped: {skip_count}")

if __name__ == "__main__":
    main()
