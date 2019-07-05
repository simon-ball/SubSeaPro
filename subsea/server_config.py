import os
from pathlib import PurePosixPath


# Using server : it's a Unix system, and thus use a posix path.
# These are parameterised because they are used repeaedly
finished = 'finished'
jobs = 'jobs'
failed = 'failed'
download = 'download'
progress = "_progress.txt"
complete = "_completed.zip"

root = PurePosixPath(".")
root_job = root / jobs
root_finished = root / finished
root_failed = root / failed
root_download = root / download



list_finished = os.path.join(root_finished, r"finished.txt")
list_failed = os.path.join(root_failed, r"failed.txt")

file_in = "Field-Opt.run"
file_out = "output.out"
bash_command = "ampl "



suffixes = (".dat", ".mod", ".run", ".log", ".tab")

