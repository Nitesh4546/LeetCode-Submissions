#!/usr/bin/env python3
#################################################################
#                         PURPOSE                               #
#################################################################

# script is to get all the submission i have till now and download them ony those who accepted ,
# avoiding duplication submissions to be downloaded again
# the the submissions are stored in the folder "LeetCode_Solution" with folder for each problem folder name=> <p.no><p.title>
# folder tree
# LeetCode_Solution
#   |-><problem no><probelm title>
#            |-><problem no><problem title>

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

def load_dotenv(dotenv_path=".env"):
    if os.path.exists(dotenv_path):
        try:
            with open(dotenv_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, val = line.split('=', 1)
                        key = key.strip()
                        val = val.strip()
                        # Remove surrounding quotes (both single and double) if present
                        if len(val) >= 2 and (
                            (val.startswith('"') and val.endswith('"')) or
                            (val.startswith("'") and val.endswith("'"))
                        ):
                            val = val[1:-1]
                        os.environ[key] = val
        except Exception as e:
            print(f"Warning: Failed to load .env file from {dotenv_path}: {e}")

def load_config(env_path):
    load_dotenv(env_path)
    
    config = {}
    
    # Priority:
    # 1. LEETCODE_COOKIE
    # 2. LEETCODE_SESSION & LEETCODE_CSRF_TOKEN
    cookie = os.environ.get('LEETCODE_COOKIE')
    if not cookie:
        session = os.environ.get('LEETCODE_SESSION')
        csrf = os.environ.get('LEETCODE_CSRF_TOKEN', '')
        if session:
            cookie = f"LEETCODE_SESSION={session}; csrftoken={csrf};"
    
    config['cookie'] = cookie or ''
    config['domain'] = os.environ.get('LEETCODE_DOMAIN', DEFAULT_DOMAIN)
    
    delay_str = os.environ.get('LEETCODE_DELAY')
    if delay_str:
        try:
            config['rate_limit_delay'] = float(delay_str)
        except ValueError:
            config['rate_limit_delay'] = DEFAULT_DELAY
    else:
        config['rate_limit_delay'] = DEFAULT_DELAY
        
    return config

def update_env_var(dotenv_path, key, value):
    lines = []
    found = False
    if os.path.exists(dotenv_path):
        try:
            with open(dotenv_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception as e:
            print(f"Warning: Failed to read {dotenv_path} for updating: {e}")
            
    # Iterate through the lines and look for key=
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('#') or not '=' in stripped:
            continue
        line_key, _ = stripped.split('=', 1)
        if line_key.strip() == key:
            lines[idx] = f"{key}={value}\n"
            found = True
            break
            
    if not found:
        # If not found, check if last line ends with newline
        if lines and not lines[-1].endswith('\n'):
            lines.append('\n')
        lines.append(f"{key}={value}\n")
        
    try:
        with open(dotenv_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
    except Exception as e:
        print(f"Error writing to {dotenv_path}: {e}")

def load_state(env_path):
    load_dotenv(env_path)
    ts_str = os.environ.get("LEETCODE_LAST_SYNCED_TIMESTAMP", "0")
    try:
        ts = int(ts_str)
    except ValueError:
        ts = 0
    return {"last_synced_timestamp": ts}

def save_state(env_path, state):
    ts = state.get("last_synced_timestamp", 0)
    try:
        update_env_var(env_path, "LEETCODE_LAST_SYNCED_TIMESTAMP", ts)
        os.environ["LEETCODE_LAST_SYNCED_TIMESTAMP"] = str(ts)
    except Exception as e:
        print(f"Error saving state to {env_path}: {e}")

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
    parser.add_argument("--env", default=".env", help="Path to .env config file")
    parser.add_argument("--reset", action="store_true", help="Reset sync state and download everything from scratch")
    parser.add_argument("--delay", type=float, help="Delay between downloading submissions (in seconds)")
    args = parser.parse_args()

    # Auto-migration: If .env doesn't exist, but config.json exists, migrate it!
    if not os.path.exists(args.env) and os.path.exists("config.json"):
        print("Found legacy 'config.json'. Migrating configuration to '.env'...")
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                old_config = json.load(f)
            cookie_str = old_config.get("cookie", "")
            cookies = parse_cookies(cookie_str)
            session = cookies.get("LEETCODE_SESSION", "")
            csrf = cookies.get("csrftoken", "")
            domain = old_config.get("domain", "leetcode.com")
            delay_val = old_config.get("rate_limit_delay", 1.0)
            
            with open(args.env, "w", encoding="utf-8") as f:
                f.write("# LeetCode Configuration Environment Variables\n\n")
                f.write(f"LEETCODE_SESSION={session}\n")
                f.write(f"LEETCODE_CSRF_TOKEN={csrf}\n")
                f.write(f"LEETCODE_DOMAIN={domain}\n")
                f.write(f"LEETCODE_DELAY={delay_val}\n")
            print(f"Migration complete! Created '{args.env}' successfully.")
            try:
                os.rename("config.json", "config.json.bak")
                print("Renamed 'config.json' to 'config.json.bak' for backup.")
            except Exception as e:
                print(f"Warning: Could not rename config.json: {e}")
        except Exception as e:
            print(f"Warning: Migration failed: {e}")

    # If .env file doesn't exist, create it with placeholders
    if not os.path.exists(args.env):
        default_env = (
            "# LeetCode Configuration Environment Variables\n\n"
            "# Copy cookies from leetcode website and place them here:\n"
            "LEETCODE_SESSION=your_leetcode_session_here\n"
            "LEETCODE_CSRF_TOKEN=your_csrftoken_here\n\n"
            "# Optional configuration:\n"
            "# LEETCODE_DOMAIN=leetcode.com\n"
            "# LEETCODE_DELAY=1.0\n"
        )
        try:
            with open(args.env, "w", encoding="utf-8") as f:
                f.write(default_env)
            print(f"\nCreated configuration template at '{args.env}'.")
            print("Please edit this file and replace the placeholder values with your actual LeetCode cookies.")
            print("See README.md for instructions on how to retrieve your cookies.")
        except Exception as e:
            print(f"Error creating template .env file: {e}")
        sys.exit(1)

    # Load configuration
    config = load_config(args.env)

    # Auto-migration of state: If state.json exists, migrate it to the env file!
    if os.path.exists("state.json"):
        print("Found legacy 'state.json'. Migrating sync state to '.env'...")
        try:
            with open("state.json", "r", encoding="utf-8") as f:
                old_state = json.load(f)
            ts = old_state.get("last_synced_timestamp", 0)
            update_env_var(args.env, "LEETCODE_LAST_SYNCED_TIMESTAMP", ts)
            os.environ["LEETCODE_LAST_SYNCED_TIMESTAMP"] = str(ts)
            print(f"Migration complete! Saved last_synced_timestamp={ts} to '{args.env}'.")
            try:
                os.rename("state.json", "state.json.bak")
                print("Renamed 'state.json' to 'state.json.bak' for backup.")
            except Exception as e:
                print(f"Warning: Could not rename state.json: {e}")
        except Exception as e:
            print(f"Warning: State migration failed: {e}")
    
    # Check if the cookie is set and is not a placeholder
    cookie_val = config.get('cookie', '')
    if (not cookie_val or 
        "your_leetcode_session_here" in cookie_val or 
        "your_csrftoken_here" in cookie_val or
        "your_leetcode_session_here" in os.environ.get('LEETCODE_SESSION', '') or
        "your_csrftoken_here" in os.environ.get('LEETCODE_CSRF_TOKEN', '')):
        print(f"\nError: Please configure your actual LeetCode cookie in '{args.env}'.")
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
        state = load_state(args.env)

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

    # Create LeetCode_Solutions directory if it doesn't exist
    os.makedirs("LeetCode_Solutions", exist_ok=True)

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
            save_state(args.env, state)
            skip_count += 1
            print_progress_bar(i, len(submissions_to_process), prefix='Downloading', suffix=status_suffix, length=35)
            continue

        # Check if we already have a local solution for this problem/language (e.g. from previous years/runs)
        if has_local_solution("LeetCode_Solutions", title, lang):
            state["last_synced_timestamp"] = ts
            save_state(args.env, state)
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
        problem_dir = os.path.join("LeetCode_Solutions", folder_name)
        
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
        save_state(args.env, state)

        # Update progress bar showing success
        print_progress_bar(i, len(submissions_to_process), prefix='Downloading', suffix=f"({i}/{len(submissions_to_process)}) {title} [Synced]", length=35)

        # Delay to prevent rate-limiting
        if i < len(submissions_to_process):
            time.sleep(delay)

    print(f"\nSync complete! Success: {success_count}, Skipped: {skip_count}")

if __name__ == "__main__":
    main()
