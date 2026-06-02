# LeetCode Solution Downloader & Sync Tool

A robust Python command-line utility to scrape and sync all your accepted LeetCode solutions locally.

## Features
- **Dedicated Folder Structure**: Organizes each solved problem under its own folder as `Solved/<problem_number>.<problem_title>/solution.<ext>`.
- **Incremental Syncing**: Saves synchronization state to `state.json`. Subsequent runs only retrieve and download solutions submitted *after* the last successful check.
- **Language Support**: Automatically maps LeetCode languages to correct file extensions (Python, C++, Java, JS/TS, Go, Rust, SQL, Bash, etc.).
- **Rate-Limit Safe**: Integrates configurable request delays to respect LeetCode's rate limits and prevent Cloudflare/IP blocking.
- **Interrupt & Resume**: Chronological processing guarantees that if the script is interrupted, it can resume from the exact point of interruption without losing progress or duplicating work.

---

## Installation & Setup

### 1. Requirements
The script uses the `requests` library. Ensure you run it with the Python virtual environment located at `~/Env/venv`.

### 2. Retrieve LeetCode Cookies
Since LeetCode submission data is private, you must authenticate using your browser's session cookies.
1. Open your browser and log in to [LeetCode](https://leetcode.com).
2. Open **Developer Tools** (Press `F12` or `Ctrl + Shift + I` / `Cmd + Option + I`).
3. Select the **Network** tab.
4. Refresh the page or click on any link (e.g. Problems list).
5. Find any request to `leetcode.com` (or `graphql`), look at its **Request Headers**, and find the `Cookie:` header.
6. Copy the **entire** string value of the `Cookie:` header. It should contain `LEETCODE_SESSION=...` and `csrftoken=...`.

### 3. Configuration
The script requires a `config.json` file in the same directory. 

On the first run, the script will automatically create a template `config.json` with placeholders:

```json
{
  "cookie": "LEETCODE_SESSION=your_leetcode_session_here; csrftoken=your_csrftoken_here;",
  "domain": "leetcode.com",
  "rate_limit_delay": 1.0
}
```

Open this `config.json` and replace the values for `LEETCODE_SESSION` and `csrftoken` with your actual cookies.

---

## Usage

Run the script using the virtual environment python interpreter:

```bash
~/Env/venv/bin/python sync_leetcode.py
```

### Command Line Arguments

- **Reset state** (Download everything from scratch):
  ```bash
  ~/Env/venv/bin/python sync_leetcode.py --reset
  ```
- **Custom config / state file paths**:
  ```bash
  ~/Env/venv/bin/python sync_leetcode.py --config /path/to/config.json --state /path/to/state.json
  ```
- **Change request delay** (e.g., set to 2.5 seconds):
  ```bash
  ~/Env/venv/bin/python sync_leetcode.py --delay 2.5
  ```

---

## File Layout Example

Once executed, your solutions will be structured as follows:

```text
LeetCode/
├── config.json
├── state.json
├── sync_leetcode.py
└── Solved/
    ├── 1.Two_Sum/
    │   └── solution.py
    ├── 2.Add_Two_Numbers/
    │   └── solution.cpp
    └── 14.Longest_Common_Prefix/
        ├── solution.py
        └── solution.js
```

---

## Daily Git Push Automation (Contribution Heatmap)

The project includes a `daily_git_push.py` script that automatically stages, commits, and pushes exactly **2 new solutions** each day. This is designed to populate your GitHub contribution graph (heatmap) consistently while avoiding duplicate pushes.

### How it works
1. Scans your `Solved/` folder.
2. Identifies all solved problems and filters out any that have already been pushed (tracked in `git_state.json`).
3. Sorts them numerically.
4. Selects the first 2 unpushed problems.
5. Stages them, commits them with custom commit messages (`Add LeetCode solution: <problem_name>`), updates the push state, and pushes to your remote Git repository.

### Initial Setup
Before scheduling the script, make sure to configure Git in the workspace:

1. **Add your remote repository**:
   ```bash
   git remote add origin git@github.com:your_username/your_leetcode_repo.git
   ```
2. **Configure your Git details** (if not already set globally):
   ```bash
   git config user.name "Your Name"
   git config user.email "your.email@example.com"
   ```

### Scheduling with Cron
To run this automatically every day at a specific time (e.g. 10:00 PM), add a Cron job:

1. Open your crontab editor:
   ```bash
   crontab -e
   ```
2. Add the following line at the bottom of the file (adjusting the paths to match your system):
   ```text
   0 22 * * * cd /home/nitesh/Project_Sandbox/LeetCode && /home/nitesh/Env/venv/bin/python daily_git_push.py >> push.log 2>&1
   ```

Now, every night at 22:00 (10 PM), exactly 2 new solutions will be committed and pushed, keeping your heatmap green!

