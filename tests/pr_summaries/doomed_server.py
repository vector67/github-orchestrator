import sys
from pathlib import Path

from tests.pr_summaries.support import THE_PR, Lane

tmp_path, behaviour = sys.argv[1:]
Lane(Path(tmp_path), behaviour).lane.start(THE_PR, use_github_api=False)
