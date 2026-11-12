"""`python -m kestrel ...`.

`--home <folder>` is applied before anything reads the home folder. Hook calls from Claude Code
(`hook claude-code`) take a short path that imports only what they need: they run on every tool
call, so they must start fast.
"""

import os
import sys

if "--home" in sys.argv:
    i = sys.argv.index("--home")
    if i + 1 < len(sys.argv):
        os.environ["KESTREL_HOME"] = sys.argv[i + 1]
        del sys.argv[i : i + 2]

if sys.argv[1:3] == ["hook", "claude-code"]:
    from kestrel.adapters.claude_code_hooks import main as hook_main

    sys.exit(hook_main())

from kestrel.cli import main  # noqa: E402

main()
