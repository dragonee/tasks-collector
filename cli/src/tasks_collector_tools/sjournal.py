"""Add journal entry with Jira output as template.

Usage:
    sjournal [options]

Options:
    -d, --date DATE  Use this date for the journal entry.
    -T TAGS, --tags TAGS  Add these tags to the journal entry.
    -s               Also save a copy as new observation, filling Situation field.
    -o               Alias for -s.
    -Y, --yesterday  Use yesterday's date for the journal entry.
    -t THREAD, --thread THREAD  Use this thread [default: Daily]
    -L, --today      List journals from today.
    -h, --help       Show this message.
    --version        Show version information.
"""

import os
import shutil
import subprocess
import sys
import tempfile


def main():
    from docopt import docopt

    arguments = docopt(__doc__, version='1.0')

    # Check if jira command exists
    if shutil.which('jira') is None:
        print("Error: 'jira' command not found. Please install jira CLI first.")
        sys.exit(1)

    # Build jira command with date options
    jira_cmd = ['jira', '-l']
    if arguments['--date']:
        jira_cmd.extend(['--date', arguments['--date']])
    if arguments['--yesterday']:
        jira_cmd.append('-Y')

    # Run jira -l and capture output
    try:
        result = subprocess.run(jira_cmd, capture_output=True, text=True)
        jira_output = result.stdout
    except Exception as e:
        print(f"Error running '{' '.join(jira_cmd)}': {e}")
        sys.exit(1)

    # Process jira output: prepend tasks with checkbox, skip Total line
    processed_lines = []
    for line in jira_output.splitlines():
        if line.strip() and not line.startswith('Total'):
            processed_lines.append(f"- [ ] {line}")
        else:
            processed_lines.append(line)
    processed_output = '\n'.join(processed_lines)

    # Write jira output to a temporary file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md') as f:
        f.write(processed_output)
        tmpfile_path = f.name

    # Build journal command with the file
    cmd = ['journal', '-f', tmpfile_path]

    # Pass through relevant options
    if arguments['--date']:
        cmd.extend(['-d', arguments['--date']])
    if arguments['--tags']:
        cmd.extend(['-T', arguments['--tags']])
    if arguments['-s']:
        cmd.append('-s')
    if arguments['-o']:
        cmd.append('-o')
    if arguments['--yesterday']:
        cmd.append('-Y')
    if arguments['--thread']:
        cmd.extend(['-t', arguments['--thread']])
    if arguments['--today']:
        cmd.append('-L')

    # Run journal with the jira output as template
    try:
        result = subprocess.run(cmd)
    finally:
        # Clean up the temporary file
        os.unlink(tmpfile_path)

    sys.exit(result.returncode)
