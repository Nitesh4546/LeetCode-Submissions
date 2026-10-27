#################################################################
#                         PURPOSE                               #
#################################################################

# Script to get all submissions and download accepted ones,
# avoiding duplicate submissions being downloaded again.
#
# The submissions are stored in the folder "LeetCode_Solutions"
# with a folder for each problem:
#
# LeetCode_Solutions/
#   └── <problem_no>.<problem_title>/
#       └── solution.<extension>

import os
import sys
import json
import time
import re
import argparse
import requests


# Directory the script itself lives in -- used so output/state paths
# are stable regardless of the working directory the script is invoked from.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOLUTIONS_DIR = os.path.join(SCRIPT_DIR, "LeetCode_Solutions")
MY_PROBLEMS_FILE = os.path.join(SCRIPT_DIR, "my_problems.txt")


# Default configuration values
DEFAULT_DOMAIN = "leetcode.com"
DEFAULT_DELAY = 1.0
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


# ================================================================
# GraphQL Queries
# ================================================================

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


USER_STATUS_QUERY = """
query globalData {
  userStatus {
    isSignedIn
    username
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


MY_SOLVED_PROBLEMS_QUERY = """
query problemsetQuestionList(
  $categorySlug: String,
  $limit: Int,
  $skip: Int,
  $filters: QuestionListFilterInput
) {
  problemsetQuestionList(
    categorySlug: $categorySlug,
    limit: $limit,
    skip: $skip,
    filters: $filters
  ) {
    total
    questions {
      frontendQuestionId
      title
      titleSlug
      status
    }
  }
}
"""


# ================================================================
# Language to extension mapping
# ================================================================

LANG_TO_EXT = {
    "cpp": "cpp",
    "java": "java",
    "python": "py",
    "python3": "py",
    "javascript": "js",
    "typescript": "ts",
    "csharp": "cs",
    "golang": "go",
    "rust": "rs",
    "ruby": "rb",
    "swift": "swift",
    "php": "php",
    "kotlin": "kt",
    "dart": "dart",
    "scala": "scala",
    "c": "c",
    "mysql": "sql",
    "mssql": "sql",
    "oraclesql": "sql",
    "postgresql": "sql",
    "bash": "sh",
}


# ================================================================
# Utility Functions
# ================================================================

def parse_cookies(cookie_string):
    cookies = {}

    for item in cookie_string.split(";"):
        item = item.strip()

        if not item:
            continue

        if "=" in item:
            key, value = item.split("=", 1)
            cookies[key] = value

    return cookies


def sanitize_name(name):
    # Replace characters that are invalid in file/directory names.
    sanitized = re.sub(r'[\\/*?:"<>|]', "_", name)

    # Strip leading/trailing whitespaces or dots.
    sanitized = sanitized.strip(" .")

    # Collapse multiple underscores.
    sanitized = re.sub(r"_+", "_", sanitized)

    return sanitized


def has_local_solution(solved_dir, title, lang):
    if not os.path.exists(solved_dir):
        return False

    safe_title = sanitize_name(title)
    ext = LANG_TO_EXT.get(lang.lower(), lang.lower())

    for item in os.listdir(solved_dir):
        if item.endswith(f".{safe_title}"):
            file_path = os.path.join(
                solved_dir,
                item,
                f"solution.{ext}",
            )

            if os.path.exists(file_path):
                return True

    return False


def load_dotenv(dotenv_path=".env"):
    if not os.path.exists(dotenv_path):
        return

    try:
        with open(dotenv_path, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()

                if not line or line.startswith("#"):
                    continue

                if "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                # Remove surrounding quotes.
                if len(value) >= 2:
                    if (
                        value.startswith('"')
                        and value.endswith('"')
                    ) or (
                        value.startswith("'")
                        and value.endswith("'")
                    ):
                        value = value[1:-1]

                os.environ[key] = value

    except Exception as error:
        print(
            f"Warning: Failed to load .env file "
            f"from {dotenv_path}: {error}"
        )


def load_config(env_path):
    load_dotenv(env_path)

    config = {}

    # Priority:
    # 1. LEETCODE_COOKIE
    # 2. LEETCODE_SESSION + LEETCODE_CSRF_TOKEN
    cookie = os.environ.get("LEETCODE_COOKIE")

    if not cookie:
        session = os.environ.get("LEETCODE_SESSION")
        csrf = os.environ.get("LEETCODE_CSRF_TOKEN", "")

        if session:
            cookie = (
                f"LEETCODE_SESSION={session}; "
                f"csrftoken={csrf};"
            )

    config["cookie"] = cookie or ""
    config["domain"] = os.environ.get(
        "LEETCODE_DOMAIN",
        DEFAULT_DOMAIN,
    )

    delay_str = os.environ.get("LEETCODE_DELAY")

    if delay_str:
        try:
            config["rate_limit_delay"] = float(delay_str)
        except ValueError:
            config["rate_limit_delay"] = DEFAULT_DELAY
    else:
        config["rate_limit_delay"] = DEFAULT_DELAY

    return config


def update_env_var(dotenv_path, key, value):
    lines = []
    found = False

    if os.path.exists(dotenv_path):
        try:
            with open(dotenv_path, "r", encoding="utf-8") as file:
                lines = file.readlines()

        except Exception as error:
            print(
                f"Warning: Failed to read {dotenv_path} "
                f"for updating: {error}"
            )

    for index, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith("#") or "=" not in stripped:
            continue

        line_key, _ = stripped.split("=", 1)

        if line_key.strip() == key:
            lines[index] = f"{key}={value}\n"
            found = True
            break

    if not found:
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")

        lines.append(f"{key}={value}\n")

    try:
        with open(dotenv_path, "w", encoding="utf-8") as file:
            file.writelines(lines)

    except Exception as error:
        print(f"Error writing to {dotenv_path}: {error}")


def load_state(env_path):
    load_dotenv(env_path)

    timestamp_string = os.environ.get(
        "LEETCODE_LAST_SYNCED_TIMESTAMP",
        "0",
    )

    try:
        timestamp = int(timestamp_string)
    except ValueError:
        timestamp = 0

    return {
        "last_synced_timestamp": timestamp
    }


def save_state(env_path, state):
    timestamp = state.get(
        "last_synced_timestamp",
        0,
    )

    try:
        update_env_var(
            env_path,
            "LEETCODE_LAST_SYNCED_TIMESTAMP",
            timestamp,
        )

        os.environ["LEETCODE_LAST_SYNCED_TIMESTAMP"] = str(
            timestamp
        )

    except Exception as error:
        print(f"Error saving state to {env_path}: {error}")


# ================================================================
# GraphQL
# ================================================================

def query_graphql(query, variables, headers, domain):
    url = f"https://{domain}/graphql"

    max_retries = 3
    backoff = 1.5

    for attempt in range(max_retries):
        try:
            response = requests.post(
                url,
                json={
                    "query": query,
                    "variables": variables,
                },
                headers=headers,
                timeout=30,
            )

            if response.status_code != 200:
                if response.status_code == 403:
                    raise Exception(
                        "GraphQL request failed with HTTP 403 "
                        "(Forbidden). Your cookies might be "
                        "invalid or expired."
                    )

                raise Exception(
                    f"GraphQL request failed with HTTP "
                    f"{response.status_code}: {response.text}"
                )

            data = response.json()

            if "errors" in data:
                raise Exception(
                    f"GraphQL returned errors: "
                    f"{data['errors']}"
                )

            return data.get("data", {})

        except Exception as error:
            if attempt == max_retries - 1:
                raise error

            print(
                f"\n[Warning] GraphQL request failed "
                f"(attempt {attempt + 1}/{max_retries}). "
                f"Retrying in {backoff}s... "
                f"(Error: {error})"
            )

            time.sleep(backoff)
            backoff *= 2


# ================================================================
# Terminal Utilities
# ================================================================

def get_terminal_width():
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80


def print_progress_bar(
    iteration,
    total,
    prefix="",
    suffix="",
    decimals=1,
    length=30,
    fill="█",
):
    percent = (
        "{0:." + str(decimals) + "f}"
    ).format(
        100 * (iteration / float(total))
    )

    filled_length = int(
        length * iteration // total
    )

    bar = (
        fill * filled_length
        + "░" * (length - filled_length)
    )

    static_part = (
        f"{prefix} |{bar}| {percent}% "
    )

    width = get_terminal_width()

    max_suffix_len = width - len(static_part) - 4

    if (
        max_suffix_len > 0
        and len(suffix) > max_suffix_len
    ):
        suffix = suffix[:max_suffix_len - 3] + "..."

    sys.stdout.write(
        f"\r\033[K{static_part}{suffix}"
    )

    sys.stdout.flush()

    if iteration == total:
        sys.stdout.write("\n")
        sys.stdout.flush()


# ================================================================
# My Problems Feature
# ================================================================

def fetch_my_solved_problems(headers, domain):
    """
    Fetch all problems that LeetCode officially marks
    as accepted for the authenticated user.
    """

    solved_problems = []

    skip = 0
    limit = 100

    print("Fetching solved problems...")

    while True:
        variables = {
            "categorySlug": "",
            "skip": skip,
            "limit": limit,
            "filters": {
                "status": "AC"
            },
        }

        try:
            data = query_graphql(
                MY_SOLVED_PROBLEMS_QUERY,
                variables,
                headers,
                domain,
            )

        except Exception as error:
            print(
                f"Error fetching solved problems: {error}"
            )
            sys.exit(1)

        problem_data = data.get(
            "problemsetQuestionList"
        )

        if not problem_data:
            print(
                "Error: Failed to retrieve solved problems."
            )
            sys.exit(1)

        questions = problem_data.get(
            "questions",
            [],
        )

        if not questions:
            break

        for question in questions:
            problem_id = question.get(
                "frontendQuestionId"
            )

            title = question.get("title")

            if not problem_id or not title:
                continue

            try:
                problem_number = int(problem_id)

            except ValueError:
                continue

            solved_problems.append(
                {
                    "problem_number": problem_number,
                    "title": title,
                }
            )

        total = problem_data.get("total", 0)

        print(
            f"Retrieved {len(solved_problems)} "
            f"of {total} solved problems..."
        )

        skip += limit

        if skip >= total:
            break

        time.sleep(0.5)

    # Sort by problem number.
    solved_problems.sort(
        key=lambda problem: problem["problem_number"]
    )

    return solved_problems


def save_my_problems(problems):
    """
    Save all solved problems to my_problems.txt.
    """

    try:
        with open(
            MY_PROBLEMS_FILE,
            "w",
            encoding="utf-8",
        ) as file:

            for problem in problems:
                file.write(
                    f"{problem['problem_number']}. "
                    f"{problem['title']}\n"
                )

        print(
            f"\nSuccessfully generated "
            f"{len(problems)} solved problems."
        )

        print(
            f"Saved to: {MY_PROBLEMS_FILE}"
        )

    except Exception as error:
        print(
            f"Error saving solved problems file: {error}"
        )
        sys.exit(1)


# ================================================================
# Main
# ================================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Sync solved LeetCode solutions "
            "to local files."
        )
    )

    parser.add_argument(
        "--env",
        default=os.path.join(SCRIPT_DIR, ".env"),
        help="Path to .env config file",
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Reset sync state and download "
            "everything from scratch"
        ),
    )

    parser.add_argument(
        "--delay",
        type=float,
        help=(
            "Delay between downloading submissions "
            "(in seconds)"
        ),
    )

    parser.add_argument(
        "--my-problems",
        action="store_true",
        help=(
            "Generate a text file containing all "
            "solved LeetCode problems"
        ),
    )

    args = parser.parse_args()

    # Auto-migration from config.json.
    if (
        not os.path.exists(args.env)
        and os.path.exists(
            os.path.join(SCRIPT_DIR, "config.json")
        )
    ):
        print(
            "Found legacy 'config.json'. "
            "Migrating configuration to '.env'..."
        )

        try:
            with open(
                os.path.join(
                    SCRIPT_DIR,
                    "config.json",
                ),
                "r",
                encoding="utf-8",
            ) as file:
                old_config = json.load(file)

            cookie_str = old_config.get("cookie", "")
            cookies = parse_cookies(cookie_str)

            session = cookies.get(
                "LEETCODE_SESSION",
                "",
            )

            csrf = cookies.get(
                "csrftoken",
                "",
            )

            domain = old_config.get(
                "domain",
                DEFAULT_DOMAIN,
            )

            delay_value = old_config.get(
                "rate_limit_delay",
                DEFAULT_DELAY,
            )

            with open(
                args.env,
                "w",
                encoding="utf-8",
            ) as file:

                file.write(
                    "# LeetCode Configuration "
                    "Environment Variables\n\n"
                )

                file.write(
                    f"LEETCODE_SESSION={session}\n"
                )

                file.write(
                    f"LEETCODE_CSRF_TOKEN={csrf}\n"
                )

                file.write(
                    f"LEETCODE_DOMAIN={domain}\n"
                )

                file.write(
                    f"LEETCODE_DELAY={delay_value}\n"
                )

            print(
                f"Migration complete! "
                f"Created '{args.env}' successfully."
            )

            try:
                os.rename(
                    os.path.join(
                        SCRIPT_DIR,
                        "config.json",
                    ),
                    os.path.join(
                        SCRIPT_DIR,
                        "config.json.bak",
                    ),
                )

                print(
                    "Renamed 'config.json' to "
                    "'config.json.bak' for backup."
                )

            except Exception as error:
                print(
                    f"Warning: Could not rename "
                    f"config.json: {error}"
                )

        except Exception as error:
            print(
                f"Warning: Migration failed: {error}"
            )

    # Create .env template if it does not exist.
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
            with open(
                args.env,
                "w",
                encoding="utf-8",
            ) as file:
                file.write(default_env)

            print(
                f"\nCreated configuration template "
                f"at '{args.env}'."
            )

            print(
                "Please edit this file and replace "
                "the placeholder values with your "
                "actual LeetCode cookies."
            )

            print(
                "See README.md for instructions on "
                "how to retrieve your cookies."
            )

        except Exception as error:
            print(
                f"Error creating template .env file: "
                f"{error}"
            )

        sys.exit(1)

    # Load configuration.
    config = load_config(args.env)

    # Migrate legacy state.json if present.
    if os.path.exists(
        os.path.join(SCRIPT_DIR, "state.json")
    ):
        print(
            "Found legacy 'state.json'. "
            "Migrating sync state to '.env'..."
        )

        try:
            with open(
                os.path.join(
                    SCRIPT_DIR,
                    "state.json",
                ),
                "r",
                encoding="utf-8",
            ) as file:
                old_state = json.load(file)

            timestamp = old_state.get(
                "last_synced_timestamp",
                0,
            )

            update_env_var(
                args.env,
                "LEETCODE_LAST_SYNCED_TIMESTAMP",
                timestamp,
            )

            os.environ[
                "LEETCODE_LAST_SYNCED_TIMESTAMP"
            ] = str(timestamp)

            print(
                f"Migration complete! "
                f"Saved last_synced_timestamp={timestamp} "
                f"to '{args.env}'."
            )

            try:
                os.rename(
                    os.path.join(
                        SCRIPT_DIR,
                        "state.json",
                    ),
                    os.path.join(
                        SCRIPT_DIR,
                        "state.json.bak",
                    ),
                )

                print(
                    "Renamed 'state.json' to "
                    "'state.json.bak' for backup."
                )

            except Exception as error:
                print(
                    f"Warning: Could not rename "
                    f"state.json: {error}"
                )

        except Exception as error:
            print(
                f"Warning: State migration failed: {error}"
            )

    # Validate cookie configuration.
    cookie_value = config.get("cookie", "")

    if (
        not cookie_value
        or "your_leetcode_session_here" in cookie_value
        or "your_csrftoken_here" in cookie_value
        or "your_leetcode_session_here"
        in os.environ.get("LEETCODE_SESSION", "")
        or "your_csrftoken_here"
        in os.environ.get("LEETCODE_CSRF_TOKEN", "")
    ):
        print(
            f"\nError: Please configure your actual "
            f"LeetCode cookie in '{args.env}'."
        )

        print(
            "It currently contains placeholder values "
            "or is empty."
        )

        print(
            "See README.md for details on how to "
            "get your cookies."
        )

        sys.exit(1)

    cookie_string = config["cookie"]

    domain = config.get(
        "domain",
        DEFAULT_DOMAIN,
    )

    delay = (
        args.delay
        if args.delay is not None
        else config.get(
            "rate_limit_delay",
            DEFAULT_DELAY,
        )
    )

    # Parse cookies to extract csrftoken.
    cookies = parse_cookies(cookie_string)
    csrf_token = cookies.get("csrftoken")

    if not csrf_token:
        print(
            "Warning: 'csrftoken' cookie not found "
            "in the provided cookie string."
        )

        print(
            "Proceeding, but requests might fail if "
            "CSRF validation is strict."
        )

    # Setup headers.
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Content-Type": "application/json",
        "Referer": f"https://{domain}",
        "Cookie": cookie_string,
    }

    if csrf_token:
        headers["x-csrftoken"] = csrf_token

    # Verify authentication.
    try:
        status_data = query_graphql(
            USER_STATUS_QUERY,
            {},
            headers,
            domain,
        )

        user_status = status_data.get(
            "userStatus",
            {},
        )

        if not user_status.get("isSignedIn"):
            print(
                "\nError: LeetCode does not recognize "
                "you as signed in."
            )

            print(
                "Your LEETCODE_SESSION / csrftoken "
                "cookies are likely expired or invalid."
            )

            print(
                f"Please grab fresh cookies from "
                f"{domain} and update '{args.env}'."
            )

            sys.exit(1)

        print(
            f"Authenticated as: "
            f"{user_status.get('username')}"
        )

    except Exception as error:
        print(
            f"\nWarning: Could not verify "
            f"authentication status: {error}"
        )

    # ============================================================
    # Handle --my-problems
    # ============================================================

    if args.my_problems:
        solved_problems = fetch_my_solved_problems(
            headers,
            domain,
        )

        if not solved_problems:
            print("\nNo solved problems were found.")
            sys.exit(0)

        save_my_problems(solved_problems)

        # Do not continue with normal sync.
        sys.exit(0)

    # ============================================================
    # Normal Sync Logic
    # ============================================================

    if args.reset:
        state = {
            "last_synced_timestamp": 0
        }

        print(
            "Resetting sync state. Script will sync "
            "all solved questions."
        )

    else:
        state = load_state(args.env)

    last_synced_timestamp = state.get(
        "last_synced_timestamp",
        0,
    )

    if last_synced_timestamp > 0:
        sync_time = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(last_synced_timestamp),
        )
    else:
        sync_time = "Beginning of time"

    print(
        f"Syncing submissions solved after: {sync_time}"
    )

    # Fetch submissions.
    offset = 0
    limit = 20
    submissions_to_process = []
    has_next = True

    print("Fetching submission history...")

    while has_next:
        variables = {
            "offset": offset,
            "limit": limit,
        }

        try:
            data = query_graphql(
                SUBMISSION_LIST_QUERY,
                variables,
                headers,
                domain,
            )

        except Exception as error:
            print(
                f"Error fetching submissions list: {error}"
            )
            sys.exit(1)

        submission_list_data = data.get(
            "submissionList"
        )

        if not submission_list_data:
            print(
                "Error: Failed to retrieve submission "
                "list. Check if your cookies are valid."
            )
            sys.exit(1)

        submissions = submission_list_data.get(
            "submissions",
            [],
        )

        if not submissions:
            break

        stop_fetching = False

        for submission in submissions:
            timestamp = int(
                submission["timestamp"]
            )

            if timestamp <= last_synced_timestamp:
                stop_fetching = True
                break

            submissions_to_process.append(
                submission
            )

        if stop_fetching:
            print(
                "Reached previously synchronized submissions."
            )
            break

        has_next = submission_list_data.get(
            "hasNext",
            False,
        )

        offset += limit

        print(
            f"Retrieved {len(submissions_to_process)} "
            f"new submissions so far..."
        )

        time.sleep(0.5)

    if not submissions_to_process:
        print(
            "No new submissions found. "
            "Everything is up to date!"
        )
        sys.exit(0)

    # Remove duplicate accepted submissions.
    seen_accepted = set()
    deduplicated_count = 0

    for submission in submissions_to_process:
        if submission["statusDisplay"] == "Accepted":
            key = (
                submission["titleSlug"],
                submission["lang"].lower(),
            )

            if key in seen_accepted:
                submission["statusDisplay"] = "Duplicate"
                deduplicated_count += 1
            else:
                seen_accepted.add(key)

    if deduplicated_count > 0:
        print(
            f"Deduplicated {deduplicated_count} "
            f"older accepted submissions "
            f"(will skip downloading them)."
        )

    # Process chronologically.
    submissions_to_process.reverse()

    print(
        f"\nProcessing "
        f"{len(submissions_to_process)} submissions "
        f"in chronological order..."
    )

    os.makedirs(
        SOLUTIONS_DIR,
        exist_ok=True,
    )

    success_count = 0
    skip_count = 0

    for index, submission in enumerate(
        submissions_to_process,
        1,
    ):
        timestamp = int(
            submission["timestamp"]
        )

        submission_id = int(
            submission["id"]
        )

        title = submission["title"]
        status = submission["statusDisplay"]
        language = submission["lang"]

        status_suffix = (
            f"({index}/{len(submissions_to_process)}) "
            f"{title} [{status}]"
        )

        print_progress_bar(
            index - 1,
            len(submissions_to_process),
            prefix="Downloading",
            suffix=status_suffix,
            length=35,
        )

        if status != "Accepted":
            state["last_synced_timestamp"] = timestamp

            save_state(
                args.env,
                state,
            )

            skip_count += 1

            print_progress_bar(
                index,
                len(submissions_to_process),
                prefix="Downloading",
                suffix=status_suffix,
                length=35,
            )

            continue

        # Check whether the solution already exists.
        if has_local_solution(
            SOLUTIONS_DIR,
            title,
            language,
        ):
            state["last_synced_timestamp"] = timestamp

            save_state(
                args.env,
                state,
            )

            skip_count += 1

            print_progress_bar(
                index,
                len(submissions_to_process),
                prefix="Downloading",
                suffix=(
                    f"({index}/"
                    f"{len(submissions_to_process)}) "
                    f"{title} [Exists]"
                ),
                length=35,
            )

            continue

        # Fetch submission details.
        try:
            details_data = query_graphql(
                SUBMISSION_DETAILS_QUERY,
                {
                    "submissionId": submission_id
                },
                headers,
                domain,
            )

        except Exception as error:
            sys.stdout.write("\n")

            print(
                f"Error fetching details: {error}"
            )

            print(
                "Stopping sync. You can run the script "
                "again to resume."
            )

            sys.exit(1)

        submission_details = details_data.get(
            "submissionDetails"
        )

        if not submission_details:
            sys.stdout.write("\n")

            print(
                "Error: Could not retrieve "
                "submission details."
            )

            sys.exit(1)

        code = submission_details.get("code")

        question = submission_details.get(
            "question",
            {},
        )

        question_id = question.get(
            "questionId"
        )

        question_title = question.get(
            "title"
        )

        if (
            not code
            or not question_id
            or not question_title
        ):
            sys.stdout.write("\n")

            print(
                "Error: Missing code or question info "
                "in submission details."
            )

            sys.exit(1)

        # Determine file extension.
        extension = LANG_TO_EXT.get(
            language.lower(),
            language.lower(),
        )

        safe_title = sanitize_name(
            question_title
        )

        safe_id = sanitize_name(
            question_id
        )

        folder_name = (
            f"{safe_id}.{safe_title}"
        )

        problem_directory = os.path.join(
            SOLUTIONS_DIR,
            folder_name,
        )

        os.makedirs(
            problem_directory,
            exist_ok=True,
        )

        file_name = f"solution.{extension}"

        file_path = os.path.join(
            problem_directory,
            file_name,
        )

        try:
            with open(
                file_path,
                "w",
                encoding="utf-8",
            ) as file:
                file.write(code)

            success_count += 1

        except Exception as error:
            sys.stdout.write("\n")

            print(
                f"Error saving file: {error}"
            )

            print(
                "Stopping sync. You can run the script "
                "again to resume."
            )

            sys.exit(1)

        # Update sync state.
        state["last_synced_timestamp"] = timestamp

        save_state(
            args.env,
            state,
        )

        print_progress_bar(
            index,
            len(submissions_to_process),
            prefix="Downloading",
            suffix=(
                f"({index}/"
                f"{len(submissions_to_process)}) "
                f"{title} [Synced]"
            ),
            length=35,
        )

        # Delay to prevent rate limiting.
        if index < len(submissions_to_process):
            time.sleep(delay)

    print(
        f"\nSync complete! "
        f"Success: {success_count}, "
        f"Skipped: {skip_count}"
    )


if __name__ == "__main__":
    main()
