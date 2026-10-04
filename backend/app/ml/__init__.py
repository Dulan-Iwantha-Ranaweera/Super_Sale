"""Machine-learning components behind the IPF price forecasting screen."""

import os

# joblib shells out to count physical cores and logs a full traceback when that
# fails on Windows. The work here is single-process, so pin it and stay quiet.
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
